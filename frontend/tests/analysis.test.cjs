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
  vm.runInNewContext(code, { module, exports: module.exports, URL, URLSearchParams, createImageBitmap:(...args)=>globalThis.createImageBitmap(...args), fetch: (...args) => globalThis.fetch(...args), require: name => name.startsWith('.') ? load(path.relative(base, path.resolve(path.dirname(filename), name + '.ts'))) : localRequire(name) }, { filename });
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
  assert.equal(parsed.adjusted, true); assert.equal(parsed.state.view, 'unified'); assert.equal(parsed.state.cell, 60); assert.equal(parsed.state.regionalCell, 300); assert.equal(parsed.state.regionalSite, '');
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

const surface = load('src/features/surface/terrain.ts');
test('surface links select real sites and reject unknown destinations', () => {
  const parsed = parseState('?view=surface&surfaceSite=earth-atacama');
  assert.equal(parsed.adjusted,false); assert.equal(parsed.state.view,'surface');
  assert.equal(parsed.state.surfaceSite,'earth-atacama');
  assert.equal(parseState('?surfaceSite=unknown').adjusted,true);
});
test('grayscale DEM decoding preserves negative heights, zero and missing samples', () => {
  const site = {width:2,height:2,offset_m:-100,scale_m:1,nodata:255};
  const h=surface.decodeGray(new Uint8ClampedArray([0,0,0,255,100,100,100,255,254,254,254,255,255,255,255,255]),site);
  assert.equal(h[0],-100); assert.equal(h[1],0); assert.equal(h[2],154); assert.ok(Number.isNaN(h[3]));
  assert.throws(()=>surface.decodeGray(new Uint8ClampedArray(4),site));
});
test('MOLA radius decoding keeps metre units and negative elevations', () => {
  const h=surface.decodeMola(new Uint8ClampedArray([128,0,0,255,127,255,0,255,129,0,0,255]));
  assert.deepEqual(Array.from(h),[0,-1,256]);
});
test('displaced plane has north-up coordinates, outward faces, UVs and nodata holes', () => {
  const site={width:2,height:2,cell_m:30,center_m:10};
  const a=surface.meshArrays(new Float32Array([10,11,12,13]),site,2);
  assert.deepEqual(Array.from(a.positions),[-15,15,0,15,15,2,-15,-15,4,15,-15,6]);
  assert.deepEqual(Array.from(a.uv),[0,1,1,1,0,0,1,0]);
  assert.deepEqual(Array.from(a.indices),[0,2,1,1,2,3]);
  const hole=surface.meshArrays(new Float32Array([NaN,11,12,13]),site,1);
  assert.deepEqual(Array.from(hole.indices),[1,2,3]);
  assert.throws(()=>surface.meshArrays(new Float32Array(4),site,NaN));
});
test('external layer URLs permit services and reject executable schemes and embedded credentials', () => {
  assert.equal(surface.layerURL('/tiles/tileset.json','https://atlas.test/'),'https://atlas.test/tiles/tileset.json');
  for(const url of ['javascript:alert(1)','data:text/html,x','https://user:password@example.test','http://example.test']) {
    assert.throws(()=>surface.layerURL(url,'https://atlas.test/'));
  }
});

