import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ChevronRight, MapPin, Info, Shield,
  BarChart3, Layers, Zap, ArrowRight, Globe2,
  Orbit, Compass
} from 'lucide-react';
import { CinematicJourney } from './CinematicJourney';
import { MockMatchPanel } from './MockMatchPanel';
import './LandingPage.css';

// ── Ciclo de Misión Automático: Tierra -> Marte -> Luna -> Tierra ──
const MISSION_LEGS = [
  {
    id: 'earth',
    planet: 'earth' as const,
    legTag: '1 · TIERRA · ORIGEN',
    titleMain: 'Antes de ir al espacio,',
    titleAcc: 'todo se prueba aquí.',
    desc: 'Los rovers y hábitats deben probarse en la Tierra antes de volar. Regolith mide la forma del terreno y los minerales para encontrar análogos cuantitativos exactos.',
    siteName: 'Desierto de Utah (Morrison) y Atacama (Chile)',
    siteMission: 'Evaluar tracción, pendientes y movilidad antes de construir una misión.',
    accentColor: '#4a9eff',
  },
  {
    id: 'mars',
    planet: 'mars' as const,
    legTag: '2 · MARTE · DESTINO',
    titleMain: 'Cráter Jezero,',
    titleAcc: 'donde opera Perseverance.',
    desc: 'Buscamos rastros de vida pasada en el delta del cráter marciano. La inclinación de sus laderas exige rovers probados en pendientes rigurosamente equivalentes.',
    siteName: 'Delta del Cráter Jezero · 18.4°N, 77.7°E',
    siteMission: 'Medir diferencias de pendiente con datos de NASA HiRISE y MOLA.',
    accentColor: '#e05222',
  },
  {
    id: 'moon',
    planet: 'moon' as const,
    legTag: '3 · LA LUNA · ARTEMIS',
    titleMain: 'Polo Sur Lunar,',
    titleAcc: 'misión Artemis.',
    desc: 'Cráteres profundos y sombras permanentes donde se oculta hielo de agua. Caracterizamos la rugosidad del regolito polar para los próximos pasos humanos.',
    siteName: 'Cráter Shackleton · Polo Sur Lunar 89.9°S',
    siteMission: 'Entrenar astronautas y sensores ópticos en análogos terrestres.',
    accentColor: '#d0d4d8',
  },
];

// 6 Instrumentos espaciales integrados
const INSTRUMENTS = [
  { name: 'NASA HiRISE', role: 'Imágenes métricas de ultra-resolución marciana' },
  { name: 'NASA MOLA', role: 'Topografía láser orbital del planeta Marte' },
  { name: 'NASA LRO LOLA', role: 'Altímetro láser polar lunar' },
  { name: 'NASA CRISM', role: 'Espectrometría de minerales y arcillas' },
  { name: 'NASA EMIT (ISS)', role: 'Firmas espectrales terrestres desde la estación espacial' },
  { name: 'Copernicus GLO-30', role: 'Modelo digital de elevación global ESA' },
];

