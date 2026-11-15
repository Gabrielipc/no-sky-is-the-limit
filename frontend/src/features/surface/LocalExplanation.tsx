import { useEffect, useState } from 'react';
import { asset, pixels } from './assets';
import { decodeGray, terrainProfile, type SurfaceSite } from './terrain';

export default function LocalExplanation({site,exaggeration}:{site:SurfaceSite;exaggeration:number}) {
  const [error,setError]=useState('');
  const [samples,setSamples]=useState<ReturnType<typeof terrainProfile>>([]);
  useEffect(()=>{
    const controller=new AbortController();setSamples([]);setError('');
    pixels(asset(site.heightmap),controller.signal,site.width,site.height)
      .then(data=>{if(!controller.signal.aborted)setSamples(terrainProfile(decodeGray(data,site),site));})
      .catch(()=>{if(!controller.signal.aborted)setError('El perfil no está disponible porque no se pudo leer el DEM.');});
    return ()=>controller.abort();
  },[site]);
  const range=site.max_m-site.min_m;
  // This chart has its own labelled vertical axis, independent of the 3D exaggeration.
  const paths:string[]=[];let segment='';
  for(const p of samples){
    if(!Number.isFinite(p.height)){if(segment)paths.push(segment);segment='';continue;}
    segment+=`${segment?'L':'M'}${60+p.distance/site.window_m*730},${142-(p.height-site.min_m)/(range||1)*115} `;
  }
  if(segment)paths.push(segment);
  return <section className="local-explanation" aria-label="Cómo leer el terreno local">
    <div className="local-reading"><p className="surface-eyebrow">QUÉ ESTÁS VIENDO</p><h2>Un recorte de terreno, medido en metros.</h2><p>Cada lado mide <strong>1.800 m</strong>. Entre el punto más bajo y el más alto hay <strong>{range.toLocaleString('es',{maximumFractionDigits:0})} m</strong> de desnivel. A escala real, una superficie extensa puede parecer casi plana.</p><p>{exaggeration===1?'La malla conserva la misma escala horizontal y vertical.':`La altura se ha ampliado ${exaggeration} veces; las distancias horizontales no cambian.`} Los colores indican altura; no representan el color real del suelo.</p><dl><div><dt>Muestra horizontal</dt><dd>{site.cell_m.toLocaleString('es')} m</dd></div><div><dt>Fuente del relieve</dt><dd>{site.source}</dd></div><div><dt>Altura mínima / máxima</dt><dd>{site.min_m.toFixed(0)} / {site.max_m.toFixed(0)} m</dd></div></dl></div>
    <div className="local-profile"><h3>Perfil A → B · oeste a este</h3><p>El trazo amarillo cruza el centro de la malla. Este gráfico muestra sus alturas originales, con ejes de distinta escala.</p>{error&&<p role="alert">{error}</p>}{!error&&!samples.length&&<p role="status">Leyendo el corte central del DEM…</p>}<svg viewBox="0 0 820 190" role="img" aria-label="Perfil de altura del corte central, de 0 a 1800 metros"><path d="M60 22V148H790" fill="none" stroke="#77958a"/><path d="M60 27H790M60 142H790" fill="none" stroke="#365046" strokeDasharray="4 6"/>{paths.map((d,i)=><path key={i} d={d} fill="none" stroke="#f0cb75" strokeWidth="2.5"/>)}<text x="50" y="32" textAnchor="end">{site.max_m.toFixed(0)} m</text><text x="50" y="146" textAnchor="end">{site.min_m.toFixed(0)} m</text><text x="60" y="173">A · 0 m</text><text x="425" y="173" textAnchor="middle">900 m</text><text x="790" y="173" textAnchor="end">B · 1.800 m</text></svg><p className="surface-hint">Alturas del datum original del DEM. El origen vertical de la malla se centra en la mediana; no es el nivel del mar.</p></div>
  </section>;
}
