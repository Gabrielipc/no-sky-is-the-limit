import {useResource} from '../../data/api';
import {asset} from './assets';
type Source={product_id:string;version:string;vertical_reference:string;observation_dates:string[];native_step_at_center_m:number[];url:string;limitations:string[]};
export function SourceContext({siteId}:{siteId:string}) {
  const resource=useResource<{sites:Record<string,Source>}>(asset('source-context.json'));
  const source=resource.data?.sites[siteId];
  if(resource.error)return <p role="alert">No se pudieron cargar los metadatos de la fuente. <button onClick={resource.retry}>Reintentar</button></p>;
  if(!source)return <p role="status">Cargando datum y resolución nativa…</p>;
  return <div className="surface-source-context"><span className="surface-step">SOPORTE DE LA MALLA LOCAL</span><dl><div><dt>Espaciado nativo en el centro</dt><dd>{source.native_step_at_center_m.map(v=>v.toLocaleString('es',{maximumFractionDigits:2})).join(' × ')} m</dd></div><div><dt>Datum de las alturas originales</dt><dd>{source.vertical_reference}</dd></div><div><dt>Periodo de observación</dt><dd>{source.observation_dates.join(' · ')}</dd></div><div><dt>Producto y versión</dt><dd><a href={source.url} target="_blank" rel="noreferrer">{source.product_id} ↗</a> · {source.version}</dd></div></dl><p>La separación entre muestras del visor se indica en el panel lateral. Reproyectar o remuestrear no mejora la resolución efectiva del instrumento.</p><ul>{source.limitations.map(l=><li key={l}>{l}</li>)}</ul></div>;
}
