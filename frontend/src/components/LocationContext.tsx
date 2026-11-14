import { Component, lazy, Suspense, useState, type ReactNode } from 'react';
import type { Location } from '../domain/analysis';
import { fmt } from '../domain/analysis';
import { loadCesium } from '../data/loadCesium';
const Globe = lazy(async () => { await loadCesium(); const module = await import('../ContextGlobe'); return { default: module.ContextGlobe }; });
class GlobeBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <p role="alert">No se pudo abrir el globo. Puedes consultar la ubicación y las medidas de la ventana.</p> : this.props.children; }
}
export function LocationContext({ sites }: { sites: Location[] }) {
  const [open, setOpen] = useState(false);
  return <details className="location-context" onToggle={e => setOpen(e.currentTarget.open)}><summary>Ubicación en Marte y la Tierra</summary>
    {open && <div className={sites.length > 1 ? 'location-pair' : ''}>{sites.map(site => <section key={site.id}><h3>{site.name}</h3><p className="muted">{fmt(site.latitude, '°', 3)} lat. · {fmt(site.longitude, '°', 3)} lon. · ventana {fmt(site.window_m / 1000, ' km')}</p>
      <GlobeBoundary key={site.id}><Suspense fallback={<p role="status">Abriendo ubicación…</p>}><Globe site={site} /></Suspense></GlobeBoundary></section>)}</div>}
  </details>;
}
