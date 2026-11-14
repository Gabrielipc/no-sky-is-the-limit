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
  vm.runInNewContext(code, { module, exports: module.exports, URLSearchParams, fetch: (...args) => globalThis.fetch(...args), require: name => name.startsWith('.') ? load(path.relative(base, path.resolve(path.dirname(filename), name + '.ts'))) : localRequire(name) }, { filename });
  cache.set(filename, module.exports);
  return module.exports;
}
const { parseState } = load('src/app/useAtlasState.ts');
test('Jezero links restore coverage and reject unknown indicator IDs', () => {
  assert.equal(parseState('?crismLayer=coverage').state.crismLayer, 'coverage');
  const bad = parseState('?crismLayer=invalid');
  assert.equal(bad.adjusted, true);
  assert.equal(bad.state.crismLayer, 'OLINDEX3');
});
const { sortFeatures, comparisonFinding } = load('src/data/adapters.ts');
const { fmt, percent } = load('src/domain/analysis.ts');
const { surfaceFmt } = load('src/domain/dimensions.ts');
const feature = (id, slope, relief, passes = true) => ({ properties: { id, passes_filter: passes, metric: { slope_wasserstein_deg: slope, candidate_minus_reference_relief_m: relief } } });

test('regional ordering considers the entire filtered set, absolute relief and deterministic ties', () => {
  const rows = Array.from({ length: 24 }, (_, i) => feature(String(i).padStart(3, '0'), 24 - i, i === 23 ? 0 : -100 + i));
  assert.equal(sortFeatures(rows, 'abs_relief_difference')[0].properties.id, '023');
  assert.equal(sortFeatures(rows, 'slope_distance')[0].properties.id, '023');
  assert.equal(rows[0].properties.id, '000');
  assert.deepEqual(Array.from(sortFeatures([feature('b', 1, -2), feature('a', 1, 2)], 'abs_relief_difference'), f => f.properties.id), ['a', 'b']);
});
test('zero is a real measurement, missing comparisons are last, exclusions remain identifiable', () => {
  const rows = [feature('null', null, null), feature('zero', 0, 0), feature('one', 1, -1), feature('excluded', 0, 0, false)];
  for (const sort of ['slope_distance', 'abs_relief_difference']) assert.deepEqual(Array.from(sortFeatures(rows, sort), f => f.properties.id), ['zero', 'one', 'null', 'excluded']);
  assert.equal(fmt(null), 'Sin evaluar'); assert.equal(fmt(0, ' m'), '0 m');
  assert.equal(percent(.95), '95 %'); assert.equal(percent(.0846), '8,46 %'); assert.equal(percent(null), 'Sin evaluar');
});
test('links reject incompatible scales, unknown modes, arbitrary identifiers and cross-area selections', () => {
  const parsed = parseState('?view=global&cell=300&regionalCell=60&layer=unknown&profile=validated&excluded=maybe&area=utah&regionalSite=atacama-001-001&sensitivitySite=../../secret');
  assert.equal(parsed.adjusted, true); assert.equal(parsed.state.view, 'compare'); assert.equal(parsed.state.cell, 60); assert.equal(parsed.state.regionalCell, 300); assert.equal(parsed.state.regionalSite, '');
});
test('links preserve distinct experiments and an unavailable sample member without silently substituting it', () => {
  const { state, adjusted } = parseState('?view=sensitivity&site=earth-atacama&cell=120&area=mojave&regionalSite=control-mojave&sensitivitySite=utah-003-001&sensitivityCell=600&excluded=true');
  assert.equal(adjusted, false); assert.equal(state.site, 'earth-atacama'); assert.equal(state.cell, 120); assert.equal(state.regionalSite, 'control-mojave'); assert.equal(state.sensitivitySite, 'utah-003-001'); assert.equal(state.sensitivityCell, 600); assert.equal(state.excluded, true);
});
test('multidimensional links preserve metric, candidate and scale', () => {
  const { state, adjusted } = parseState('?view=dimensions&surfaceMetric=laplacian&site=earth-atacama&cell=120');
  assert.equal(adjusted, false); assert.equal(state.view, 'dimensions');
  assert.equal(state.surfaceMetric, 'laplacian'); assert.equal(state.site, 'earth-atacama'); assert.equal(state.cell, 120);
  const invalid = parseState('?view=dimensions&surfaceMetric=mobility');
  assert.equal(invalid.adjusted, true); assert.equal(invalid.state.surfaceMetric, 'roughness_rms');
});
test('small curvature measurements remain distinct from exact zero and missing values', () => {
  assert.notEqual(surfaceFmt(4.38e-7, ' m⁻¹', 5), surfaceFmt(0, ' m⁻¹', 5));
  assert.match(surfaceFmt(4.38e-7, ' m⁻¹', 5, true), /^\+/);
  assert.match(surfaceFmt(-4.38e-7, ' m⁻¹', 5), /^-/);
  assert.equal(surfaceFmt(null), 'Sin evaluar');
});
test('findings distinguish a smaller relief from resemblance and handle a zero reference', () => {
  assert.match(comparisonFinding('Utah', { relief_p95_p5_m: 27.38 }, { relief_p95_p5_m: 54.63 }, true), /mitad/);
  assert.match(comparisonFinding('Atacama', { relief_p95_p5_m: 200 }, { relief_p95_p5_m: 54.63 }, false), /más distintas/);
  assert.doesNotMatch(comparisonFinding('X', { relief_p95_p5_m: 0 }, { relief_p95_p5_m: 0 }, true), /Infinity|NaN/);
});

