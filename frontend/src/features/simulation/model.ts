import {getLang,localized,tr} from '../../i18n/lang';
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
export type LoadedSearch = {data:SearchResponse;source:'published'|'demo'|'live';notice:string;version?:string;queryId?:string;timings?:{engine_ms:number;total_ms:number;cache_hit:boolean}};
export const viewNames:Record<string,string> = localized({escabrosidad:['Escabrosidad','Ruggedness'],forma_hipsometrica:['Forma del relieve','Relief shape'],organizacion:['Organización del terreno','Terrain organisation'],regimen_morfologico:['Familia morfológica','Morphological family'],espectral:['Composición espectral','Spectral composition'],termica:['Propiedades térmicas','Thermal properties'],radar:['Radar','Radar'],entorno_superficial:['Entorno superficial','Surface setting'],emisividad_cmg:['Emisividad','Emissivity']});
const feature = (es:string,en:string,unit:string) => ({get label(){return tr(es,en);},unit});
export const features:Record<string,{label:string;unit:string}> = {
  relief_p95_p05_m:feature('Relieve p95–p5','Relief p95–p5','m'),slope_240m_p50_deg:feature('Pendiente mediana · base 240 m','Median slope · 240 m baseline','°'),
  slope_240m_p90_deg:feature('Pendiente p90 · base 240 m','Slope p90 · 240 m baseline','°'),roughness_360m_p50_m:feature('Rugosidad mediana · radio 360 m','Median roughness · 360 m radius','m'),
  hypsometric_integral:feature('Integral hipsométrica','Hypsometric integral',''),elevation_skew_p95_p05:feature('Asimetría de elevación','Elevation skewness',''),
};
const noData = () => tr('Sin datos','No data');
export const number = (n:number|null|undefined,digits=3) => n==null||!Number.isFinite(n)?noData():n.toLocaleString(getLang(),{maximumFractionDigits:digits});
export const pct = (n:number|null|undefined) => n==null?noData():`${number(n*100,1)}${getLang()==='en'?'':' '}%`;
export const distance = (n:number|null|undefined) => n==null?noData():n!==0&&Math.abs(n)<0.000001?(getLang()==='en'?n.toExponential(2):n.toExponential(2).replace('.',',')):n.toLocaleString(getLang(),{maximumFractionDigits:6});
export const signed = (n:number|null|undefined) => n==null?noData():`${n>0?'+':''}${number(n,4)}`;
export const location = (r:{latitude:number;longitude:number})=>`${number(r.latitude,3)}°, ${number(r.longitude,3)}°`;
const ELIGIBILITY = localized({excluded_permanent_water:['Excluida: agua permanente','Excluded: permanent water'],excluded_dense_canopy:['Excluida: vegetación densa','Excluded: dense vegetation'],pending_on_demand_cover_check:['Cobertura pendiente de comprobar','Land cover not yet checked'],eligible_arid_exposed:['Cumple el filtro árido','Passes the arid filter']});
export const eligibility = (status:string) => (ELIGIBILITY as Record<string,string>)[status] || status || tr('Elegibilidad sin información','No eligibility information');
export function viewReason(view:ViewReport) {
  if(view.status==='not_fitted')return tr('Sin datos para ajustar esta dimensión todavía.','Not enough data to fit this dimension yet.');
  if(view.status==='reference_missing')return tr('La referencia no tiene esta dimensión.','The reference has no data for this dimension.');
  if(view.status==='no_candidate_coverage')return tr('Ninguna candidata tiene cobertura en esta dimensión.','No candidate has coverage in this dimension.');
  return view.reason || tr('Disponible en el cálculo publicado.','Available in the published calculation.');
}
/** Adapt only fields whose meaning is recoverable from the old example. Never infer measurements. */
export function adaptSearch(raw:unknown):SearchResponse {
  const d=raw as SearchResponse;
  if(!d||d.engine_id!=='motor-similitud-ml-v1'||!d.reference?.id||!Array.isArray(d.results)||!d.views||!d.weights_requested||!d.weights_effective||!Array.isArray(d.warnings))throw new Error(tr('La respuesta no corresponde al contrato del motor de similitud.','The response does not match the similarity engine contract.'));
  for(const r of d.results) {
    if(!r||!Number.isInteger(r.rank)||r.rank<1||!r.region_id||!Number.isFinite(r.longitude)||Math.abs(r.longitude)>180||!Number.isFinite(r.latitude)||Math.abs(r.latitude)>90||![r.score,r.score_low,r.score_high,r.coverage].every(n=>Number.isFinite(n)&&n>=0&&n<=1)||r.score_low>r.score_high||!r.views||!Array.isArray(r.missing_views))throw new Error(tr('El motor devolvió una candidata con datos inválidos.','The engine returned a candidate with invalid data.'));
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
  const text:Record<string,string>={insufficient_coverage:tr('Sin dato válido en esta zona','No valid data in this area'),unobserved_by_product:tr('Fuera de la cobertura del producto','Outside the product coverage'),on_demand_fetchable:tr('Pendiente de procesar','Pending processing')};
  return text[String(status)] || tr('Sin dato publicado','No published data');
}
