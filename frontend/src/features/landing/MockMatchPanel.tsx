import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Target, Zap, Layers, Globe2, ShieldCheck,
  Compass, ArrowRight, RotateCw, Eye, Box, Sliders
} from 'lucide-react';
import { SingleTerrainViewer, TERRAIN_CATALOG } from './TexturedTerrain3D';

export const MATCH_EXAMPLES = [
  {
    id: 'utah-jezero',
    earth: 'Desierto de Utah, EE.UU.',
    earthRegion: 'Formación Morrison · Cuenca sedimentaria',
    space: 'Cráter Jezero, Marte',
    spaceRegion: 'Delta de abanico fluvial · Sitio Perseverance',
    type: 'Marte',
    similarity: 94,
    slopeDelta: 'Δ 1.5° (Pendientes casi idénticas)',
    reliefDiff: '-28 m (Utah más plano)',
    earthImg: '/analysis/utah-context.png',
    spaceImg: '/analysis/jezero-context.png',
    earthTerrainKey: 'utah',
    spaceTerrainKey: 'jezero',
    slopeMatch: 97,
    mineralMatch: 92,
    topographyMatch: 96,
    roughnessMatch: 95,
    colorTheme: '#c5e59e',
    finding: 'Utah no es el análogo más famoso, pero sus pendientes se alejan solo 1.5° del cráter marciano donde aterrizó Perseverance, minimizando riesgos de tracción para el rover.',
    instruments: ['NASA HiRISE', 'NASA MOLA', 'USGS 3DEP', 'EMIT (ISS)'],
  },
  {
    id: 'atacama-jezero',
    earth: 'Desierto de Atacama, Chile',
    earthRegion: 'Cuenca Yungay · Hiperaridez extrema',
    space: 'Cráter Jezero, Marte',
    spaceRegion: 'Delta de abanico fluvial · 18.4°N, 77.7°E',
    type: 'Marte',
    similarity: 78,
    slopeDelta: 'Δ 5.0° (Diferencia crítica en laderas)',
    reliefDiff: '+84 m (Atacama más escarpado)',
    earthImg: '/analysis/atacama-context.png',
    spaceImg: '/analysis/jezero-context.png',
    earthTerrainKey: 'atacama',
    spaceTerrainKey: 'jezero',
    slopeMatch: 72,
    mineralMatch: 84,
    topographyMatch: 78,
    roughnessMatch: 80,
    colorTheme: '#ff7070',
    finding: 'Atacama es el análogo más citado por su aridez, pero la inclinación de sus laderas difiere 5.0° de Jezero. Ensayar movilidad de un rover aquí puede comprometer la misión.',
    instruments: ['NASA MOLA', 'Copernicus GLO-30', 'ESA Sentinel-2'],
  },
  {
    id: 'atacama-shackleton',
    earth: 'Desierto de Atacama, Chile',
    earthRegion: 'Meseta hiperárida · Sustrato seco',
    space: 'Cráter Shackleton, Luna',
    spaceRegion: 'Polo Sur Lunar 89.9°S · Misión Artemis',
    type: 'Luna',
    similarity: 88,
    slopeDelta: 'Δ 4.1° de diferencia',
    reliefDiff: '-144 m',
    earthImg: '/analysis/atacama-context.png',
    spaceImg: '/analysis/shackleton-context.png',
    earthTerrainKey: 'atacama',
    spaceTerrainKey: 'shackleton',
    slopeMatch: 89,
    mineralMatch: 87,
    topographyMatch: 89,
    roughnessMatch: 90,
    colorTheme: '#F2A64E',
    finding: 'Preparación para el programa Artemis: evaluación de sombras permanentes y rugosidad de regolito para entrenar sensores ópticos y astronautas.',
    instruments: ['NASA LRO LOLA', 'Copernicus GLO-30', 'JAXA Kaguya'],
  },
];

