const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { createRequire } = require('node:module');
const base = path.resolve(__dirname, '..');
const cache = new Map();
function load(relative) {
  const filename = path.resolve(base, relative);
  if (cache.has(filename)) return cache.get(filename);
  const localRequire = createRequire(filename);
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  vm.runInNewContext(code, { module, exports: module.exports, URLSearchParams, AbortController, setTimeout, clearTimeout, JSON, fetch: (...args) => globalThis.fetch(...args), require: name => name.startsWith('.') ? load(path.relative(base, path.resolve(path.dirname(filename), name + '.ts'))) : localRequire(name) }, { filename });
  cache.set(filename, module.exports);
  return module.exports;
}
// Values built inside the vm context have another Object prototype: compare plain copies.
const plain = value => JSON.parse(JSON.stringify(value));
const s = load('src/domain/similarity.ts');
const { postSearch } = load('src/data/similarityApi.ts');

const jezero = { id: 'jezero', name: 'Jezero', body: 'Mars', available: true, kind: 'landing_site', status: 'measured', center: null, sources: [], limitations: ['x'],
  views: { escabrosidad: 'reference_has_data', forma_hipsometrica: 'reference_has_data', espectral: 'not_fitted', radar: 'reference_missing' } };
const catalog = { references: [jezero], default_weights: { Mars: { escabrosidad: 0.5, espectral: 0.2 }, Moon: {} }, views: {}, engine_status: 'unsupervised_pending_blind_validation' };

test('untouched weights are not sent, so the server applies its own defaults', () => {
  const controls = s.defaultControls(jezero, catalog);
  assert.deepEqual(plain(controls.weights), { escabrosidad: 0.5, espectral: 0.2 });
  const request = s.buildRequest('jezero', controls);
  assert.equal('weights' in request, false);
  assert.deepEqual(plain(request), { reference: 'jezero', only_eligible: true, limit: 25, fusion: 'weighted', missing_policy: 'neutral' });
});
test('touched weights are sent rounded', () => {
  const controls = { ...s.defaultControls(jezero, catalog), touched: true };
  controls.weights = { escabrosidad: 0.30000000000000004, espectral: 0 };
  assert.deepEqual(plain(s.buildRequest('jezero', controls).weights), { escabrosidad: 0.3, espectral: 0 });
});
test('only views that are fitted and measured on the reference are usable', () => {
  assert.deepEqual(plain(s.usableViews(jezero)), ['escabrosidad', 'forma_hipsometrica']);
  assert.deepEqual(plain(s.usableViews(undefined)), []);
});
test('all-zero weights are caught before the server refuses them', () => {
  const usable = s.usableViews(jezero);
  const request = (weights) => ({ ...s.buildRequest('jezero', { ...s.defaultControls(jezero, catalog), touched: true, weights }) });
  assert.equal(s.noWeight(request({ escabrosidad: 0, forma_hipsometrica: 0, espectral: 0 }), usable), true);
  assert.equal(s.noWeight(request({ escabrosidad: 0.2, forma_hipsometrica: 0 }), usable), false);
  assert.equal(s.noWeight(s.buildRequest('jezero', s.defaultControls(jezero, catalog)), usable), false);
});
test('requests with the same content have the same key', () => {
  const a = s.buildRequest('jezero', s.defaultControls(jezero, catalog));
  assert.equal(s.requestKey(a), s.requestKey({ ...a }));
  assert.notEqual(s.requestKey(a), s.requestKey({ ...a, fusion: 'rrf' }));
});
test('server errors become readable messages', () => {
  assert.equal(s.errorMessage('Referencia desconocida', 404), 'Referencia desconocida');
  assert.equal(s.errorMessage([{ msg: 'Input should be less than or equal to 1000' }, { msg: 'campo extra' }], 422), 'Input should be less than or equal to 1000; campo extra');
  assert.match(s.errorMessage(undefined, 503), /no está disponible/);
  assert.match(s.errorMessage(undefined, 500), /No se pudo completar/);
});
test('the strongest feature contributions come first', () => {
  const view = { distance: 0.1, weight: 1, available: true, features: { a: { candidate: 1, reference: 2, z_delta: 1, share: 0.1 }, b: { candidate: 1, reference: 2, z_delta: 1, share: -0.6 }, c: { candidate: 1, reference: 2, z_delta: 1, share: 0.3 } } };
  assert.deepEqual(plain(s.topFeatures(view, 2).map(([name]) => name)), ['b', 'c']);
  assert.deepEqual(plain(s.topFeatures(undefined)), []);
});
test('the interval bar stays inside the track and never disappears', () => {
  assert.deepEqual(plain(s.scoreWidth(0.2, 0.5)), { left: 20, width: 30 });
  assert.equal(s.scoreWidth(0.3, 0.3).width, 0.5);
  assert.deepEqual(plain(s.scoreWidth(-1, 2)), { left: 0, width: 100 });
});
test('places are written with hemispheres', () => {
  assert.match(s.placeLabel(-87.45, -5), /87,45° S, 5° O/);
  assert.match(s.placeLabel(18.44, 77.45), /18,44° N, 77,45° E/);
});

