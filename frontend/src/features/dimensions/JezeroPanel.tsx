import { useEffect, useRef, useState } from 'react';
import type { CrismData, CrismLayer } from '../../domain/minerals';
import { percent } from '../../domain/analysis';
import { surfaceFmt as fmt } from '../../domain/dimensions';
import { useResource } from '../../data/api';
import { RequestState } from '../../components/EvidenceStatus';
import { EvidenceLinks, MethodDrawer } from '../../components/MethodDrawer';

const low = [48, 39, 111];
const middle = [36, 151, 148];
const high = [249, 219, 117];
const coverageColors = { supported: [116, 174, 119], excluded: [213, 135, 77], missing: [88, 98, 108] };

function indicatorColor(value: number, min: number, max: number) {
  const t = min === max ? .5 : Math.min(1, Math.max(0, (value - min) / (max - min)));
  const [from, to, fraction] = t < .5 ? [low, middle, t * 2] as const : [middle, high, (t - .5) * 2] as const;
  return from.map((channel, i) => channel + fraction * (to[i] - channel));
}

export function JezeroPanel({ layer, onLayer }: { layer: CrismLayer; onLayer: (value: CrismLayer) => void }) {
  const resource = useResource<CrismData>('/api/minerals/jezero');
  return <section className="mineral-map-panel" aria-label="Indicadores CRISM de Jezero">
    <RequestState {...resource} />
    {resource.data && <JezeroMap data={resource.data} layerId={layer} onLayer={onLayer} />}
  </section>;
}

function JezeroMap({ data, layerId, onLayer }: { data: CrismData; layerId: CrismLayer; onLayer: (value: CrismLayer) => void }) {
  const { grid, coverage } = data;
  const { rows, columns, inside, mask } = grid;
  const [index, setIndex] = useState<number | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const layer = layerId === 'coverage' ? undefined : data.layers.find(item => item.id === layerId) ?? data.layers[0];
  const row = index === null ? 0 : Math.floor(index / columns);
  const col = index === null ? 0 : index % columns;
  const validCells = layer?.valid_cells ?? coverage.supported;
  const title = layer?.label ?? 'Cobertura VNIR/IR';

  useEffect(() => {
    const context = canvas.current?.getContext('2d');
    if (!context) return;
    const image = context.createImageData(columns, rows);
    for (let i = 0; i < inside.length; i++) {
      if (!inside[i]) continue;
      const value = layer?.values[i];
      let rgb = coverageColors.missing;
      if (mask[i] === 1) rgb = coverageColors.excluded;
      else if (mask[i] === 0 && !layer) rgb = coverageColors.supported;
      else if (value != null && layer?.p02 != null && layer.p98 != null) rgb = indicatorColor(value, layer.p02, layer.p98);
      image.data.set([...rgb, 255], i * 4);
    }
    context.putImageData(image, 0, 0);
  }, [columns, rows, inside, mask, layer]);

  function inspection() {
    if (index === null) return 'Pulsa una celda o recorre el mapa con las flechas.';
    if (!inside[index]) return 'Fuera de la ventana.';
    if (mask[index] === null) return 'Sin cobertura CRISM.';
    if (mask[index] === 1) return 'Celda excluida por la máscara VNIR/IR.';
    if (!layer) return 'Cobertura válida en visible e infrarrojo.';
    const value = layer.values[index];
    return value === null ? 'Indicador sin dato en esta celda.' : `${layer.id === 'atm_residual' ? 'Residuo' : layer.id} · ${fmt(value, '', 5)}`;
  }

  return <>
    <div className="mineral-map-title"><h2>Jezero</h2><span>Marte · CRISM · {data.date}</span></div>
    <label className="select-field mineral-map-select">Capa de Jezero
      <select value={layer?.id ?? 'coverage'} onChange={event => onLayer(event.target.value as CrismLayer)}>
        {data.layers.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
        <option value="coverage">Cobertura VNIR/IR</option>
      </select>
    </label>
    <div className="crism-map mineral-map">
      <canvas ref={canvas} width={columns} height={rows} role="img" tabIndex={0}
        aria-label={`Mapa CRISM de Jezero, ${title}. Flechas para inspeccionar celdas.`}
        onPointerUp={event => {
          const box = event.currentTarget.getBoundingClientRect();
          const c = Math.max(0, Math.min(columns - 1, Math.floor((event.clientX - box.left) / box.width * columns)));
          const r = Math.max(0, Math.min(rows - 1, Math.floor((event.clientY - box.top) / box.height * rows)));
          setIndex(r * columns + c);
        }}
        onKeyDown={event => {
          const move = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[event.key];
          if (!move) return;
          event.preventDefault();
          if (index === null) {
            setIndex(Math.floor(rows / 2) * columns + Math.floor(columns / 2));
            return;
          }
          const c = Math.max(0, Math.min(columns - 1, col + move[0]));
          const r = Math.max(0, Math.min(rows - 1, row + move[1]));
          setIndex(r * columns + c);
        }} />
      {index !== null && <span aria-hidden="true" className="crism-cursor" style={{
        left: `${100 * col / columns}%`, top: `${100 * row / rows}%`,
        width: `${100 / columns}%`, height: `${100 / rows}%`
      }} />}
    </div>
    <div className="terrain-meta"><span>↑ N · cuadrícula de {grid.step_m[0]} m</span><span>{percent(validCells / coverage.total)} con dato</span></div>
    <div className="mineral-legend">
      {layer && layer.p02 !== null && layer.p98 !== null && <span aria-label="Escala local de color">
        ≤ {fmt(layer.p02, '', 4)} <i className="mineral-ramp crism-ramp" /> ≥ {fmt(layer.p98, '', 4)}
      </span>}
      {!layer && <span><i className="mineral-key" style={{ background: 'rgb(116 174 119)' }} />Soporte válido</span>}
      <span><i className="mineral-key" style={{ background: 'rgb(213 135 77)' }} />Excluida por máscara</span>
      <span><i className="mineral-key" style={{ background: 'rgb(88 98 108)' }} />Sin dato</span>
    </div>
    <p className="mineral-inspection" aria-live="polite">{index !== null && `Fila ${row + 1}, columna ${col + 1} · `}{inspection()}</p>
    <p className="dimension-note">{layer?.description ?? 'La máscara distingue las celdas que tienen señal de ambos detectores.'}</p>
    <MethodDrawer title="Cobertura, método y fuentes CRISM">
      <p>{coverage.supported.toLocaleString('es')} celdas con cobertura válida, {coverage.excluded.toLocaleString('es')} excluidas por máscara y {coverage.missing.toLocaleString('es')} sin cobertura.</p>
      <p>Los colores de cada indicador se ajustan entre los percentiles 2 y 98 de Jezero. La inspección conserva el valor con su signo.</p>
      <p>Los indicadores CRISM describen variaciones espectrales. Comparar identificaciones entre planetas requiere una clasificación común.</p>
      <a href={data.documentation} target="_blank" rel="noreferrer">Documentación CRISM · {data.observation_id} ↗</a>
      <EvidenceLinks links={data.evidence} />
    </MethodDrawer>
  </>;
}
