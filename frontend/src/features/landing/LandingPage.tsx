import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ChevronRight, MapPin, Info, Shield,
  BarChart3, Layers, Zap, ArrowRight, Globe2,
  Play, Pause, Compass, Mountain, Orbit
} from 'lucide-react';
import { CinematicJourney, PLANET_COLORS } from './CinematicJourney';
import { MockMatchPanel } from './MockMatchPanel';
import './LandingPage.css';

// ── Ciclo de Misión Automático (de la Tierra a Marte y de nuevo de la Tierra a la Luna) ──
const MISSION_LEGS = [
  {
    id: 'earth-origin',
    planet: 'earth' as const,
    legTag: 'PASO 1 · ORIGEN',
    titleMain: 'Antes de ir al espacio,',
    titleAcc: 'todo se prueba aquí.',
    desc: 'Los rovers y hábitats deben probarse en la Tierra antes de volar. Pero una región famosa no garantiza que su terreno sea realmente análogo al destino.',
    siteName: 'Desierto de Utah · Formación Morrison',
    siteMission: 'Evaluar tracción y movilidad en sedimentos arcillosos análogos.',
    accentColor: '#4a9eff',
  },
  {
    id: 'mars-jezero',
    planet: 'mars' as const,
    legTag: 'PASO 2 · DESTINO MARTE',
    titleMain: 'Cráter Jezero,',
    titleAcc: 'donde opera Perseverance.',
    desc: 'Buscamos rastros de vida pasada en el delta del cráter marciano. La inclinación de sus laderas exige rovers probados en pendientes rigurosamente equivalentes.',
    siteName: 'Delta del Cráter Jezero · 18.4°N, 77.7°E',
    siteMission: 'Medir diferencias de pendiente antes de planificar rutas de exploración.',
    accentColor: '#F2A64E',
  },
  {
    id: 'earth-comparison',
    planet: 'earth' as const,
    legTag: 'PASO 3 · RETORNO Y MEDICIÓN',
    titleMain: 'La fama no garantiza',
    titleAcc: 'la exactitud científica.',
    desc: 'Científicos estudian el volcán Cerro Negro y el desierto de Atacama. Sin embargo, Atacama difiere 5.0° de Jezero, mientras que Utah se aleja solo 1.5°.',
    siteName: 'Utah (Δ 1.5°) vs Atacama (Δ 5.0°)',
    siteMission: 'Descubrir el verdadero análogo cuantitativo con datos de 6 instrumentos.',
    accentColor: '#c5e59e',
  },
  {
    id: 'moon-artemis',
    planet: 'moon' as const,
    legTag: 'PASO 4 · DESTINO LUNA',
    titleMain: 'Polo Sur Lunar,',
    titleAcc: 'misión Artemis.',
    desc: 'Cráteres profundos y sombras permanentes donde se oculta hielo de agua. Caracterizamos la rugosidad del regolito polar para los próximos pasos humanos.',
    siteName: 'Cráter Shackleton · Polo Sur Lunar 89.9°S',
    siteMission: 'Entrenar astronautas y sensores ópticos en análogos terrestres.',
    accentColor: '#e9ede5',
  },
];

// Instrumentos científicos integrados
const INSTRUMENTS = [
  { name: 'NASA HiRISE', role: 'Imágenes métricas de ultra-resolución marciana' },
  { name: 'NASA MOLA', role: 'Topografía láser orbital de Marte' },
  { name: 'NASA LRO LOLA', role: 'Altímetro láser polar lunar' },
  { name: 'NASA CRISM', role: 'Espectrometría de minerales y arcillas' },
  { name: 'NASA EMIT (ISS)', role: 'Firmas espectrales terrestres desde la estación espacial' },
  { name: 'Copernicus GLO-30', role: 'Modelo digital de elevación global ESA' },
];

