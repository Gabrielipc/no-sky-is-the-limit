import { Component, lazy, Suspense, useState, type ReactNode } from 'react';
import { loadCesium } from '../../data/loadCesium';
import { useResource } from '../../data/api';
import type { AtlasState } from '../../app/useAtlasState';
import { asset } from './assets';
import { layerURL, type SurfaceManifest, type SurfaceMode, type RemoteLayer } from './terrain';
import './surface.css';
const Scene = lazy(async () => { await loadCesium(); return import('./SurfaceScene'); });
class SceneBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <div className="surface-failure" role="alert"><h2>No se pudo abrir el visor 3D</h2><p>Comprueba WebGL y vuelve a cargar la página. Los mapas de alturas y sus fuentes siguen disponibles debajo.</p></div> : this.props.children; }
}
export function SurfaceWorkspace({ state, update }: { state: AtlasState; update: (p: Partial<AtlasState>) => void }) {
  const result = useResource<SurfaceManifest>(asset('manifest.json'));
  const [mode, setMode] = useState<SurfaceMode>('space');
  const [exaggeration, setExaggeration] = useState(1);
  const [texture, setTexture] = useState<'relief' | 'height'>('relief');
  const [remote, setRemote] = useState<RemoteLayer>(null);
  const [kind, setKind] = useState<'terrain' | 'tiles'>('tiles');
  const [url, setURL] = useState('');
  const [formError, setFormError] = useState('');
  const site = result.data?.sites.find(s => s.id === state.surfaceSite);
  function select(id: string) { update({ surfaceSite: id }); setRemote(null); setFormError(''); setMode('space'); }
  return <section className="surface-workspace" aria-labelledby="surface-title">
    <div className="surface-heading"><div><p className="surface-eyebrow">OBSERVATORIO DEL TERRENO · CESIUMJS</p><h1 id="surface-title">Del espacio a la superficie.</h1><p>Recorre el planeta. Acércate al relieve. Explora la forma de una ventana medida.</p></div><span className="surface-tag">MARTE ↔ TIERRA</span></div>
    {result.error && <div role="alert" className="request-error">{result.error}<button onClick={result.retry}>Reintentar</button></div>}
    {result.loading && <p role="status">Cargando catálogo de superficies…</p>}
    {site && result.data && <>
      <div className="surface-layout"><aside className="surface-sidebar" aria-label="Controles de superficie">
        <div className="surface-control-block"><span className="surface-step">01 / DESTINO</span><div className="surface-destinations">{result.data.sites.map(s => <button key={s.id} aria-pressed={s.id === site.id} onClick={() => select(s.id)}><span className={`planet-dot ${s.body.toLowerCase()}`} aria-hidden="true" /><span><strong>{s.id === 'mars-jezero-fan' ? 'Jezero' : s.id === 'earth-utah' ? 'Utah' : 'Atacama'}</strong><small>{s.body === 'Mars' ? 'Marte · delta antiguo' : 'Tierra · terreno análogo'}</small></span><span aria-hidden="true">↗</span></button>)}</div></div>
        <div className="surface-control-block"><span className="surface-step">02 / ESCALA DE EXPLORACIÓN</span><div className="surface-modes">{([{id:'space',name:'Órbita',detail:'El planeta completo'},{id:'regional',name:'Relieve regional',detail:'Descender al lugar'},{id:'mesh',name:'Superficie local',detail:'DEM → malla 3D'}] as const).map(m => <button key={m.id} aria-pressed={mode === m.id} onClick={() => setMode(m.id)}><span>{m.name}</span><small>{m.detail}</small></button>)}</div></div>
        <div className="surface-control-block"><span className="surface-step">03 / APARIENCIA</span><label htmlFor="terrain-exaggeration">Exageración vertical <strong>{exaggeration}×</strong></label><input id="terrain-exaggeration" type="range" min="1" max="5" step="0.5" value={exaggeration} onChange={e => setExaggeration(Number(e.target.value))}/><p className="surface-hint">{exaggeration === 1 ? 'Proporciones reales del relieve.' : 'Alturas amplificadas para leer la forma.'}</p>
        {mode === 'mesh' && <div className="surface-textures" role="group" aria-label="Textura de la malla"><button aria-pressed={texture==='relief'} onClick={()=>setTexture('relief')}>Relieve sombreado</button><button aria-pressed={texture==='height'} onClick={()=>setTexture('height')}>Mapa de alturas</button></div>}</div>
        <div className="surface-readout"><span>VENTANA LOCAL</span><strong>1,8 <small>×</small> 1,8 <small>km</small></strong><p>{site.source} · paso visual {site.cell_m.toLocaleString('es')} m</p><p>{(site.coverage*100).toFixed(1)} % de celdas válidas</p></div>
      </aside><div className="surface-stage"><SceneBoundary key={site.id}><Suspense fallback={<div className="surface-loading" role="status">Iniciando CesiumJS…</div>}><Scene site={site} manifest={result.data} mode={mode} exaggeration={exaggeration} texture={texture} remote={remote}/></Suspense></SceneBoundary></div></div>
      <div className="surface-caption"><span>Centro · {Math.abs(site.latitude).toFixed(3)}° {site.latitude>=0?'N':'S'} / {Math.abs(site.longitude).toFixed(3)}° {site.longitude>=0?'E':'O'}</span><p>{mode==='mesh' ? 'Malla local con alturas respecto a la mediana. El sombreado se deriva del DEM; no es una fotografía. Los huecos conservan su ausencia de datos.' : site.body==='Mars' ? 'MOLA global · 0,25° (~14,8 km en el ecuador). El acercamiento no añade resolución. El detalle local se abre por separado.' : 'Blue Marble · NASA. El relieve mundial se solicita a Esri; su detalle depende de la fuente y la conexión.'}</p></div>
      <div className="surface-details"><details><summary>Cómo se construye esta superficie</summary><div className="surface-method"><div><span>01</span><h3>Altura en cada píxel</h3><img src={asset(site.heightmap)} alt={`Mapa de alturas calibrado de ${site.name}`} /><p>Una imagen en grises conserva elevación y máscara. Error máximo de codificación: {(site.scale_m/2).toFixed(2)} m.</p><a href={asset(site.heightmap)} download>Descargar heightmap PNG ↓</a></div><div><span>02</span><h3>Una cuadrícula desplazada</h3><p>JavaScript convierte cada muestra en un vértice, conserva norte arriba y desplaza la malla en metros. Las caras con datos ausentes se omiten.</p><p>{site.width} × {site.height} muestras. Las alturas se centran en {site.center_m.toFixed(1)} m del datum original.</p></div><div><span>03</span><h3>Textura y procedencia</h3><img src={asset(site.texture)} alt="Textura de relieve derivada del DEM"/><p>El relieve sombreado usa la misma cuadrícula. Las medidas científicas del atlas se consultan en sus recorridos originales.</p><a href={site.source_url} target="_blank" rel="noreferrer">Fuente del DEM ↗</a> · <a href={asset('manifest.json')} target="_blank" rel="noreferrer">Manifiesto de visualización ↗</a></div></div></details>
      <details><summary>Conectar terreno o 3D Tiles</summary><div className="surface-connect"><p>Servicios propios o abiertos con acceso CORS. Terreno: raíz con <code>layer.json</code> (quantized-mesh). 3D Tiles: URL de <code>tileset.json</code>, georreferenciada en WGS84. Las capas externas se muestran sobre la Tierra, en órbita o relieve regional.</p><form onSubmit={e=>{e.preventDefault();try{setRemote({kind,url:layerURL(url,window.location.href)});setFormError('');setMode('regional');}catch(error){setFormError((error as Error).message);}}}><label>Tipo<select value={kind} onChange={e=>setKind(e.target.value as typeof kind)}><option value="tiles">3D Tiles</option><option value="terrain">Terreno quantized-mesh</option></select></label><label className="surface-url">URL del servicio<input type="url" required placeholder="https://…/tileset.json" value={url} onChange={e=>setURL(e.target.value)}/></label><button disabled={site.body==='Mars'}>Conectar</button>{remote && <button type="button" onClick={()=>setRemote(null)}>Quitar capa</button>}</form>{site.body==='Mars' && <p>Selecciona Utah o Atacama para conectar un servicio terrestre.</p>}{formError && <p role="alert">{formError}</p>}</div></details></div>
    </>}
  </section>;
}