export function MockMatchPanel() {
  const [activeMatch, setActiveMatch] = useState(0);
  const [isScanning, setIsScanning] = useState(true);
  const [scanProgress, setScanProgress] = useState(0);
  const [viewMode, setViewMode] = useState<'3d' | 'satellite'>('3d');
  const [exaggeration, setExaggeration] = useState<number>(2.0);

  const current = MATCH_EXAMPLES[activeMatch];
  const earthConfig = TERRAIN_CATALOG[current.earthTerrainKey];
  const spaceConfig = TERRAIN_CATALOG[current.spaceTerrainKey];

  // Iniciar el escaneo láser y revelar el modelo 3D al finalizar
  useEffect(() => {
    setIsScanning(true);
    setScanProgress(0);

    const intervalTime = 25; // ms
    const totalDuration = 2000; // 2 segundos de escaneo
    const step = 100 / (totalDuration / intervalTime);

    const timer = setInterval(() => {
      setScanProgress(prev => {
        if (prev + step >= 100) {
          clearInterval(timer);
          setIsScanning(false);
          return 100;
        }
        return prev + step;
      });
    }, intervalTime);

    return () => clearInterval(timer);
  }, [activeMatch]);

  const triggerRescan = () => {
    setIsScanning(true);
    setScanProgress(0);

    const intervalTime = 25;
    const totalDuration = 1800;
    const step = 100 / (totalDuration / intervalTime);

    const timer = setInterval(() => {
      setScanProgress(prev => {
        if (prev + step >= 100) {
          clearInterval(timer);
          setIsScanning(false);
          return 100;
        }
        return prev + step;
      });
    }, intervalTime);
  };

  return (
    <div className="match-visualizer-v4">
      {/* Controles superiores de selección de análogo */}
      <div className="match-controls">
        {MATCH_EXAMPLES.map((m, i) => (
          <button
            key={m.id}
            className={`control-btn ${activeMatch === i ? 'active' : ''}`}
            onClick={() => setActiveMatch(i)}
          >
            <Compass size={14} />
            <span>{m.earth.split(',')[0]} → {m.space}</span>
            <span className="control-btn-badge">{m.similarity}%</span>
          </button>
        ))}
      </div>

      {/* Tarjeta interactiva del Motor de Coincidencias */}
      <div className="match-display-card">
        {/* Barra superior con controles de escaneo y modo 3D */}
        <div className="match-card-toolbar">
          <div className="match-finding-badge">
            <span className="finding-pill" style={{ color: current.colorTheme, borderColor: current.colorTheme }}>
              HALLAZGO CIENTÍFICO
            </span>
            <p>{current.finding}</p>
          </div>

          <div className="match-action-tools">
            <button
              className="tool-action-btn"
              onClick={triggerRescan}
              disabled={isScanning}
              title="Volver a escanear con altímetro láser"
            >
              <RotateCw size={13} className={isScanning ? 'spin-icon' : ''} />
              <span>{isScanning ? `Escaneando ${Math.round(scanProgress)}%` : 'Re-escanear'}</span>
            </button>

            {!isScanning && (
              <div className="mode-toggle-group">
                <button
                  className={`mode-toggle-btn ${viewMode === '3d' ? 'active' : ''}`}
                  onClick={() => setViewMode('3d')}
                  title="Textura geológica 3D con colores planetarios"
                >
                  <Box size={13} />
                  <span>Modelo 3D (Geología)</span>
                </button>
                <button
                  className={`mode-toggle-btn ${viewMode === 'satellite' ? 'active' : ''}`}
                  onClick={() => setViewMode('satellite')}
                  title="Ortofoto satelital de alta resolución con relieve 3D"
                >
                  <Eye size={13} />
                  <span>Satelital (Relieve 3D)</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Indicador de escaneo en progreso */}
        {isScanning && (
          <div className="scanning-banner-active">
            <div className="scan-pulse-dot" />
            <span>
              ESCANEANDO TOPOGRAFÍA MULTIFUENTE (VENTANA 1.8 KM) ... <strong>{Math.round(scanProgress)}%</strong>
            </span>
            <div className="scan-progress-track">
              <div className="scan-progress-bar" style={{ width: `${scanProgress}%` }} />
            </div>
          </div>
        )}

        {/* GRID PRINCIPAL: TIERRA ↔ GAUGE ↔ ESPACIO (100% 3D INTERACTIVO) */}
        <div className="display-grid">
          {/* LADO TIERRA */}
          <div className="display-side earth">
            <div className="side-tag">
              <Globe2 size={13} />
              TIERRA · ANÁLOGO
            </div>

            <div className="side-view-container">
              <div className="side-3d-wrapper">
                <SingleTerrainViewer
                  key={`${current.id}-earth-${earthConfig.id}-${viewMode}-${exaggeration}`}
                  config={earthConfig}
                  exaggeration={exaggeration}
                  viewMode={viewMode}
                  isScanning={isScanning}
                  scanProgress={scanProgress}
                />
                <div className="model-3d-badge">
                  <span>{viewMode === 'satellite' ? '🛰️ Satélite 3D con Relieve' : '🎮 Color Geológico 3D'}</span>
                </div>
              </div>
            </div>

            <h4>{current.earth}</h4>
            <p className="side-region-text">{current.earthRegion}</p>
          </div>

          {/* CENTRO: GAUGE DE SIMILITUD Y PENDIENTES */}
          <div className="display-center">
            <div className="similarity-gauge">
              <svg viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="44" className="gauge-bg" />
                <motion.circle
                  cx="50" cy="50" r="44"
                  className="gauge-progress"
                  stroke={current.colorTheme}
                  strokeDasharray={2 * Math.PI * 44}
                  initial={{ strokeDashoffset: 2 * Math.PI * 44 }}
                  animate={{
                    strokeDashoffset: isScanning
                      ? (2 * Math.PI * 44) * (1 - (scanProgress / 100) * (current.similarity / 100))
                      : (2 * Math.PI * 44) * (1 - current.similarity / 100)
                  }}
                  transition={{ duration: 0.2 }}
                />
              </svg>
              <div className="gauge-text">
                <span className="percent" style={{ color: current.colorTheme }}>
                  {isScanning ? Math.round((scanProgress / 100) * current.similarity) : current.similarity}%
                </span>
                <span className="label">
                  {isScanning ? 'ESCANEANDO' : 'SIMILITUD'}
                </span>
              </div>
            </div>

            {/* Delta de laderas del pitch */}
            <div className="slope-delta-pill">
              <span className="delta-label">Inclinación de laderas</span>
              <strong style={{ color: current.colorTheme }}>{current.slopeDelta}</strong>
            </div>

            {/* Línea de pulso de partículas */}
            <div className="connection-line">
              <motion.div
                className="line-flow"
                style={{ background: current.colorTheme }}
                animate={{ left: ['-100%', '100%'] }}
                transition={{ duration: 2.0, repeat: Infinity, ease: 'linear' }}
              />
            </div>

            {/* Control de exageración vertical disponible en ambos modos */}
            {!isScanning && (
              <div className="exaggeration-tool">
                <Sliders size={11} className="text-gold" />
                <span>Relieve 3D:</span>
                {[1.0, 2.0, 3.0].map(val => (
                  <button
                    key={val}
                    className={`exagg-btn ${exaggeration === val ? 'active' : ''}`}
                    onClick={() => setExaggeration(val)}
                  >
                    {val}x
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* LADO ESPACIO (MARTE / LUNA) */}
          <div className="display-side space">
            <div className="side-tag" style={{ color: current.type === 'Marte' ? '#e05222' : '#c5e59e' }}>
              <Target size={13} />
              {current.type.toUpperCase()} · DESTINO
            </div>

            <div className="side-view-container">
              <div className="side-3d-wrapper space-border">
                <SingleTerrainViewer
                  key={`${current.id}-space-${spaceConfig.id}-${viewMode}-${exaggeration}`}
                  config={spaceConfig}
                  exaggeration={exaggeration}
                  viewMode={viewMode}
                  isScanning={isScanning}
                  scanProgress={scanProgress}
                />
                <div className="model-3d-badge">
                  <span>{viewMode === 'satellite' ? '🛰️ Satélite 3D con Relieve' : '🎮 Color Geológico 3D'}</span>
                </div>
              </div>
            </div>

            <h4>{current.space}</h4>
            <p className="side-region-text">{current.spaceRegion}</p>
          </div>
        </div>

        {/* MÉTRICAS DETALLADAS DEL MOTOR */}
        <div className="match-analysis-details">
          <div className="detail">
            <Zap size={16} className="text-gold" />
            <span>Pendientes (Wasserstein): <strong>{current.slopeMatch}%</strong></span>
          </div>
          <div className="detail">
            <Layers size={16} className="text-gold" />
            <span>Relieve e hipsometría: <strong>{current.topographyMatch}%</strong></span>
          </div>
          <div className="detail">
            <Compass size={16} className="text-gold" />
            <span>Mineralogía espectral: <strong>{current.mineralMatch}%</strong></span>
          </div>
        </div>

        {/* INSTRUMENTOS DE LA NASA Y LA ESA */}
        <div className="match-instruments-row">
          <span className="inst-label">Instrumentos espaciales integrados:</span>
          <div className="inst-tags">
            {current.instruments.map(inst => (
              <span key={inst} className="inst-tag">{inst}</span>
            ))}
          </div>
        </div>

        <div className="match-disclaimer">
          <ShieldCheck size={14} className="text-gold" />
          <span>Datos calibrados por el motor Regolith Atlas · Modelos 3D generados a partir de DEMs reales de NASA y ESA</span>
        </div>
      </div>
    </div>
  );
}
