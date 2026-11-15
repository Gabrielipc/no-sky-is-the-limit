import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Layers, Zap, ArrowRight, ShieldCheck, Eye, Compass, Mountain } from 'lucide-react';
import { SingleTerrainViewer, TERRAIN_CATALOG, type TerrainConfig } from './TexturedTerrain3D';

// ── Comparaciones preconfiguradas basadas en el pitch científico ──
interface ComparisonScenario {
  id: string;
  label: string;
  tagline: string;
  earthKey: keyof typeof TERRAIN_CATALOG;
  spaceKey: keyof typeof TERRAIN_CATALOG;
  similarity: number;
  slopeDelta: string;
  reliefDelta: string;
  finding: string;
  instrumentSources: string[];
  dimensions: {
    slope: number;
    relief: number;
    roughness: number;
    mineralogy: number;
  };
}

const COMPARISON_SCENARIOS: ComparisonScenario[] = [
  {
    id: 'utah-jezero',
    label: 'Utah ↔ Jezero (Marte)',
    tagline: 'El análogo más cercano en inclinación de laderas',
    earthKey: 'utah',
    spaceKey: 'jezero',
    similarity: 94,
    slopeDelta: '1.5° de diferencia',
    reliefDelta: '-28 m (Utah más plano)',
    finding: 'Utah no es el análogo más famoso, pero sus pendientes se alejan solo 1.5° de las laderas del cráter Jezero donde opera Perseverance, minimizando riesgos de tracción para el rover.',
    instrumentSources: ['NASA HiRISE', 'NASA MOLA', 'USGS 3DEP', 'EMIT (ISS)'],
    dimensions: { slope: 97, relief: 91, roughness: 95, mineralogy: 92 },
  },
  {
    id: 'atacama-jezero',
    label: 'Atacama ↔ Jezero (Marte)',
    tagline: 'El análogo más citado, pero con alto desvío de pendiente',
    earthKey: 'atacama',
    spaceKey: 'jezero',
    similarity: 78,
    slopeDelta: '5.0° de diferencia',
    reliefDelta: '+84 m (Atacama más escarpado)',
    finding: 'Aunque Atacama es mundialmente famoso por su aridez, la inclinación de sus laderas difiere 5.0° de Jezero. Ensayar movilidad rover aquí puede generar falsos positivos.',
    instrumentSources: ['NASA MOLA', 'Copernicus GLO-30', 'ESA Sentinel-2'],
    dimensions: { slope: 72, relief: 79, roughness: 81, mineralogy: 84 },
  },
  {
    id: 'atacama-shackleton',
    label: 'Atacama ↔ Shackleton (Luna)',
    tagline: 'Preparando el terreno polar para la misión Artemis',
    earthKey: 'atacama',
    spaceKey: 'shackleton',
    similarity: 88,
    slopeDelta: '4.1° de diferencia',
    reliefDelta: '-144 m',
    finding: 'El Polo Sur lunar presenta pendientes pronunciadas e iluminación rasante. Atacama ofrece superficies rugosas y secas ideales para ensayar sensores ópticos y lidar.',
    instrumentSources: ['NASA LRO LOLA', 'Copernicus GLO-30', 'JAXA Kaguya'],
    dimensions: { slope: 89, relief: 86, roughness: 90, mineralogy: 87 },
  },
];