const journey = load('src/app/useAtlasState.ts');
const motor = load('src/features/simulation/model.ts');
const motorSource = load('src/features/simulation/source.ts');
const example = JSON.parse(fs.readFileSync(path.resolve(base,'public/simulation/jezero.json'),'utf8'));
test('journey links round-trip reference, candidate, release, method, map scale and atlas weights',()=>{
  const state={...journey.defaults,view:'compare',reference:'haworth-fondo',regionId:example.results[0].region_id,release:'etl-30m-r2',method:'engine',engineSource:'demo',surfaceMode:'mesh',exaggeration:2.5,atlasSlope:0};
  const parsed=journey.parseState(journey.stateQuery(state));
  assert.equal(parsed.adjusted,false);
  for(const key of ['view','reference','regionId','release','method','engineSource','surfaceMode','exaggeration','atlasSlope'])assert.equal(parsed.state[key],state[key]);
  assert.equal(journey.parseState('?view=compare').state.method,'local');
  const bad=journey.parseState('?reference=venus&regionId=../../etc&release=../x&exaggeration=8&atlasSlope=-2');
  assert.equal(bad.adjusted,true);assert.equal(bad.state.regionId,'');assert.equal(bad.state.exaggeration,1);
});
test('old motor examples adapt coverage without changing distances, order, eligibility or absent features',()=>{
  const data=motor.adaptSearch(example);
  assert.equal(data.results[0].score,example.results[0].score);
  assert.equal(data.results[0].scenario_eligibility,'excluded_permanent_water');
  assert.equal(data.views.escabrosidad.coverage_fraction,1);
  assert.equal(data.views.espectral.coverage_fraction,undefined);
  assert.equal(motor.selectedMatch(data,'missing-window'),undefined);
  assert.equal(motor.featureRows(data,data.results[0])[0].reference,example.reference.features.relief_p95_p05_m.value);
  assert.throws(()=>motor.adaptSearch({...example,results:[{...example.results[0],score:NaN}]}));
});
test('missing similarity service falls back to labelled repository evidence, independent of release',async t=>{
  const urls=[];
  t.mock.method(globalThis,'fetch',async url=>{urls.push(url);return urls.length===1?{ok:false,status:404}:{ok:true,json:async()=>example};});
  const result=await motorSource.loadSearch('jezero','release-real','auto','/',new AbortController().signal);
  assert.equal(result.source,'demo');assert.equal(result.version,undefined);
  assert.match(result.notice,/No está vinculado/);assert.match(urls[0],/version=release-real/);
  assert.equal(urls[1],'/simulation/jezero.json');
});
test('published responses must confirm requested identity and are never silently replaced when invalid',async t=>{
  t.mock.method(globalThis,'fetch',async()=>({ok:true,json:async()=>({...example,version:'r2'})}));
  const good=await motorSource.loadSearch('jezero','r2','auto','/',new AbortController().signal);
  assert.equal(good.source,'published');assert.equal(good.version,'r2');
  await assert.rejects(motorSource.loadSearch('jezero','wrong-release','auto','/',new AbortController().signal),/publicación solicitada/);
  await assert.rejects(motorSource.loadSearch('haworth-fondo','','auto','/',new AbortController().signal),/otra referencia/);
});
test('explicit demo bypasses service, preserves warnings and reports references without examples',async t=>{
  const urls=[];t.mock.method(globalThis,'fetch',async url=>{urls.push(url);return {ok:true,json:async()=>example};});
  const result=await motorSource.loadSearch('jezero','','demo','/',new AbortController().signal);
  assert.equal(urls.length,1);assert.equal(urls[0],'/simulation/jezero.json');assert.deepEqual(Array.from(result.data.warnings),example.warnings);
  await assert.rejects(motorSource.loadSearch('de-gerlache-cresta','','demo','/',new AbortController().signal),/todavía no tiene/);
});
test('metric rulers fit their viewport and profile uses exactly the mesh centre row',()=>{
  const scale=surface.metricScale(2,120);assert.equal(scale.distance,200);assert.equal(scale.pixels,100);
  assert.equal(surface.metricScale(NaN),null);
  const row=surface.terrainProfile(new Float32Array([0,1,2,10,NaN,12,20,21,22]),{width:3,height:3,cell_m:30});
  assert.deepEqual(Array.from(row,r=>r.distance),[0,30,60]);assert.equal(row[0].height,10);assert.ok(Number.isNaN(row[1].height));
  assert.deepEqual(Array.from(surface.elevationColor(0,0,100)),[43,29,20]);assert.deepEqual(Array.from(surface.elevationColor(100,0,100)),[253,241,214]);
});

