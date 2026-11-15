export const references = [
  {id:'jezero',name:'Jezero',detail:'Marte · abanico sedimentario',body:'Mars',longitude:77.41,latitude:18.49},
  {id:'haworth-fondo',name:'Haworth',detail:'Luna · fondo polar',body:'Moon',longitude:-5,latitude:-87.45},
  {id:'de-gerlache-cresta',name:'De Gerlache',detail:'Luna · cresta polar',body:'Moon',longitude:-68.7,latitude:-88.71},
] as const;
export type ReferenceId = typeof references[number]['id'];
export type Feature = {candidate:number;reference?:number|null;z_delta:number;share:number};
export type ResultView = {distance:number|null;weight:number;available:boolean;pool_percentile?:number;features?:Record<string,Feature>;component?:number;posterior?:number};
export type Match = {rank:number;region_id:string;longitude:number;latitude:number;scenario_eligibility:string;score:number;score_low:number;score_high:number;coverage:number;missing_views:string[];views:Record<string,ResultView>};
export type ViewReport = {weight:number;kind:'metric'|'gmm';status:string;reason?:string|null;candidates_with_view?:number;coverage_fraction?:number;fit_population?:{mode:string}};
export type SearchResponse = {
  engine_id:string;model_fitted_at:string;status:string;version?:string;
  reference:{id:string;name:string;body:string;features:Record<string,{value?:number|null;earth_percentile?:number;outside_earth_range?:boolean;reason?:string}>};
  weights_requested:Record<string,number>;weights_effective:Record<string,number>;views:Record<string,ViewReport>;
  warnings:string[];results:Match[];candidates_in_pool:number;candidates_ranked:number;only_eligible:boolean;fusion:string;profile:string;
};
export type LoadedSearch = {data:SearchResponse;source:'published'|'demo';notice:string;version?:string};
export const viewNames:Record<string,string> = {escabrosidad:'Escabrosidad',forma_hipsometrica:'Forma del relieve',organizacion:'Organización del terreno',regimen_morfologico:'Familia morfológica',espectral:'Composición espectral',termica:'Propiedades térmicas',radar:'Radar',entorno_superficial:'Entorno superficial',emisividad_cmg:'Emisividad'};
export const features:Record<string,{label:string;unit:string}> = {
  relief_p95_p05_m:{label:'Relieve p95–p5',unit:'m'},slope_240m_p50_deg:{label:'Pendiente mediana · base 240 m',unit:'°'},
  slope_240m_p90_deg:{label:'Pendiente p90 · base 240 m',unit:'°'},roughness_360m_p50_m:{label:'Rugosidad mediana · radio 360 m',unit:'m'},
  hypsometric_integral:{label:'Integral hipsométrica',unit:''},elevation_skew_p95_p05:{label:'Asimetría de elevación',unit:''},
};
export const number = (n:number|null|undefined,digits=3) => n==null||!Number.isFinite(n)?'Sin datos':n.toLocaleString('es',{maximumFractionDigits:digits});
export const pct = (n:number|null|undefined) => n==null?'Sin datos':`${number(n*100,1)} %`;
export const distance = (n:number|null|undefined) => n==null?'Sin datos':n!==0&&Math.abs(n)<0.000001?n.toExponential(2).replace('.',','):n.toLocaleString('es',{maximumFractionDigits:6});
export const signed = (n:number|null|undefined) => n==null?'Sin datos':`${n>0?'+':''}${number(n,4)}`;
export const location = (r:{latitude:number;longitude:number})=>`${number(r.latitude,3)}°, ${number(r.longitude,3)}°`;
export const eligibility = (status:string) => ({excluded_permanent_water:'Excluida: agua permanente',excluded_dense_canopy:'Excluida: vegetación densa',pending_on_demand_cover_check:'Cobertura pendiente de comprobar',eligible_arid_exposed:'Cumple el filtro árido'}[status] || status || 'Elegibilidad sin información');
export function viewReason(view:ViewReport) {
  if(view.status==='not_fitted')return 'Sin datos para ajustar esta dimensión todavía.';
  if(view.status==='reference_missing')return 'La referencia no tiene esta dimensión.';
  if(view.status==='no_candidate_coverage')return 'Ninguna candidata tiene cobertura en esta dimensión.';
  return view.reason || 'Disponible en el cálculo publicado.';
}
/** Adapt only fields whose meaning is recoverable from the old example. Never infer measurements. */
export function adaptSearch(raw:unknown):SearchResponse {
  const d=raw as SearchResponse;
  if(!d||d.engine_id!=='motor-similitud-ml-v1'||!d.reference?.id||!Array.isArray(d.results)||!d.views||!d.weights_requested||!d.weights_effective||!Array.isArray(d.warnings))throw new Error('La respuesta no corresponde al contrato del motor de similitud.');
  for(const r of d.results) {
    if(!r||!Number.isInteger(r.rank)||r.rank<1||!r.region_id||!Number.isFinite(r.longitude)||Math.abs(r.longitude)>180||!Number.isFinite(r.latitude)||Math.abs(r.latitude)>90||![r.score,r.score_low,r.score_high,r.coverage].every(n=>Number.isFinite(n)&&n>=0&&n<=1)||r.score_low>r.score_high||!r.views||!Array.isArray(r.missing_views))throw new Error('El motor devolvió una candidata con datos inválidos.');
  }
  return {...d,views:Object.fromEntries(Object.entries(d.views).map(([id,v])=>[id,{...v,coverage_fraction:v.coverage_fraction ?? (d.candidates_in_pool>0&&v.candidates_with_view!=null ? v.candidates_with_view/d.candidates_in_pool:undefined)}]))};
}
/** Only the matching ID can carry over: never silently replace a selected window. */
export function selectedMatch(data:SearchResponse|undefined,id:string) {return id?data?.results.find(r=>r.region_id===id):data?.results[0];}
export function featureRows(data:SearchResponse,row:Match) {
  return Object.entries(row.views).flatMap(([view,v])=>Object.entries(v.features||{}).map(([id,f])=>({view,id,...f,reference:f.reference === undefined ? data.reference.features[id]?.value ?? null : f.reference})));
}

export function contextValue(value:unknown,status:unknown,unit:string) {
  if(status==='measured'&&typeof value==='number'&&Number.isFinite(value))return unit==='fracción'?pct(value):`${number(value)} ${unit}`;
  return ({insufficient_coverage:'Sin dato válido en esta zona',unobserved_by_product:'Fuera de la cobertura del producto',on_demand_fetchable:'Pendiente de procesar'}[String(status)] || 'Sin dato publicado');
}