// ── Gauge animado ──────────────────────────────────────────
function SimilarityGauge({ value, color }: { value: number; color: string }) {
  const [displayed, setDisplayed] = useState(0);
  const circumference = 2 * Math.PI * 40;

  useEffect(() => {
    setDisplayed(0);
    let start: number | null = null;
    const duration = 1200;
    const animate = (ts: number) => {
      if (!start) start = ts;
      const p = Math.min((ts - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplayed(Math.round(value * eased));
      if (p < 1) requestAnimationFrame(animate);
    };
    const raf = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(raf);
  }, [value]);

  const strokeDash = (displayed / 100) * circumference;

  return (
    <div className="match-gauge-box">
      <svg viewBox="0 0 100 100" className="match-gauge-svg">
        <circle cx="50" cy="50" r="40" className="match-gauge-track" />
        <circle
          cx="50" cy="50" r="40"
          className="match-gauge-fill"
          stroke={color}
          strokeDasharray={`${strokeDash} ${circumference}`}
          strokeDashoffset={circumference * 0.25}
          strokeLinecap="round"
        />
      </svg>
      <div className="match-gauge-center">
        <span className="match-gauge-pct" style={{ color }}>{displayed}%</span>
        <span className="match-gauge-sub">SIMILITUD</span>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// PANEL PRINCIPAL DE ENCUENTRO ANALÓGICO PERFECTO (3D TEXTURIZADO)
// ══════════════════════════════════════════════════════════════
export function MockMatchPanel() {
  const [activeScenarioId, setActiveScenarioId] = useState<string>('utah-jezero');
  const [exaggeration, setExaggeration] = useState<number>(2.0);
  const [showWireframe, setShowWireframe] = useState<boolean>(false);
  const [colorMode, setColorMode] = useState<'geology' | 'elevation' | 'slope'>('geology');

  const currentScenario = COMPARISON_SCENARIOS.find(s => s.id === activeScenarioId) || COMPARISON_SCENARIOS[0];
  const earthTerrain: TerrainConfig = TERRAIN_CATALOG[currentScenario.earthKey];
  const spaceTerrain: TerrainConfig = TERRAIN_CATALOG[currentScenario.spaceKey];

  return (
    <div className="textured-match-container">
      {/* Selector de escenarios científicos */}
      <div className="scenario-selector-bar">
        <div className="scenario-chips">
          {COMPARISON_SCENARIOS.map(sc => {
            const isActive = sc.id === activeScenarioId;
            return (
              <button
                key={sc.id}
                className={`scenario-chip ${isActive ? 'scenario-chip--active' : ''}`}
                onClick={() => setActiveScenarioId(sc.id)}
              >
                <Compass size={14} />
                <span>{sc.label}</span>
                {isActive && <span className="chip-badge-acc">{sc.similarity}%</span>}
              </button>
            );
          })}
        </div>

        {/* Controles de visualización 3D */}
        <div className="terrain-view-controls">
          <div className="control-group">
            <span className="ctrl-label">Exageración:</span>
            {[1.0, 2.0, 3.0].map(val => (
              <button
                key={val}
                className={`ctrl-btn ${exaggeration === val ? 'ctrl-btn--active' : ''}`}
                onClick={() => setExaggeration(val)}
              >
                {val}x
              </button>
            ))}
          </div>

          <div className="control-group">
            <button
              className={`ctrl-btn ${showWireframe ? 'ctrl-btn--active' : ''}`}
              onClick={() => setShowWireframe(w => !w)}
              title="Mostrar curvas y rejilla de elevación"
            >
              <Layers size={13} />
              Rejilla
            </button>
            <button
              className={`ctrl-btn ${colorMode === 'geology' ? 'ctrl-btn--active' : ''}`}
              onClick={() => setColorMode(colorMode === 'geology' ? 'elevation' : 'geology')}
              title="Cambiar entre textura geológica y rampa hipsométrica"
            >
              <Eye size={13} />
              {colorMode === 'geology' ? 'Relieve natural' : 'Hipsometría'}
            </button>
          </div>
        </div>
      </div>

      {/* Hallazgo científico clave */}
      <motion.div
        key={currentScenario.id}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="scientific-finding-banner"
      >
        <div className="finding-icon">💡</div>
        <div className="finding-content">
          <strong>{currentScenario.tagline}</strong>
          <p>{currentScenario.finding}</p>
        </div>
      </motion.div>

      {/* ── ESCENARIO 3D COMPARATIVO CON PROFUNDIDAD Y RELIEVE ── */}
      <div className="dual-terrain-3d-grid">
        {/* Terreno 1: Tierra */}
        <div className="terrain-column terrain-column--earth">
          <div className="column-header">
            <span className="body-indicator earth-ind">TIERRA · ANÁLOGO</span>
            <span className="delta-badge">{currentScenario.slopeDelta}</span>
          </div>
          <div className="terrain-3d-frame">
            <SingleTerrainViewer
              key={`${earthTerrain.id}-${exaggeration}-${showWireframe}-${colorMode}`}
              config={earthTerrain}
              exaggeration={exaggeration}
              showWireframe={showWireframe}
              colorMode={colorMode}
            />
          </div>
        </div>

        {/* Centro: Medición, Instrumentos y Similitud */}
        <div className="terrain-center-connector">
          <SimilarityGauge
            value={currentScenario.similarity}
            color="#F2A64E"
          />

          <div className="comparison-metric-capsules">
            <div className="metric-capsule">
              <span className="cap-label">Diferencia de pendiente</span>
              <strong className="cap-val cap-val--highlight">{currentScenario.slopeDelta}</strong>
            </div>
            <div className="metric-capsule">
              <span className="cap-label">Diferencia de relieve</span>
              <strong className="cap-val">{currentScenario.reliefDelta}</strong>
            </div>
          </div>

          <div className="flow-arrow-indicator">
            <div className="flow-line-animated" />
            <ArrowRight size={18} className="flow-icon" />
          </div>

          <div className="data-source-tags">
            <span className="source-title">Instrumentos unificados:</span>
            <div className="source-badges">
              {currentScenario.instrumentSources.map(inst => (
                <span key={inst} className="source-badge">{inst}</span>
              ))}
            </div>
          </div>
        </div>

        {/* Terreno 2: Marte o Luna */}
        <div className="terrain-column terrain-column--space">
          <div className="column-header">
            <span className="body-indicator space-ind">
              {spaceTerrain.body.toUpperCase()} · DESTINO
            </span>
            <span className="window-badge">Ventana 1.8 km</span>
          </div>
          <div className="terrain-3d-frame">
            <SingleTerrainViewer
              key={`${spaceTerrain.id}-${exaggeration}-${showWireframe}-${colorMode}`}
              config={spaceTerrain}
              exaggeration={exaggeration}
              showWireframe={showWireframe}
              colorMode={colorMode}
            />
          </div>
        </div>
      </div>

      {/* Barras de desglose multidimensional */}
      <div className="dimensions-breakdown-bar">
        <div className="dim-header">
          <Mountain size={14} className="text-gold" />
          <span>DESGLOSE MULTIDIMENSIONAL (ESCALA UNIFICADA SIN PONDERACIÓN ARBITRARIA)</span>
        </div>
        <div className="dim-bars-grid">
          <div className="dim-bar-item">
            <div className="dim-info">
              <span>Similitud de pendientes (Wasserstein)</span>
              <strong>{currentScenario.dimensions.slope}%</strong>
            </div>
            <div className="dim-track"><div className="dim-fill" style={{ width: `${currentScenario.dimensions.slope}%` }} /></div>
          </div>
          <div className="dim-bar-item">
            <div className="dim-info">
              <span>Coincidencia de relieve vertical</span>
              <strong>{currentScenario.dimensions.relief}%</strong>
            </div>
            <div className="dim-track"><div className="dim-fill" style={{ width: `${currentScenario.dimensions.relief}%` }} /></div>
          </div>
          <div className="dim-bar-item">
            <div className="dim-info">
              <span>Rugosidad topográfica</span>
              <strong>{currentScenario.dimensions.roughness}%</strong>
            </div>
            <div className="dim-track"><div className="dim-fill" style={{ width: `${currentScenario.dimensions.roughness}%` }} /></div>
          </div>
          <div className="dim-bar-item">
            <div className="dim-info">
              <span>Mineralogía espectral</span>
              <strong>{currentScenario.dimensions.mineralogy}%</strong>
            </div>
            <div className="dim-track"><div className="dim-fill" style={{ width: `${currentScenario.dimensions.mineralogy}%` }} /></div>
          </div>
        </div>
      </div>

      {/* Nota científica sin API */}
      <div className="mock-guarantee-note">
        <ShieldCheck size={14} className="text-gold" />
        <span>
          <strong>Rigor científico local:</strong> Los modelos 3D se generan a partir de DEMs reales medidos en ventanas de 1.8 km. Visualización 100% procesada en tu navegador WebGL sin llamadas de red a APIs externas.
        </span>
      </div>
    </div>
  );
}