test('service outage still opens evidence, while HTTP authorization errors stay explicit',async t=>{
  let count=0;t.mock.method(globalThis,'fetch',async()=>++count===1?{ok:false,status:502}:{ok:true,json:async()=>example});
  const result=await motorSource.loadSearch('jezero','','auto','/',new AbortController().signal);
  assert.equal(result.source,'demo');assert.match(result.notice,/no está disponible/);
  t.mock.method(globalThis,'fetch',async()=>({ok:false,status:401}));
  await assert.rejects(motorSource.loadSearch('jezero','','auto','/',new AbortController().signal),/401/);
});
test('tiny nonzero motor distances remain distinct from exact zero',()=>{
  assert.notEqual(motor.distance(1e-8),motor.distance(0));
  assert.equal(motor.number(null),'Sin datos');
});
test('packaged CTX preview keeps the exact tile footprint and image identity',()=>{
  const crypto=require('node:crypto');
  const m=JSON.parse(fs.readFileSync(path.resolve(base,'public/surface/regional-preview.json'),'utf8'));
  const bytes=fs.readFileSync(path.resolve(base,'public/surface',m.file));
  assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),m.sha256);
  assert.equal(bytes.readUInt32BE(16),m.width);assert.equal(bytes.readUInt32BE(20),m.height);
  const tiles=m.sources.map(s=>s.url.split('/').slice(-3).map(Number));
  assert.equal(new Set(m.sources.map(s=>s.url)).size,9);
  assert.deepEqual(m.rectangle_degrees,[-180+Math.min(...tiles.map(t=>t[2]))*180/256,90-(Math.max(...tiles.map(t=>t[1]))+1)*180/256,-180+(Math.max(...tiles.map(t=>t[2]))+1)*180/256,90-Math.min(...tiles.map(t=>t[1]))*180/256]);
  assert.ok(m.rectangle_degrees[0]<77.41&&m.rectangle_degrees[2]>77.41&&m.rectangle_degrees[1]<18.49&&m.rectangle_degrees[3]>18.49);
});
test('explicitly absent reference values are not replaced by a raw value from another comparison domain',()=>{
  const row={...example.results[0],views:{termica:{distance:null,available:false,weight:0,features:{relief_p95_p05_m:{candidate:5,reference:null,z_delta:0,share:0}}}}};
  assert.equal(motor.featureRows(example,row)[0].reference,null);
});
test('environment context keeps measured zero distinct from pending, null and out-of-coverage values',()=>{
  assert.equal(motor.contextValue(0,'measured','mm/año'),'0 mm/año');
  assert.equal(motor.contextValue(null,'measured','mm/año'),'Sin dato publicado');
  assert.equal(motor.contextValue(1,'on_demand_fetchable','fracción'),'Pendiente de procesar');
  assert.equal(motor.contextValue(null,'unobserved_by_product','fracción'),'Fuera de la cobertura del producto');
});
test('malformed successful service responses and cancelled queries never fall back to a different dataset',async t=>{
  let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;return {ok:true,json:async()=>{throw new TypeError('Malformed response');}};});
  await assert.rejects(motorSource.loadSearch('jezero','','auto','/',new AbortController().signal),/Malformed response/);
  assert.equal(calls,1);
  const controller=new AbortController();controller.abort();
  t.mock.method(globalThis,'fetch',async()=>{throw new Error('cancelled');});
  await assert.rejects(motorSource.loadSearch('jezero','','auto','/',controller.signal),/cancelled/);
});

