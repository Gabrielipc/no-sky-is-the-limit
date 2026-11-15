import { useMemo, useState } from 'react';
import { useI18n } from '../../i18n/I18nProvider';
import { dataText } from './english';
import {
  LEVEL_COLORS, coverText, displayVolcano, levelLabel, placeText, worldShare,
  type KnownSite, type NicaraguaData, type Scored, type Scope, type Window,
} from './model';

const WIDTH = 900;
/** Cadena volcánica del Pacífico (de Cosigüina a Concepción) y país completo, en grados. */
const EXTENTS: Record<Scope, [number, number, number, number]> = {
  volcanic: [-87.78, 11.3, -85.4, 13.12],
  all: [-87.75, 10.65, -82.65, 15.1],
};
// Etiquetas de volcanes que, si no, se pisan (Cerro Negro y Las Pilas están a 2,6 km).
const LABEL_SIDE: Record<string, 'left' | 'right' | 'below'> = {
  '344070': 'left', '344080': 'below', '344101': 'left', '344111': 'right', '344092': 'left', '344120': 'left',
};

type Props = {
  data: NicaraguaData; ranked: Scored[]; water: Window[]; scope: Scope; selected?: string; total: number;
  onSelect: (id: string) => void; sites: KnownSite[];
};

export function NicaraguaMap({ data, ranked, water, scope, selected, total, onSelect, sites }: Props) {
  const { lang, t } = useI18n();
  const [hover, setHover] = useState<{ w: Scored; x: number; y: number }>();
  const [w0, s0, e0, n0] = EXTENTS[scope];
  const k = Math.cos(((s0 + n0) / 2) * Math.PI / 180);
  const scale = WIDTH / ((e0 - w0) * k);
  const height = Math.round((n0 - s0) * scale);
  const px = (lon: number) => (lon - w0) * k * scale;
  const py = (lat: number) => (n0 - lat) * scale;
  const path = useMemo(() => {
    const g = data.boundary.geometry;
    const polys = (g.type === 'Polygon' ? [g.coordinates] : g.coordinates) as number[][][][];
    return polys.map(poly => poly.map(ring => 'M' + ring.map(([x, y]) => `${px(x).toFixed(1)},${py(y).toFixed(1)}`).join('L') + 'Z').join('')).join('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, scope]);
  const kmPx = scale / 111.32;
  const order = useMemo(() => [...ranked].sort((a, b) => a.level - b.level), [ranked]);
  const sel = ranked.find(r => r.region_id === selected);
  const side = (w: Scored) => (w.source === 'atlas' ? 3 : 2) * kmPx;
  return (
    <figure className="nic-map">
      <div className="nic-map-frame">
        <svg viewBox={`0 0 ${WIDTH} ${height}`} role="img"
          aria-label={t(
            `Mapa de ${scope === 'volcanic' ? 'la cadena volcánica' : 'Nicaragua'} con ${ranked.length} ventanas coloreadas según su parecido`,
            `Map of ${scope === 'volcanic' ? 'the volcanic chain' : 'Nicaragua'} with ${ranked.length} windows coloured by similarity`,
          )}
          onMouseLeave={() => setHover(undefined)}>
          <rect width={WIDTH} height={height} className="nic-sea" />
          <path d={path} className="nic-land" />
          <g aria-hidden="true">
            {water.map(w => {
              const s = (w.source === 'atlas' ? 3 : 2) * kmPx;
              return <rect key={w.region_id} x={px(w.longitude) - s / 2} y={py(w.latitude) - s / 2} width={s} height={s} className="nic-water" />;
            })}
          </g>
          <g>
            {order.map(w => {
              const s = side(w);
              return (
                <rect key={w.region_id} x={px(w.longitude) - s / 2} y={py(w.latitude) - s / 2} width={s} height={s}
                  rx={Math.min(2, s / 4)} fill={LEVEL_COLORS[w.level]} className="nic-cell"
                  onMouseEnter={() => setHover({ w, x: px(w.longitude), y: py(w.latitude) })}
                  onClick={() => onSelect(w.region_id)} />
              );
            })}
          </g>
          {sel && (
            <rect x={px(sel.longitude) - side(sel) / 2 - 2} y={py(sel.latitude) - side(sel) / 2 - 2}
              width={side(sel) + 4} height={side(sel) + 4} rx={3} className="nic-selected" />
          )}
          <g className="nic-volcanoes">
            {data.volcanoes.volcanoes.map(v => {
              const x = px(v.longitude), y = py(v.latitude);
              if (x < 0 || x > WIDTH || y < 0 || y > height) return null;
              const where = LABEL_SIDE[v.id] ?? 'right';
              const t = where === 'left' ? { x: x - 9, y: y + 4, a: 'end' } : where === 'below' ? { x, y: y + 18, a: 'middle' } : { x: x + 9, y: y + 4, a: 'start' };
              return (
                <g key={v.id}>
                  <path d={`M${x},${y - 6}L${x + 5.5},${y + 4}L${x - 5.5},${y + 4}Z`} className="nic-volcano" />
                  {scope === 'volcanic' && <text x={t.x} y={t.y} textAnchor={t.a as 'start'} className="nic-label">{displayVolcano(v.name)}</text>}
                </g>
              );
            })}
          </g>
          <g>
            {sites.map(s => (
              <circle key={s.id} cx={px(s.longitude)} cy={py(s.latitude)} r={scope === 'volcanic' ? 9 : 6} className="nic-known">
                <title>{dataText(s.name, lang)} · {t('análogo conocido', 'known analogue')}</title>
              </circle>
            ))}
          </g>
          <g className="nic-scale" transform={`translate(${WIDTH - 24 - 20 * kmPx},${height - 22})`}>
            <rect width={20 * kmPx} height={4} />
            <text x={10 * kmPx} y={-6} textAnchor="middle">20 km</text>
          </g>
        </svg>
        {hover && (
          <div className="nic-tooltip" role="status"
            style={{ left: `${(hover.x / WIDTH) * 100}%`, top: `${(hover.y / height) * 100}%` }}>
            <strong>{placeText(data, hover.w, lang)}</strong>
            <span>{t('Puesto', 'Rank')} {hover.w.rank} {t('de', 'of')} {ranked.length} · {worldShare(hover.w.global_rank, total, lang)}</span>
            <span>{coverText(hover.w, lang)}</span>
          </div>
        )}
      </div>
      <figcaption>
        <span className="nic-legend-ramp" aria-label={t('Escala de parecido', 'Similarity scale')}>
          <small>{t('Menos parecido', 'Less similar')}</small>
          {LEVEL_COLORS.map((c, i) => <i key={c} style={{ background: c }} title={levelLabel(i, lang)} />)}
          <small>{t('Más parecido', 'More similar')}</small>
        </span>
        <span className="nic-legend-item"><i className="nic-key-volcano" />{t('Volcán holoceno (GVP)', 'Holocene volcano (GVP)')}</span>
        <span className="nic-legend-item"><i className="nic-key-known" />{t('Análogo conocido', 'Known analogue')}</span>
        <span className="nic-legend-item"><i className="nic-key-water" />{t('Agua (sin clasificar)', 'Water (not ranked)')}</span>
        <small>{t('El color compara con el resto de ventanas mostradas (quintiles), no es una probabilidad.', 'Colour compares with the other windows shown (quintiles); it is not a probability.')}</small>
      </figcaption>
    </figure>
  );
}
