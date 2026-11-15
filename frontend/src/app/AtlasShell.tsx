import { useEffect, useState } from 'react';
import { SurfaceWorkspace } from '../features/surface/SurfaceWorkspace';
import { useAtlasState } from './useAtlasState';
import { CompareWorkspace } from '../features/compare/CompareWorkspace';
import { ExploreWorkspace } from '../features/explore/ExploreWorkspace';
import { SensitivityWorkspace } from '../features/sensitivity/SensitivityWorkspace';
import { WorldWorkspace } from '../features/world/WorldWorkspace';
import { DimensionsWorkspace } from '../features/dimensions/DimensionsWorkspace';

export function AtlasShell() {
  const { state, update, adjusted, dismissAdjustment } = useAtlasState();
  const [help, setHelp] = useState(false);
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'instant' }); }, [state.view]);
  return <><a className="skip-link" href="#main-content">Saltar al contenido</a><header className="app-header"><a className="brand" href="/" aria-label="Atlas de análogos planetarios, inicio"><span aria-hidden="true">✳</span> ATLAS <small>ANÁLOGOS PLANETARIOS</small></a><nav aria-label="Recorridos del atlas">{([{ id: 'surface', name: 'Superficie 3D' }, { id: 'compare', name: 'Comparar lugares' }, { id: 'dimensions', name: 'Más dimensiones' }, { id: 'explore', name: 'Explorar zonas' }, { id: 'world', name: 'Búsqueda mundial' }, { id: 'sensitivity', name: 'Ver qué cambia' }] as const).map(view => <button key={view.id} aria-current={state.view === view.id ? 'page' : undefined} onClick={() => update({ view: view.id })}>{view.name}</button>)}</nav><button className="help-toggle" aria-expanded={help} aria-controls="atlas-help" onClick={() => setHelp(open => !open)}>Cómo leerlo</button></header>
    <main id="main-content"><div className="scope-line"><span className="scope-dot" aria-hidden="true" />Comparación exploratoria de terreno <span>·</span> movilidad sin evaluar</div>
      {adjusted && <div className="parameter-notice" role="status">Se ajustaron parámetros del enlace a las opciones disponibles.<button onClick={dismissAdjustment}>Entendido</button></div>}
      {help && <section id="atlas-help" className="help-panel"><h2>Empieza por lo que ves</h2><div><p><strong>Inclinación:</strong> cuánto se inclina cada celda. Los colores tienen la misma escala en ambos lugares.</p><p><strong>Relieve:</strong> cuánto varía la altura dentro de la ventana; no es la altitud del lugar.</p><p><strong>Celda:</strong> tamaño de los bloques con los que medimos. Un bloque mayor suaviza detalles.</p><p><strong>Falta evaluar:</strong> desconocido, sin valor cero ni mala nota. Cumplir un filtro no valida un lugar para una misión.</p></div></section>}
      {state.view === 'surface' ? <SurfaceWorkspace state={state} update={update} /> : state.view === 'world' ? <WorldWorkspace /> : state.view === 'compare' ? <CompareWorkspace state={state} update={update} /> : state.view === 'dimensions' ? <DimensionsWorkspace state={state} update={update} /> : state.view === 'explore' ? <ExploreWorkspace state={state} update={update} /> : <SensitivityWorkspace state={state} update={update} />}
    </main><footer className="app-footer"><span>✳ ATLAS · MARTE ↔ TIERRA</span><span>Datos medidos, diferencias visibles, preguntas abiertas.</span></footer></>;
}