export function LandingPage({ onStart }: { onStart: () => void }) {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [isAutoPlaying, setIsAutoPlaying] = useState(true);
  const [isTraveling, setIsTraveling] = useState(false);

  const step = MISSION_LEGS[currentStepIndex];

  // Avance automático en ciclos continuos
  useEffect(() => {
    if (!isAutoPlaying) return;

    const timer = setInterval(() => {
      setIsTraveling(true);
      // Breve transición de warp antes de cambiar el contenido
      const warpTimeout = setTimeout(() => {
        setCurrentStepIndex(prev => (prev + 1) % MISSION_LEGS.length);
        setIsTraveling(false);
      }, 1600);

      return () => clearTimeout(warpTimeout);
    }, 7500);

    return () => clearInterval(timer);
  }, [isAutoPlaying, currentStepIndex]);

  // Selección manual de paso del ciclo
  const jumpToStep = (index: number) => {
    if (index === currentStepIndex) return;
    setIsTraveling(true);
    setTimeout(() => {
      setCurrentStepIndex(index);
      setIsTraveling(false);
    }, 800);
  };

  return (
    <div className="rl-landing">
      {/* ── FONDO CINEMÁTICO 3D EN CICLO AUTOMÁTICO ── */}
      <div className="rl-canvas-bg">
        <CinematicJourney
          activePlanet={step.planet}
          isTraveling={isTraveling}
        />
        <div className="rl-canvas-vignette" />
      </div>

      {/* ── BARRA DE NAVEGACIÓN CON LOGO OFICIAL ── */}
      <nav className="rl-nav">
        <div className="rl-nav-inner">
          <div className="rl-logo-wrap">
            <img
              src="/regolith-lockup-noche.png"
              alt="Regolith Atlas · No sky is the limit"
              className="rl-official-logo"
            />
            <span className="rl-slogan-badge">
              Tres cuerpos, un mismo suelo.
            </span>
          </div>

          <div className="rl-nav-links">
            <a href="#gancho">EL RETO</a>
            <a href="#match">ANÁLOGOS 3D</a>
            <a href="#instrumentos">INSTRUMENTOS</a>
            <a href="#ciencia">METODOLOGÍA</a>
          </div>

          <button className="rl-btn-launch" onClick={onStart}>
            INICIAR ATLAS <ChevronRight size={15} />
          </button>
        </div>
      </nav>

      {/* ═══════════════════════════════════════════
          HERO: CINEMÁTICA AUTOMATIZADA
      ═══════════════════════════════════════════ */}
      <section className="rl-hero">
        <div className="rl-hero-inner">
          {/* Contenido dinámico según el paso del ciclo */}
          <div className="rl-hero-text">
            {/* Barra de progreso de la misión automática */}
            <div className="rl-mission-cycle-bar">
              <div className="rl-cycle-label">
                <Orbit size={13} className="text-gold" />
                <span>VIAJE CINEMÁTICO AUTOMÁTICO</span>
                <button
                  className="rl-pause-toggle"
                  onClick={() => setIsAutoPlaying(p => !p)}
                  title={isAutoPlaying ? 'Pausar ciclo' : 'Reanudar ciclo'}
                >
                  {isAutoPlaying ? <Pause size={12} /> : <Play size={12} />}
                </button>
              </div>

              <div className="rl-cycle-steps">
                {MISSION_LEGS.map((leg, idx) => {
                  const isActive = idx === currentStepIndex;
                  return (
                    <button
                      key={leg.id}
                      className={`rl-cycle-step-btn ${isActive ? 'rl-cycle-step-btn--active' : ''}`}
                      onClick={() => jumpToStep(idx)}
                    >
                      <span className="step-num">{idx + 1}</span>
                      <span className="step-name">{leg.planet.toUpperCase()}</span>
                      {isActive && (
                        <motion.div
                          className="step-progress-indicator"
                          layoutId="step-prog"
                          style={{ background: leg.accentColor }}
                        />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Texto animado del Hero */}
            <AnimatePresence mode="wait">
              <motion.div
                key={step.id}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.5 }}
                className="rl-hero-anim-block"
              >
                <div className="rl-status-badge">
                  <span className="rl-pulse" style={{ background: step.accentColor }} />
                  <span style={{ color: step.accentColor }}>{step.legTag}</span>
                </div>

                <h1 className="rl-title">
                  {step.titleMain} <br />
                  <span style={{ color: step.accentColor }}>{step.titleAcc}</span>
                </h1>

                <p className="rl-desc">{step.desc}</p>

                {/* Tarjeta de contexto del lugar */}
                <div className="rl-meta-card">
                  <div className="rl-meta-item">
                    <MapPin size={16} style={{ color: step.accentColor, flexShrink: 0 }} />
                    <div>
                      <span className="rl-meta-label">LUGAR Y COORDENADAS</span>
                      <span className="rl-meta-value">{step.siteName}</span>
                    </div>
                  </div>
                  <div className="rl-meta-divider" />
                  <div className="rl-meta-item">
                    <Info size={16} style={{ color: step.accentColor, flexShrink: 0 }} />
                    <div>
                      <span className="rl-meta-label">OBJETIVO DE MISIÓN</span>
                      <span className="rl-meta-value">{step.siteMission}</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            </AnimatePresence>

            {/* CTAs */}
            <div className="rl-ctas">
              <button className="rl-btn-primary" onClick={onStart}>
                EXPLORAR ATLAS COMPLETO
              </button>
              <button
                className="rl-btn-secondary"
                onClick={() => document.getElementById('match')?.scrollIntoView({ behavior: 'smooth' })}
              >
                VER ANÁLOGO TEXTURIZADO 3D
              </button>
            </div>
          </div>

          {/* Estadísticas clave del proyecto */}
          <div className="rl-hero-stats">
            <div className="rl-stat-card">
              <BarChart3 size={22} className="text-gold" />
              <div>
                <span className="rl-stat-num text-gold">3.000+</span>
                <span className="rl-stat-desc">Zonas terrestres analizadas</span>
              </div>
            </div>
            <div className="rl-stat-card">
              <Layers size={22} className="text-gold" />
              <div>
                <span className="rl-stat-num text-gold">6</span>
                <span className="rl-stat-desc">Instrumentos NASA y ESA fusionados</span>
              </div>
            </div>
            <div className="rl-stat-card">
              <Zap size={22} className="text-gold" />
              <div>
                <span className="rl-stat-num text-gold">Δ 1.5°</span>
                <span className="rl-stat-desc">Diferencia de pendiente Utah vs Jezero</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          GANCHO Y EL RETO CIENTÍFICO (DEL PITCH)
      ═══════════════════════════════════════════ */}
      <section id="gancho" className="rl-pitch-hook-section">
        <div className="rl-container">
          <div className="rl-section-header">
            <span className="rl-eyebrow">EL RETO CIENTÍFICO</span>
            <h2>Ser famoso no garantiza ser un <span className="rl-gold">análogo real.</span></h2>
            <p>
              Antes de ir a Marte o la Luna, todo se prueba aquí en la Tierra. Pero si el terreno difiere al evaluar un rover, lo aprendido aquí no sirve allá.
            </p>
          </div>

          <div className="rl-pitch-cards-grid">
            <div className="rl-pitch-card">
              <div className="pitch-badge pitch-badge--warning">EL ANÁLOGO MÁS FAMOSO</div>
              <h3>Desierto de Atacama, Chile</h3>
              <p>
                Mundialmente citado por su aridez extrema. Sin embargo, al medir la inclinación de sus laderas respecto al punto donde aterrizó Perseverance en Jezero, <strong>Atacama se alejó en promedio 5.0°</strong> del cráter marciano.
              </p>
              <div className="pitch-delta-visual error">
                <span>Desvío de laderas:</span>
                <strong>Δ 5.0°</strong>
              </div>
            </div>

            <div className="rl-pitch-card rl-pitch-card--highlight">
              <div className="pitch-badge pitch-badge--success">EL ANÁLOGO MÁS PRECISO</div>
              <h3>Desierto de Utah, EE.UU.</h3>
              <p>
                Menos famoso que Atacama, pero sus abanicos sedimentarios se alejan <strong>solo 1.5° de Jezero</strong>. Ofrece una superficie mucho más representativa para ensayar tracción, pendientes y movilidad.
              </p>
              <div className="pitch-delta-visual success">
                <span>Desvío de laderas:</span>
                <strong>Δ 1.5°</strong>
              </div>
            </div>

            <div className="rl-pitch-card">
              <div className="pitch-badge pitch-badge--info">ANÁLOGOS VOLCÁNICOS</div>
              <h3>Volcán Cerro Negro, Nicaragua</h3>
              <p>
                Científicos con apoyo de la NASA han estudiado este volcán joven porque sus piroclastos y rocas basálticas se asemejan a los basaltos de Marte, aportando datos de textura y mineralogía.
              </p>
              <div className="pitch-delta-visual info">
                <span>Aporte clave:</span>
                <strong>Basaltos y rocas</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          ENCUENTRO ANALÓGICO PERFECTO: 3D TEXTURIZADO CON PROFUNDIDAD
      ═══════════════════════════════════════════ */}
      <section id="match" className="rl-textured-match-section">
        <div className="rl-container">
          <div className="rl-section-header">
            <span className="rl-eyebrow">ENCUENTRO ANALÓGICO PERFECTO</span>
            <h2>Topografía 3D con <span className="rl-gold">Relieve y Profundidad</span></h2>
            <p>
              Compara dos terrenos en bloques 3D interactivos con elevación real, sombreado solar y curvas de nivel. Sin consumir datos de API externa.
            </p>
          </div>

          {/* Componente 3D Texturizado */}
          <MockMatchPanel />
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          LOS 6 INSTRUMENTOS DE LA NASA Y ESA
      ═══════════════════════════════════════════ */}
      <section id="instrumentos" className="rl-instruments-section">
        <div className="rl-container">
          <div className="rl-section-header">
            <span className="rl-eyebrow">FUSIÓN MULTIFUENTE</span>
            <h2>Seis instrumentos espaciales, <span className="rl-gold">un solo mapa</span></h2>
            <p>
              Regolith mide la Tierra, la Luna y Marte con las mismas reglas en una cuadrícula unificada de 1,8 km.
            </p>
          </div>

          <div className="rl-instruments-grid">
            {INSTRUMENTS.map((inst) => (
              <div key={inst.name} className="rl-instrument-card">
                <div className="inst-icon-wrap">🛰️</div>
                <h4>{inst.name}</h4>
                <p>{inst.role}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          PILARES CIENTÍFICOS
      ═══════════════════════════════════════════ */}
      <section id="ciencia" className="rl-pillars-section">
        <div className="rl-container">
          <div className="rl-section-header">
            <span className="rl-eyebrow">METODOLOGÍA TRANSPARENTE</span>
            <h2>Rigor científico sin <span className="rl-gold">cajas negras</span></h2>
          </div>
          <div className="rl-pillars-grid">
            <div className="rl-pillar">
              <div className="rl-pillar-icon">📏</div>
              <h3>Misma Ventana Espacial</h3>
              <p>
                Comparamos ventanas estandarizadas de 1,8 km con resolución de celda de 60 m y 120 m. Nunca comparamos una montaña entera contra un metro cuadrado.
              </p>
            </div>
            <div className="rl-pillar">
              <div className="rl-pillar-icon">⚖️</div>
              <h3>Sin Ponderaciones Falsas</h3>
              <p>
                No inventamos una nota del 1 al 10 mezclando pendiente y minerales arbitrariamente. Declaramos la diferencia exacta en cada dimensión por separado.
              </p>
            </div>
            <div className="rl-pillar">
              <div className="rl-pillar-icon">🔍</div>
              <h3>Honestidad con lo Desconocido</h3>
              <p>
                Lo que falta por medir (polvo fino, hielo subsuperficial) se declara abiertamente como "sin evaluar", evitando falsas certezas en misiones críticas.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          FOOTER Y CIERRE CON EL ESLOGAN
      ═══════════════════════════════════════════ */}
      <footer className="rl-footer">
        <div className="rl-footer-cta">
          <span className="rl-footer-motto">TRES CUERPOS, UN MISMO SUELO.</span>
          <h2>Nuestro sistema no pregunta qué lugar es famoso, sino cuál es análogo de verdad.</h2>
          <p>Proyecto de código abierto para agencias espaciales, universidades y la ciencia global.</p>
          <button className="rl-btn-launch-lg" onClick={onStart}>
            INGRESAR AL ATLAS INTERACTIVO <ChevronRight size={18} />
          </button>
        </div>

        <div className="rl-footer-bottom">
          <div className="rl-container">
            <div className="rl-footer-row">
              <div className="rl-footer-brand">
                <img src="/regolith-lockup-noche.png" alt="Regolith" className="rl-footer-logo" />
                <span>© 2026 REGOLITH ATLAS · TRES CUERPOS, UN MISMO SUELO.</span>
              </div>
              <div className="rl-footer-links">
                <a href="#gancho">EL RETO</a>
                <a href="#match">ANÁLOGOS 3D</a>
                <a href="#instrumentos">INSTRUMENTOS</a>
                <button className="rl-link-btn" onClick={onStart}>ACCEDER AL ATLAS</button>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
