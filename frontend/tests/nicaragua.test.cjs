const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const base = path.resolve(__dirname, '..');
function load(relative) {
  const filename = path.resolve(base, relative);
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  vm.runInNewContext(code, { module, exports: module.exports, Math, Number, Infinity }, { filename });
  return module.exports;
}
const m = load('src/features/nicaragua/model.ts');
// Los arrays creados dentro del contexto vm tienen otro prototipo: se comparan copias planas.
const plain = value => JSON.parse(JSON.stringify(value));

const site = { id: 'cerro-negro', name: 'Cerro Negro', longitude: -86.702, latitude: 12.506, sources: [] };
function fixture() {
  const columns = ['region_id', 'source', 'longitude', 'latitude', 'qa_status', 'eligibility', 'volcano_id', 'volcano_km', 'volcanic', 'water_dominated', 'bare_or_sparse_fraction'];
  const rows = [
    ['a', 'grid', -86.70, 12.506, 'rankable', 'excluded_dense_canopy', '344070', 0.2, true, false, 0.3],  // en Cerro Negro
    ['b', 'grid', -86.60, 12.45, 'rankable', 'excluded_dense_canopy', '344090', 6, true, false, null],
    ['c', 'grid', -86.59, 12.45, 'rankable', 'excluded_dense_canopy', '344090', 6, true, false, null],  // a 1 km de b
    ['d', 'atlas', -85.0, 13.5, 'rankable', 'excluded_dense_canopy', '344090', 120, false, false, null],
    ['e', 'grid', -86.30, 12.10, 'rankable', 'excluded_permanent_water', '344092', 3, true, true, null],
  ];
  return {
    windows: { columns, rows },
    volcanoes: { volcanoes: [{ id: '344070', name: 'Negro, Cerro' }, { id: '344090', name: 'Momotombo' }] },
    rankings: { jezero: { score: [0.05, 0.1, 0.11, 0.01, null], coverage: [1, 1, 1, 1, null], global_rank: [10, 20, 22, 2, null] } },
    references: [{ id: 'haworth-fondo' }, { id: 'jezero' }],
  };
}

test('las ventanas se decodifican por columna', () => {
  const w = m.decodeWindows(fixture());
  assert.equal(w.length, 5);
  assert.equal(w[1].region_id, 'b');
  assert.equal(w[1].index, 1);
  assert.equal(w[4].water_dominated, true);
});

test('el ámbito volcánico excluye ventanas lejanas y las sin distancia', () => {
  const d = fixture(), w = m.decodeWindows(d);
  assert.deepEqual(plain(m.rankWindows(d, w, 'jezero', 'volcanic').map(r => r.region_id)), ['a', 'b', 'c']);
  const all = m.rankWindows(d, w, 'jezero', 'all');
  assert.deepEqual(plain(all.map(r => r.region_id)), ['d', 'a', 'b', 'c']);
  assert.deepEqual(plain(all.map(r => r.rank)), [1, 2, 3, 4]);
  assert.equal(all[0].level, 4);
  assert.ok(all[3].level < all[0].level);
  assert.equal(m.rankWindows(d, w, 'desconocida', 'all').length, 0);
});

test('los lugares propuestos omiten sitios conocidos y ventanas solapadas', () => {
  const d = fixture(), w = m.decodeWindows(d);
  const found = m.discoveries(m.rankWindows(d, w, 'jezero', 'volcanic'), [site]);
  assert.deepEqual(plain(found.map(r => r.region_id)), ['b']);
});

test('textos de puesto mundial, lugar y cobertura', () => {
  const d = fixture(), w = m.decodeWindows(d);
  assert.equal(m.worldShare(10, 1000), 'top 1 % de la Tierra');
  assert.equal(m.worldShare(4, 1000), 'top 0,4 % de la Tierra');
  assert.equal(m.worldShare(null, 1000), 'sin puesto mundial');
  assert.equal(m.placeText(d, w[0]), 'Cumbre de Cerro Negro');
  assert.equal(m.placeText(d, w[1]), 'A 6 km de Momotombo');
  assert.equal(m.coverText(w[0]), 'Bosque denso · 30 % suelo desnudo');
  assert.equal(m.defaultReference(d), 'jezero');
});

test('el precálculo publicado tiene rankings alineados con las ventanas', { skip: !fs.existsSync(path.join(base, 'public', m.DATA_URL)) }, () => {
  const d = JSON.parse(fs.readFileSync(path.join(base, 'public', m.DATA_URL), 'utf8'));
  const w = m.decodeWindows(d);
  for (const id of Object.keys(d.rankings)) assert.equal(d.rankings[id].score.length, w.length, id);
  const ranked = m.rankWindows(d, w, m.defaultReference(d), 'volcanic');
  assert.ok(ranked.length > 500);
  assert.ok(m.discoveries(ranked, d.known_sites.sites).length >= 10);
});
