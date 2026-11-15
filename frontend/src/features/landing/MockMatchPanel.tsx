import { useState } from 'react';
import { ArrowLeftRight } from 'lucide-react';
import { SingleTerrainViewer, TERRAIN_CATALOG } from './TexturedTerrain3D';
import { useI18n } from '../../i18n/I18nProvider';
import type { Msg } from '../../i18n/lang';

/** Every visible text holds [Spanish, English]. */
export interface MatchExample {
  id: string;
  label: Msg;
  earth: Msg;
  earthBody: Msg;
  space: Msg;
  spaceBody: Msg;
  earthTerrainKey: keyof typeof TERRAIN_CATALOG;
  spaceTerrainKey: keyof typeof TERRAIN_CATALOG;
  summary: Msg;
}

export const MATCH_EXAMPLES: MatchExample[] = [
  {
    id: 'utah-jezero',
    label: ['Utah → Cráter Jezero', 'Utah → Jezero Crater'],
    earth: ['Desierto de Utah', 'Utah Desert'],
    earthBody: ['Tierra · EE. UU.', 'Earth · USA'],
    space: ['Cráter Jezero', 'Jezero Crater'],
    spaceBody: ['Marte · Perseverance', 'Mars · Perseverance'],
    earthTerrainKey: 'utah',
    spaceTerrainKey: 'jezero',
    summary: [
      'Cuando comparamos las laderas del sector donde aterrizó Perseverance, las de esta zona de Utah se parecen más que las de Atacama.',
      'When we compare the slopes of the sector where Perseverance landed, those of this area in Utah are more similar than those of Atacama.',
    ],
  },
  {
    id: 'atacama-jezero',
    label: ['Atacama → Cráter Jezero', 'Atacama → Jezero Crater'],
    earth: ['Desierto de Atacama', 'Atacama Desert'],
    earthBody: ['Tierra · Chile', 'Earth · Chile'],
    space: ['Cráter Jezero', 'Jezero Crater'],
    spaceBody: ['Marte · Perseverance', 'Mars · Perseverance'],
    earthTerrainKey: 'atacama',
    spaceTerrainKey: 'jezero',
    summary: [
      'Atacama es uno de los lugares más citados por su parecido con Marte, aunque sus laderas difieren del sector evaluado en Jezero.',
      'Atacama is one of the places most often cited for resembling Mars, although its slopes differ from the sector assessed in Jezero.',
    ],
  },
  {
    id: 'atacama-shackleton',
    label: ['Atacama → Polo Sur Lunar', 'Atacama → Lunar South Pole'],
    earth: ['Desierto de Atacama', 'Atacama Desert'],
    earthBody: ['Tierra · Chile', 'Earth · Chile'],
    space: ['Cráter Shackleton', 'Shackleton Crater'],
    spaceBody: ['Luna · Polo Sur', 'Moon · South Pole'],
    earthTerrainKey: 'atacama',
    spaceTerrainKey: 'shackleton',
    summary: [
      'Con un mismo criterio medimos la inclinación y qué tan accidentado es el suelo antes de ensayar para la Luna.',
      'With the same criteria we measure how steep and how rugged the ground is before testing for the Moon.',
    ],
  },
];

export function MockMatchPanel() {
  const { t } = useI18n();
  const [activeMatch, setActiveMatch] = useState(0);
  const [viewMode, setViewMode] = useState<'3d' | 'satellite'>('3d');

  const current = MATCH_EXAMPLES[activeMatch];
  const earthConfig = TERRAIN_CATALOG[current.earthTerrainKey];
  const spaceConfig = TERRAIN_CATALOG[current.spaceTerrainKey];

  return (
    <div className="match-panel">
      <div className="match-panel-bar">
        <div className="match-pair-tabs" role="tablist" aria-label={t('Comparaciones de ejemplo', 'Example comparisons')}>
          {MATCH_EXAMPLES.map((item, idx) => {
            const isActive = activeMatch === idx;
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                className={`match-pair-tab ${isActive ? 'is-active' : ''}`}
                onClick={() => setActiveMatch(idx)}
              >
                {t(...item.label)}
              </button>
            );
          })}
        </div>

        <div className="match-view-switch" role="group" aria-label={t('Vista del terreno', 'Terrain view')}>
          <button
            type="button"
            className={`match-view-btn ${viewMode === '3d' ? 'is-active' : ''}`}
            aria-pressed={viewMode === '3d'}
            onClick={() => setViewMode('3d')}
          >
            {t('Relieve', 'Relief')}
          </button>
          <button
            type="button"
            className={`match-view-btn ${viewMode === 'satellite' ? 'is-active' : ''}`}
            aria-pressed={viewMode === 'satellite'}
            onClick={() => setViewMode('satellite')}
          >
            {t('Satélite', 'Satellite')}
          </button>
        </div>
      </div>

      <div className="match-stage">
        <div className="match-terrain-col">
          <span className="match-body-kicker">{t(...current.earthBody)}</span>
          <div className="match-canvas-frame">
            <SingleTerrainViewer
              key={`${current.id}-earth-${earthConfig.id}-${viewMode}`}
              config={earthConfig}
              exaggeration={2.0}
              viewMode={viewMode}
            />
          </div>
          <h3 className="match-site-name">{t(...current.earth)}</h3>
        </div>

        <div className="match-bridge" aria-hidden="true">
          <span className="match-bridge-line" />
          <span className="match-bridge-icon">
            <ArrowLeftRight size={16} />
          </span>
          <span className="match-bridge-line" />
        </div>

        <div className="match-terrain-col">
          <span className="match-body-kicker match-body-kicker--space">{t(...current.spaceBody)}</span>
          <div className="match-canvas-frame match-canvas-frame--space">
            <SingleTerrainViewer
              key={`${current.id}-space-${spaceConfig.id}-${viewMode}`}
              config={spaceConfig}
              exaggeration={2.0}
              viewMode={viewMode}
            />
          </div>
          <h3 className="match-site-name">{t(...current.space)}</h3>
        </div>
      </div>

      <p className="match-summary">{t(...current.summary)}</p>
    </div>
  );
}