const { getJSON } = load('src/data/api.ts');
test('requests preserve the abort signal and explain malformed data without exposing HTML', async t => {
  const controller = new AbortController();
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(options.signal, controller.signal);
    return { ok: true, json: async () => { throw new SyntaxError('Unexpected <html>'); } };
  });
  await assert.rejects(getJSON('/analysis/terrain.json', controller.signal), /formato esperado/);
});
test('service failures retain the reviewed-evidence explanation and never return stale data', async t => {
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, json: async () => ({ detail: 'La evidencia falta o cambió.' }) }));
  await assert.rejects(getJSON('/api/scenarios/relieve-regional/comparison', new AbortController().signal), /La evidencia falta o cambió/);
});

const { mineralSelection, mineralColor } = load('src/domain/minerals.ts');
test('mineral filters preserve the window denominator, missing data, zero no-match and group IDs', () => {
  const group = { ids: [2, 2, 3, 0, null, 3], fit: [.4, .8, .9, null, null, .9], usable: [true, true, true, false, false, true], classes: [{id:2},{id:3}] };
  const inside = [true,true,true,true,true,false], slopes = [0,20,null,0,0,0];
  const all = mineralSelection(group, inside, slopes, 0, null);
  assert.equal(all.total, 5); assert.equal(all.acceptedCount, 3);
  assert.equal(all.counts.find(c=>c.id===2).fraction, .4);
  const filtered = mineralSelection(group, inside, slopes, .5, 10);
  assert.equal(filtered.total, 5); assert.equal(filtered.acceptedCount, 0);
  assert.equal(mineralSelection(group, inside, slopes, .4, 0).acceptedCount, 1);
  assert.equal(mineralColor(2), mineralColor(2)); assert.notEqual(mineralColor(2), mineralColor(3));
});
test('mineral links preserve filters, clamp non-step fit values and reject incompatible parameters', () => {
  const valid = parseState('?view=dimensions&dimensionSection=minerals&mineralGroup=2&mineralLayer=uncertainty&mineralId=129&mineralFit=0.45&mineralMaxSlope=10');
  assert.equal(valid.adjusted, false); assert.equal(valid.state.mineralGroup, 2); assert.equal(valid.state.mineralId, 129); assert.equal(valid.state.mineralFit, .45);
  const bad = parseState('?mineralGroup=3&mineralFit=0.43&mineralMaxSlope=80&mineralId=-1');
  assert.equal(bad.adjusted, true); assert.equal(bad.state.mineralFit, .45); assert.equal(bad.state.mineralMaxSlope,90); assert.equal(bad.state.mineralId,0);
});