export function LandingPage({ onStart }: { onStart: () => void }) {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [isTraveling, setIsTraveling] = useState(false);

  const step = MISSION_LEGS[currentStepIndex];

  // ── INICIO AUTOMÁTICO INMEDIATO AL CARGAR LA WEB (SIN BOTONES) ──
  useEffect(() => {
    const timer = setInterval(() => {
      setIsTraveling(true);
      setTimeout(() => {
        setCurrentStepIndex(prev => (prev + 1) % MISSION_LEGS.length);
        setTimeout(() => {
          setIsTraveling(false);
        }, 900);
      }, 1400);
    }, 7200);

    return () => clearInterval(timer);
  }, []);

  return (
    <div className="rl-landing">
      {/* ── FONDO CINEMÁTICO 3D EN CICLO AUTOMÁTICO INMEDIATO ── */}
      <div className="rl-canvas-bg">
        <CinematicJourney
          activePlanet={step.planet}
          isTraveling={isTraveling}
        />
        <div className="rl-canvas-vignette" />
      </div>

      {/* ── BARRA DE NAVEGACIÓN CON LOGO Y ESLOGAN ── */}
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
            <a href="#matching">MOTOR DE ANÁLOGOS</a>
            <a href="#solucion">SOLUCIÓN</a>
            <a href="#impacto">IMPACTO</a>
          </div>

          <button className="rl-btn-launch" onClick={onStart}>
            INICIAR ATLAS <ChevronRight size={15} />
          </button>
        </div>
      </nav>

      {/* ═══════════════════════════════════════════
          HERO: CICLO CINEMÁTICO AUTOMÁTICO
      ═══════════════════════════════════════════ */}
      <section className="rl-hero">
        <div className="rl-hero-inner">
          <div className="rl-hero-text">
            {/* Indicador de misión automática */}
            <div className="rl-mission-cycle-bar">
              <div className="rl-cycle-label">
                <Orbit size={13} className="text-gold" />
                <span>VIAJE INTERPLANETARIO AUTOMÁTICO</span>
              </div>

              <div className="rl-cycle-steps">
                {MISSION_LEGS.map((leg, idx) => {
                  const isActive = idx === currentStepIndex;
                  return (
                    <div
                      key={leg.id}
                      className={`rl-cycle-step-btn ${isActive ? 'rl-cycle-step-btn--active' : ''}`}
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
                    </div>
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
                EXPLORAR ANÁLOGOS
              </button>
              <button
                className="rl-btn-secondary"
                onClick={() => document.getElementById('matching')?.scrollIntoView({ behavior: 'smooth' })}
              >
                VER CÓMO FUNCIONA EL MOTOR
              </button>
            </div>
          </div>

          {/* Estadísticas visuales del Atlas */}
          <div className="rl-hero-stats">
            <div className="rl-stat-card">
              <BarChart3 size={24} className="text-gold" />
              <div>
                <span className="rl-stat-num text-gold">3.000+</span>
                <span className="rl-stat-desc">Zonas planetarias revisadas</span>
              </div>
            </div>
            <div className="rl-stat-card">
              <Layers size={24} className="text-gold" />
              <div>
                <span className="rl-stat-num text-gold">6</span>
                <span className="rl-stat-desc">Instrumentos NASA y ESA fusionados</span>
              </div>
            </div>
            <div className="rl-stat-card">
              <Zap size={24} className="text-gold" />
              <div>
                <span className="rl-stat-num text-gold">Δ 1.5°</span>
                <span className="rl-stat-desc">Diferencia de pendiente Utah vs Jezero</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          SLIDE 1 & 2 · EL GANCHO Y EL RETO CIENTÍFICO
      ═══════════════════════════════════════════ */}
      <section id="gancho" className="rl-problem-section">
        <div className="rl-container">
          <div className="rl-section-header">
            <span className="rl-eyebrow">EL DESAFÍO CIENTÍFICO</span>
            <h2>La fama no garantiza la <span className="rl-gold">exactitud.</span></h2>
            <p>
              Antes de ir a Marte, todo se prueba primero aquí, en la Tierra. Pero si el terreno difiere al evaluar cómo se desempeña un rover, lo aprendido aquí no servirá allá.
            </p>
          </div>

          <div className="rl-pitch-cards-grid">
            <div className="rl-pitch-card">
              <div className="pitch-badge pitch-badge--warning">EL MÁS FAMOSO (ALTO ERROR)</div>
              <h3>Desierto de Atacama, Chile</h3>
              <p>
                Mundialmente citado por su aridez. Pero comparándolo con el sector del cráter donde aterrizó el rover Perseverance, <strong>la inclinación de sus laderas se alejó en promedio 5 grados</strong> del cráter marciano, dificultando la misión.
              </p>
              <div className="pitch-delta-visual error">
                <span>Diferencia de laderas:</span>
                <strong>Δ 5.0°</strong>
              </div>
            </div>

            <div className="rl-pitch-card rl-pitch-card--highlight">
              <div className="pitch-badge pitch-badge--success">EL MÁS EXACTO (DESCUBIERTO)</div>
              <h3>Desierto de Utah, EE.UU.</h3>
              <p>
                Menos famoso que Atacama, pero sus laderas se alejan <strong>solo 1.5 grados de Jezero</strong>. Ofrece las condiciones cuantitativas precisas para evaluar tracción y movilidad antes de enviar un rover al espacio.
              </p>
              <div className="pitch-delta-visual success">
                <span>Diferencia de laderas:</span>
                <strong>Δ 1.5°</strong>
              </div>
            </div>

            <div className="rl-pitch-card">
              <div className="pitch-badge pitch-badge--info">ANÁLOGOS VOLCÁNICOS</div>
              <h3>Volcán Cerro Negro, Nicaragua</h3>
              <p>
                En Nicaragua: científicos con apoyo de la NASA han estudiado el volcán Cerro Negro porque sus rocas y piroclastos basálticos se parecen a los de Marte, aportando datos clave sobre tipos de roca y regolito.
              </p>
              <div className="pitch-delta-visual info">
                <span>Aporte geológico:</span>
                <strong>Basaltos análogos</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          MOTOR DE COINCIDENCIAS (TAL COMO ESTABA PERO LO MÁS REALISTA POSIBLE)
      ═══════════════════════════════════════════ */}
      <section id="matching" className="matching-section">
        <div className="rl-container">
          <div className="rl-section-header">
            <span className="rl-eyebrow">TECNOLOGÍA REGOLITH</span>
            <h2>Motor de <span className="rl-gold">Coincidencias</span></h2>
            <p>Algoritmos avanzados que conectan mundos a través de su geología real.</p>
          </div>

          {/* Componente del motor como estaba, con imágenes de satélite y escáner láser */}
          <MockMatchPanel />
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          SLIDE 3 · SOLUCIÓN: FUSIÓN DE 6 INSTRUMENTOS
      ═══════════════════════════════════════════ */}
      <section id="solucion" className="rl-instruments-section">
        <div className="rl-container">
          <div className="rl-section-header">
            <span className="rl-eyebrow">LA SOLUCIÓN</span>
            <h2>Tres cuerpos medidos con las <span className="rl-gold">mismas reglas</span></h2>
            <p>
              Fusionamos cientos de datos de seis instrumentos de la NASA (en sus misiones a Marte, la Luna y la ISS) junto con modelos de la Agencia Espacial Europea.
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
          SLIDE 4 & 5 · RESULTADO E IMPACTO
      ═══════════════════════════════════════════ */}
      <section id="impacto" className="rl-pillars-section">
        <div className="rl-container">
          <div className="rl-section-header">
            <span className="rl-eyebrow">IMPACTO Y SOSTENIBILIDAD</span>
            <h2>Ciencia abierta para <span className="rl-gold">misiones reales</span></h2>
          </div>
          <div className="rl-pillars-grid">
            <div className="rl-pillar">
              <div className="rl-pillar-icon">🚀</div>
              <h3>Equipos de Misión y Universidades</h3>
              <p>
                Diseñado para científicos que planifican rutas de rovers, universidades que estudian geología planetaria y países como el nuestro que pueden aportar sitios y datos.
              </p>
            </div>
            <div className="rl-pillar">
              <div className="rl-pillar-icon">🌐</div>
              <h3>Código Abierto y Sostenible</h3>
              <p>
                Funciona como una organización sin fines de lucro. Mantener la plataforma en línea cuesta menos de 1.700 dólares al año, financiada mediante convenios con agencias y universidades.
              </p>
            </div>
            <div className="rl-pillar">
              <div className="rl-pillar-icon">⚖️</div>
              <h3>Rigor y Transparencia</h3>
              <p>
                Sin cajas negras ni notas arbitrarias. Declaramos lo medido y somos honestos con lo que falta: rocas, polvo, hielo y análisis más fino de la Luna.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          SLIDE 6 · CIERRE CON EL ESLOGAN OFICIAL
      ═══════════════════════════════════════════ */}
      <footer className="rl-footer">
        <div className="rl-footer-cta">
          <span className="rl-footer-motto">TRES CUERPOS, UN MISMO SUELO.</span>
          <h2>Nuestro sistema no pregunta qué lugar es famoso, sino cuál es análogo de verdad.</h2>
          <p>Proyecto de código abierto · NASA Space Apps Challenge</p>
          <button className="rl-btn-launch-lg" onClick={onStart}>
            ACCEDER AL ATLAS COMPLETO <ChevronRight size={18} />
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
                <a href="#matching">MOTOR DE ANÁLOGOS</a>
                <a href="#solucion">SOLUCIÓN</a>
                <button className="rl-link-btn" onClick={onStart}>INICIAR ATLAS</button>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