async function withFetch(impl, run) {
  const real = globalThis.fetch; globalThis.fetch = impl;
  try { return await run(); } finally { globalThis.fetch = real; }
}
const answer = (status, body) => async () => ({ ok: status < 300, status, json: async () => body });
test('postSearch posts the request as JSON and returns the response', async () => {
  let seen;
  const out = await withFetch(async (url, init) => { seen = { url, init }; return { ok: true, status: 200, json: async () => ({ query_id: 'q' }) }; },
    () => postSearch({ reference: 'jezero' }, new AbortController().signal));
  assert.equal(out.query_id, 'q');
  assert.equal(seen.url, '/api/similarity/search');
  assert.equal(seen.init.method, 'POST');
  assert.equal(seen.init.headers['Content-Type'], 'application/json');
  assert.deepEqual(plain(JSON.parse(seen.init.body)), { reference: 'jezero' });
});
test('postSearch turns API errors into messages', async () => {
  await withFetch(answer(404, { detail: 'Referencia no disponible' }), async () =>
    assert.rejects(postSearch({}, new AbortController().signal), /Referencia no disponible/));
  await withFetch(answer(422, { detail: [{ msg: 'peso inválido' }] }), async () =>
    assert.rejects(postSearch({}, new AbortController().signal), /peso inválido/));
  await withFetch(async () => ({ ok: false, status: 503, json: async () => { throw new Error('no json'); } }), async () =>
    assert.rejects(postSearch({}, new AbortController().signal), /no está disponible/));
  await withFetch(async () => ({ ok: true, status: 200, json: async () => { throw new Error('bad'); } }), async () =>
    assert.rejects(postSearch({}, new AbortController().signal), /formato esperado/));
});

// The client must stay inside the published contract (specs/api): these tests read the schemas.
const specs = path.resolve(base, '..', 'specs/api');
const motor = JSON.parse(fs.readFileSync(path.join(specs, 'motor-busqueda-v1.schema.json'), 'utf8'));
const api = JSON.parse(fs.readFileSync(path.join(specs, 'similitud-api-v1.schema.json'), 'utf8'));
const keys = object => Object.keys(object).sort();

test('every view, kind and view status of the contract has a label', () => {
  assert.deepEqual(keys(s.VIEW_LABELS), [...api.$defs.ViewId.enum].sort());
  assert.deepEqual(keys(s.VIEW_LABELS), [...motor.$defs.ViewId.enum].sort());
  assert.deepEqual(keys(s.KIND_LABELS), api.$defs.ReferenceEntry.properties.kind.enum.filter(Boolean).sort());
  assert.deepEqual(keys(s.STATUS_TEXT), [...api.$defs.ViewStatus.enum].sort());
  assert.deepEqual(keys(s.BODY_LABELS), [...api.$defs.ReferenceEntry.properties.body.enum].sort());
});
test('the request the client builds is a valid SearchRequest', () => {
  const schema = motor.$defs.SearchRequest;
  const controls = { ...s.defaultControls(jezero, catalog), touched: true };
  const request = s.buildRequest('jezero', controls);
  for (const key of Object.keys(request)) assert.ok(key in schema.properties, `campo desconocido: ${key}`);
  assert.ok(schema.required.every(key => key in request));
  assert.ok(schema.properties.fusion.enum.includes(request.fusion));
  assert.ok(schema.properties.missing_policy.enum.includes(request.missing_policy));
  assert.ok(request.limit >= schema.properties.limit.minimum && request.limit <= schema.properties.limit.maximum);
  assert.equal(typeof request.only_eligible, 'boolean');
  for (const [view, weight] of Object.entries(request.weights)) {
    assert.ok(motor.$defs.ViewId.enum.includes(view));
    assert.ok(weight >= schema.properties.weights.additionalProperties.minimum);
  }
});
test('the client talks to the documented endpoints', () => {
  const documented = api['x-endpoints'].map(e => `${e.method} ${e.path}`);
  assert.ok(documented.includes('POST /api/similarity/search'));
  assert.ok(documented.includes('GET /api/similarity/references'));
  const source = fs.readFileSync(path.join(base, 'src/data/similarityApi.ts'), 'utf8');
  assert.ok(source.includes('/api/similarity/search'));
});
test('the client timeout and debounce follow the contract rules', () => {
  const { SEARCH_TIMEOUT_MS, DEBOUNCE_MS } = load('src/data/similarityApi.ts');
  assert.equal(SEARCH_TIMEOUT_MS, 30000);
  assert.ok(DEBOUNCE_MS >= 200 && DEBOUNCE_MS <= 500);
  assert.ok(api['x-client-rules'].some(rule => rule.includes('30 s')));
});