const unified=load('src/features/unified/terrainModel.ts');
test('unified study levels retain the complete scientific pair and default to true vertical scale',()=>{
  const {state}=parseState('?reference=haworth-fondo&regionId=utm-ups-v1-10000-32741-249-59&release=reviewed-v1&visualLayer=slope');
  assert.equal(state.view,'unified');assert.equal(state.exaggeration,1);
  const {stateQuery}=load('src/app/useAtlasState.ts');
  for(const surfaceMode of ['space','regional','mesh']){
    const restored=parseState(stateQuery({...state,surfaceMode})).state;
    for(const key of ['reference','regionId','release','method','visualLayer'])assert.equal(restored[key],state[key]);
    assert.equal(restored.surfaceMode,surfaceMode);
  }
});
test('visual DEM selection requires both exact identity and centre, including distinct regional and local Jezero sources',()=>{
 const catalog=JSON.parse(fs.readFileSync(path.join(base,'public/surface/unified/catalog.json')));
 assert.equal(unified.exactSite(catalog,'haworth-fondo',-5,-87.45,'local').body,'Moon');
 assert.equal(unified.exactSite(catalog,'haworth-fondo',-68.7,-88.71,'local'),undefined);
 assert.equal(unified.exactSite(catalog,'de-gerlache-cresta',-68.7,-88.71,'local').id,'de-gerlache-cresta');
 assert.equal(unified.exactSite(catalog,'unknown',-5,-87.45,'local'),undefined);
 assert.match(unified.exactSite(catalog,'jezero',77.41,18.49,'regional').source,/MOLA/);
 assert.match(unified.exactSite(catalog,'jezero',77.41,18.49,'local').source,/HiRISE/);
});
test('shared visual ranges align relative datums and common slope support while keeping nodata gaps',()=>{
 const site={width:3,height:3,cell_m:30,center_m:1000};
 const a={site,heights:new Float32Array([970,1000,1030,970,1000,1030,970,1000,1030])};
 const b={site:{...site,center_m:-3000},heights:new Float32Array([-3060,-3000,-2940,-3060,-3000,-2940,-3060,-3000,-2940])};
 assert.deepEqual(Array.from(unified.sharedRange([a,b],'elevation')),[-60,60]);
 assert.equal(unified.visualValues(a,'slope')[4],45);
 assert.ok(Math.abs(unified.sharedRange([a,b],'slope')[1]-63.43495)<.001);
 a.heights[3]=NaN;assert.ok(Number.isNaN(unified.visualValues(a,'slope')[4]));
 assert.equal(unified.visualValues(a,'elevation')[4],0);
 assert.deepEqual(Array.from(unified.sharedRange([undefined,undefined],'elevation')),[0,1]);
});
test('polar DEM offsets follow metre distances without longitude stretching or reversed north',()=>{
 const radius=1737400,lon=-68.7,lat=-88.71;
 const north=unified.offsetDegrees(lon,lat,0,900,radius),east=unified.offsetDegrees(lon,lat,900,0,radius);
 assert.ok(north[1]>lat);assert.ok(east[0]>lon);
 function arc([a,b]){const p=lat*Math.PI/180,q=b*Math.PI/180,d=(a-lon)*Math.PI/180;return 2*radius*Math.asin(Math.sqrt(Math.sin((q-p)/2)**2+Math.cos(p)*Math.cos(q)*Math.sin(d/2)**2));}
 assert.ok(Math.abs(arc(north)-900)<1e-5);assert.ok(Math.abs(arc(east)-900)<1e-5);
});
test('browser terrain catalog contains calibrated DEMs for exact demonstration centres and true lunar sites',()=>{
 const crypto=require('node:crypto');
 const catalog=JSON.parse(fs.readFileSync(path.join(base,'public/surface/unified/catalog.json')));
 for(const reference of ['jezero','haworth-fondo'])for(const row of JSON.parse(fs.readFileSync(path.join(base,`public/simulation/${reference}.json`))).results){
  const site=unified.exactSite(catalog,row.region_id,row.longitude,row.latitude,'local');assert.ok(site,row.region_id);assert.equal(site.window_m,1800);assert.equal(site.cell_m,30);
 }
 for(const entry of Object.values(catalog.sites))for(const [kind,s] of Object.entries(entry)){
  assert.equal((s.width-1)*s.cell_m,s.window_m);assert.ok(s.scale_m>0);assert.equal(s.nodata,255);
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(base,'public/surface',s.heightmap))).digest('hex'),s.sha256);
  assert.equal(s.cell_m,kind==='local'?30:150);
 }
});
test('unselected result framing respects spherical geography at the date line',()=>{
 const [lon,lat]=unified.candidateFocus([{longitude:179,latitude:30},{longitude:-179,latitude:30}]);
 assert.ok(Math.abs(Math.abs(lon)-180)<1e-6);assert.ok(lat>30&&lat<30.01);
 assert.deepEqual(Array.from(unified.candidateFocus([])),[0,10]);
});
test('map clusters can be expanded by keyboard while a selected location remains separate',()=>{
 const points=[{id:'a',name:'1',x:10,y:10},{id:'b',name:'2',x:20,y:20},{id:'c',name:'3',x:200,y:200}];
 const groups=unified.groupMapPoints(points,'c');
 assert.deepEqual(Array.from(groups[0].members),['a','b']);assert.deepEqual(Array.from(groups[1].members),['c']);
 const selected=unified.groupMapPoints(points,'a');assert.deepEqual(Array.from(selected.at(-1).members),['a']);assert.equal(selected.length,3);
 const separated=unified.groupMapPoints([{...points[0],x:0},{...points[1],x:100}], '');assert.equal(separated.length,2);
});
const pixelReader=load('src/features/surface/pixels.ts');
test('a successful SPA HTML fallback is never decoded or displayed as a DEM',async t=>{
 t.mock.method(globalThis,'fetch',async()=>({ok:true,headers:{get:()=> 'text/html'}}));
 await assert.rejects(pixelReader.pixels('/missing.png',new AbortController().signal,61,61),/imagen DEM válida/);
});
test('invalid image data reports a Spanish DEM error, while cancellation retains its identity',async t=>{
 t.mock.method(globalThis,'fetch',async()=>({ok:true,headers:{get:()=> 'image/png'},blob:async()=>new Blob(['invalid'])}));
 const previousBitmap=globalThis.createImageBitmap;globalThis.createImageBitmap=async()=>{throw Error('Cannot decode the data');};t.after(()=>{if(previousBitmap)globalThis.createImageBitmap=previousBitmap;else delete globalThis.createImageBitmap;});
 await assert.rejects(pixelReader.pixels('/broken.png',new AbortController().signal,61,61),/No se pudo decodificar/);
 const c=new AbortController();c.abort();const abort=Error('cancelled');
 t.mock.method(globalThis,'fetch',async()=>{throw abort;});
 await assert.rejects(pixelReader.pixels('/cancelled.png',c.signal,61,61),error=>error===abort);
});
test('the bare address opens the landing; the scientific mode follows the specialised analyses',()=>{
  const {parseState,stateQuery}=load('src/app/useAtlasState.ts');
  assert.equal(parseState('').state.view,'landing');
  assert.equal(parseState('').state.science,false);
  assert.equal(parseState('?view=unified').state.science,false);
  assert.equal(parseState('?view=world').state.science,true);
  assert.equal(parseState('?view=world&science=false').state.science,false);
  const landing=parseState(stateQuery({...parseState('').state,reference:'haworth-fondo'}));
  assert.equal(landing.state.view,'landing');assert.equal(landing.state.reference,'haworth-fondo');
});

test('automatic marker framing accounts for nearby points, narrow panels and the date line', () => {
 const center = {longitude: 179, latitude: 0};
 const alone = unified.markerCameraRange(center, [center], 1000, 1);
 const nearby = [{longitude: -179, latitude: 0}];
 assert.ok(unified.markerCameraRange(center, nearby, 1000, 1) >= alone);
 const spread = [{longitude: -177, latitude: 0}];
 assert.ok(unified.markerCameraRange(center, spread, 1000, .5) > unified.markerCameraRange(center, spread, 1000, 1));
 assert.equal(unified.markerCameraRange(center, [{longitude: 0, latitude: 0}], 1000, 1), alone);
 assert.equal(unified.markerCameraRange(center, [{longitude: -151, latitude: 0}], 1000, 1), alone);
 assert.ok(unified.markerCameraRange(center, nearby, 1000, 1) > alone);
 const polar = {longitude: -5, latitude: -87.45};
 assert.ok(Number.isFinite(unified.markerCameraRange(polar, [{longitude: -68.7, latitude: -88.71}], 1737400, 1)));
});
