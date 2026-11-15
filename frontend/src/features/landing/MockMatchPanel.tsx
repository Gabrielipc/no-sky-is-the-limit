import { useState } from 'react';
import { ArrowLeftRight } from 'lucide-react';
import { SingleTerrainViewer, TERRAIN_CATALOG } from './TexturedTerrain3D';

export interface MatchExample {
  id: string;
  label: string;
  earth: string;
  earthBody: string;
  space: string;
  spaceBody: string;
  earthTerrainKey: keyof typeof TERRAIN_CATALOG;
  spaceTerrainKey: keyof typeof TERRAIN_CATALOG;
  summary: string;
}

export const MATCH_EXAMPLES: MatchExample[] = [
  {
    id: 'utah-jezero',
    label: 'Utah → Cráter Jezero',
    earth: 'Desierto de Utah',
    earthBody: 'Tierra · EE. UU.',
    space: 'Cráter Jezero',
    spaceBody: 'Marte · Perseverance',
    earthTerrainKey: 'utah',
    spaceTerrainKey: 'jezero',
    summary:
      'Cuando comparamos las laderas del sector donde aterrizó Perseverance, las de esta zona de Utah se parecen más que las de Atacama.',
  },
  {
    id: 'atacama-jezero',
    label: 'Atacama → Cráter Jezero',
    earth: 'Desierto de Atacama',
    earthBody: 'Tierra · Chile',
    space: 'Cráter Jezero',
    spaceBody: 'Marte · Perseverance',
    earthTerrainKey: 'atacama',
    spaceTerrainKey: 'jezero',
    summary:
      'Atacama es uno de los lugares más citados por su parecido con Marte, aunque sus laderas difieren del sector evaluado en Jezero.',
  },
  {
    id: 'atacama-shackleton',
    label: 'Atacama → Polo Sur Lunar',
    earth: 'Desierto de Atacama',
    earthBody: 'Tierra · Chile',
    space: 'Cráter Shackleton',
    spaceBody: 'Luna · Polo Sur',
    earthTerrainKey: 'atacama',
    spaceTerrainKey: 'shackleton',
    summary:
      'Con un mismo criterio medimos la inclinación y qué tan accidentado es el suelo antes de ensayar para la Luna.',
  },
];

export function MockMatchPanel() {
  const [activeMatch, setActiveMatch] = useState(0);
  const [viewMode, setViewMode] = useState<'3d' | 'satellite'>('3d');

  const current = MATCH_EXAMPLES[activeMatch];
  const earthConfig = TERRAIN_CATALOG[current.earthTerrainKey];
  const spaceConfig = TERRAIN_CATALOG[current.spaceTerrainKey];

  return (
    <div className="match-panel">
      <div className="match-panel-bar">
        <div className="match-pair-tabs" role="tablist" aria-label="Comparaciones de ejemplo">
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
                {item.label}
              </button>
            );
          })}
        </div>

        <div className="match-view-switch" role="group" aria-label="Vista del terreno">
          <button
            type="button"
            className={`match-view-btn ${viewMode === '3d' ? 'is-active' : ''}`}
            aria-pressed={viewMode === '3d'}
            onClick={() => setViewMode('3d')}
          >
            Relieve
          </button>
          <button
            type="button"
            className={`match-view-btn ${viewMode === 'satellite' ? 'is-active' : ''}`}
            aria-pressed={viewMode === 'satellite'}
            onClick={() => setViewMode('satellite')}
          >
            Satélite
          </button>
        </div>
      </div>

      <div className="match-stage">
        <div className="match-terrain-col">
          <span className="match-body-kicker">{current.earthBody}</span>
          <div className="match-canvas-frame">
            <SingleTerrainViewer
              key={`${current.id}-earth-${earthConfig.id}-${viewMode}`}
              config={earthConfig}
              exaggeration={2.0}
              viewMode={viewMode}
            />
          </div>
          <h3 className="match-site-name">{current.earth}</h3>
        </div>

        <div className="match-bridge" aria-hidden="true">
          <span className="match-bridge-line" />
          <span className="match-bridge-icon">
            <ArrowLeftRight size={16} />
          </span>
          <span className="match-bridge-line" />
        </div>

        <div className="match-terrain-col">
          <span className="match-body-kicker match-body-kicker--space">{current.spaceBody}</span>
          <div className="match-canvas-frame match-canvas-frame--space">
            <SingleTerrainViewer
              key={`${current.id}-space-${spaceConfig.id}-${viewMode}`}
              config={spaceConfig}
              exaggeration={2.0}
              viewMode={viewMode}
            />
          </div>
          <h3 className="match-site-name">{current.space}</h3>
        </div>
      </div>

      <p className="match-summary">{current.summary}</p>
    </div>
  );
}
