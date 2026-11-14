import { useState } from 'react';
import { fmt, type RegionalFeature } from '../../domain/analysis';

type Control = { id: string; name: string; latitude: number; longitude: number };
export function RegionalMap({ area, features, selected, onSelect, controls }: { area: { id: string; name: string; bbox: number[] }; features: RegionalFeature[]; selected: string; onSelect: (id: string) => void; controls: Control[] }) {
  const [zoom, setZoom] = useState(1);
  const [failedBackground, setFailedBackground] = useState(false);
  const [w, s, e, n] = area.bbox;
  const width = 650, height = width * (n - s) / ((e - w) * Math.cos((n + s) / 2 * Math.PI / 180));
  // Local equirectangular display, with longitude scaled at the area's central latitude.
  const x = (lon: number) => (lon - w) / (e - w) * width;
  const y = (lat: number) => (n - lat) / (n - s) * height;
  const target = features.find(f => f.properties.id === selected)?.properties ?? controls.find(c => c.id === selected);
  const halfW = (width + 70) / zoom / 2, halfH = (height + 60) / zoom / 2;
  const cx = zoom > 1 && target ? Math.max(halfW - 35, Math.min(width + 35 - halfW, x(target.longitude))) : width / 2;
  const cy = zoom > 1 && target ? Math.max(halfH - 30, Math.min(height + 30 - halfH, y(target.latitude))) : height / 2;
  return <div className="regional-map" id="regional-map"><div className="map-toolbar"><div><p className="eyebrow">MAPA DEL MUESTREO</p><h2>{area.name}</h2></div><div className="zoom-controls"><button onClick={() => setZoom(z => Math.max(1, z - 1))} disabled={zoom === 1} aria-label="Alejar mapa">−</button><button onClick={() => setZoom(z => Math.min(4, z + 1))} disabled={zoom === 4} aria-label="Acercar mapa a la selección">+</button><button onClick={() => setZoom(1)}>Ver área</button></div></div>
    <svg className="sampling-map" viewBox={`${cx - halfW} ${cy - halfH} ${halfW * 2} ${halfH * 2}`} role="img" aria-label={`${area.name}: ${features.length} huellas de ventanas de 3 km. Los espacios entre ventanas no están evaluados. Selección disponible también en la lista.`}>
      <rect x="0" y="0" width={width} height={height} className="map-base" />
      {!failedBackground && <image href={`/analysis/${area.id}-context.png`} x="0" y="0" width={width} height={height} preserveAspectRatio="none" onError={() => setFailedBackground(true)} />}
      {[0, .5, 1].map(t => <g className="map-graticule" key={t}><line x1={t * width} x2={t * width} y1="0" y2={height} /><line x1="0" x2={width} y1={t * height} y2={t * height} /></g>)}
      {features.filter(f => f.properties.id !== selected).map(f => <polygon key={f.properties.id} className={f.properties.passes_filter ? 'map-window accepted' : 'map-window excluded'} points={f.geometry.coordinates[0].map(([lon, lat]) => `${x(lon)},${y(lat)}`).join(' ')} onClick={() => onSelect(f.properties.id)}><title>{f.properties.name} · {f.properties.passes_filter ? 'Cumple el filtro' : 'Fuera del filtro'}</title></polygon>)}
      {features.filter(f => f.properties.id === selected).map(f => <polygon key={f.properties.id} className="map-window selected" points={f.geometry.coordinates[0].map(([lon, lat]) => `${x(lon)},${y(lat)}`).join(' ')} onClick={() => onSelect(f.properties.id)}><title>{f.properties.name} · seleccionada</title></polygon>)}
      {controls.map(c => <g key={c.id} className="map-control" onClick={() => onSelect(c.id)}><circle cx={x(c.longitude)} cy={y(c.latitude)} r={selected === c.id ? 8 : 6} className={selected === c.id ? 'selected-control' : ''} /><title>{c.name} · control contextual</title></g>)}
      <text x={width - 12} y="26" textAnchor="end" className="north-label">↑ N</text>
    </svg>
    <div className="map-extents"><span>Lat. {fmt(s, '°')} a {fmt(n, '°')}</span><span>Lon. {fmt(w, '°')} a {fmt(e, '°')}</span></div><div className="map-legend"><span><i className="map-key accepted" />Cumple</span><span><i className="map-key excluded" />Fuera</span><span><i className="map-key control" />Control</span><span><i className="map-key selected" />Selección</span></div>
    <p className="chart-caption">Huellas de 3 km, separadas 10 km. Fondo de relieve GMTED para ubicación; contraste propio de esta región.</p>
    {failedBackground && <p className="subtle-note">Fondo no disponible. Las huellas y coordenadas siguen visibles.</p>}
  </div>;
}
