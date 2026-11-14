import { useEffect, useState, type PointerEvent } from 'react';
import { fmt, type Layer, type TerrainGrid, type Terrain } from '../domain/analysis';

type Frame = { zoom: number; x: number; y: number };
const center: Frame = { zoom: 1, x: .5, y: .5 };
export function TerrainLayer({ grid, layer, range, name, source, frame, onFrame }: { grid: TerrainGrid; layer: Layer; range: [number, number]; name: string; source: string; frame: Frame; onFrame: (frame: Frame) => void }) {
  const [drag, setDrag] = useState<{ x: number; y: number; frame: Frame } | null>(null);
  const [inspection, setInspection] = useState<string>('');
  useEffect(() => setInspection(''), [grid, layer]);
  const n = grid.columns, height = grid.rows, side = n / frame.zoom;
  const clamp = (v: number) => Math.max(.5 / frame.zoom, Math.min(1 - .5 / frame.zoom, v));
  function move(e: PointerEvent<SVGSVGElement>) {
    if (!drag) return;
    const rect = e.currentTarget.getBoundingClientRect();
    onFrame({ ...frame, x: clamp(drag.frame.x - (e.clientX - drag.x) / rect.width / frame.zoom), y: clamp(drag.frame.y - (e.clientY - drag.y) / rect.height / frame.zoom) });
  }
  function inspect(e: PointerEvent<SVGSVGElement>) {
    if (drag && Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) < 5) {
      const box = e.currentTarget.getBoundingClientRect();
      const x = Math.floor((frame.x * n - side / 2) + (e.clientX - box.left) / box.width * side);
      const y = Math.floor((frame.y * height - side / 2) + (e.clientY - box.top) / box.height * side);
      const value = grid[layer][Math.max(0, Math.min(height - 1, y)) * n + Math.max(0, Math.min(n - 1, x))];
      setInspection(`Celda seleccionada: ${fmt(value, layer === 'slope' ? '°' : ' m', 2)}`);
    }
    setDrag(null);
  }
  return <section className="terrain-panel"><div className="terrain-heading"><h2>{name}</h2><span>{source}</span></div>
    <svg className="terrain-layer" viewBox={`${frame.x * n - side / 2} ${frame.y * height - side / 2} ${side} ${side}`} role="img" aria-label={`${name}: ${layer === 'slope' ? 'inclinación en grados' : 'altura respecto a la mediana en metros'}. Cuadrícula medida, ventana de 1,8 km; norte arriba.`}
      onPointerDown={e => { if (e.button !== 0) return; e.currentTarget.setPointerCapture(e.pointerId); setDrag({ x: e.clientX, y: e.clientY, frame }); }} onPointerMove={move} onPointerUp={inspect} onPointerCancel={() => setDrag(null)}>
      {grid[layer].map((v, i) => { const t = v === null ? 0 : Math.max(0, Math.min(1, (v - range[0]) / (range[1] - range[0]))); return <rect key={i} x={i % n} y={Math.floor(i / n)} width="1" height="1" fill={v === null ? 'var(--nodata)' : `hsl(${210 - 100 * t} ${45 + 15 * t}% ${25 + 55 * t}%)`} />; })}
    </svg><div className="terrain-meta"><span>↑ N · 1,8 × 1,8 km</span><span>Vista 2D · {fmt(1800 / frame.zoom, ' m', 0)} de ancho</span></div>
    {inspection && <small className="inspection" aria-live="polite">{inspection}</small>}
  </section>;
}
export function ComparisonStage({ terrain, candidateId, name, cell, layer }: { terrain: Terrain; candidateId: string; name: string; cell: number; layer: Layer }) {
  const [frame, setFrame] = useState<Frame>(center);
  const range = layer === 'slope' ? terrain.slope_range : terrain.height_range;
  const ref = terrain.sites['mars-jezero-fan']?.[cell], candidate = terrain.sites[candidateId]?.[cell];
  if (!ref || !candidate) return <p role="alert">No hay capas de esta ventana y escala.</p>;
  function zoom(amount: number) { setFrame(previous => ({ zoom: Math.max(1, Math.min(4, previous.zoom + amount)), x: .5, y: .5 })); }
  return <><div className="comparison-stage"><TerrainLayer grid={ref} layer={layer} range={range} name="Jezero · Marte" source="DTM HiRISE" frame={frame} onFrame={setFrame} /><TerrainLayer grid={candidate} layer={layer} range={range} name={`${name} · Tierra`} source="SRTM" frame={frame} onFrame={setFrame} /></div>
    <div className="stage-footer"><div className="layer-legend"><span>{fmt(range[0], layer === 'slope' ? '°' : ' m', 0)}</span><span className="legend-ramp" aria-hidden="true" /><span>{fmt(range[1], layer === 'slope' ? '°' : ' m', 0)}</span><small>{layer === 'slope' ? 'Inclinación' : 'Altura respecto a la mediana'} · misma escala de color</small></div>
      <div className="zoom-controls" role="group" aria-label="Encuadre vinculado de ambos terrenos"><button onClick={() => zoom(-1)} disabled={frame.zoom === 1} aria-label="Alejar ambos terrenos">−</button><span>{frame.zoom}×</span><button onClick={() => zoom(1)} disabled={frame.zoom === 4} aria-label="Acercar ambos terrenos">+</button><button onClick={() => setFrame(center)}>Centrar</button></div></div>
    {frame.zoom > 1 && <p className="subtle-note">Arrastra un terreno para desplazar ambos. Los valores describen la ventana completa de 1,8 km.</p>}
  </>;
}
