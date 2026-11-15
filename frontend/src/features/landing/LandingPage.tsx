import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Rocket, Globe as GlobeIcon, Zap, ChevronRight, MapPin, Layers, Target, Info, Shield, BarChart3 } from 'lucide-react';
import { CinematicJourney } from './CinematicJourney';
import './LandingPage.css';

const PLANETS_DATA = {
  earth: {
    title: 'PLANETA TIERRA',
    subtitle: 'El Análogo Maestro',
    description: 'Nuestra base de operaciones donde la geología terrestre nos enseña sobre el cosmos.',
    color: '#4a9eff',
    site: 'Desierto de Utah, EE.UU.',
    pitch: 'Donde el regolito se encuentra con la geología terrestre.'
  },
  moon: {
    title: 'LA LUNA',
    subtitle: 'Puerta a las Estrellas',
    description: 'El próximo gran salto de la humanidad. Cráteres y regolito esperando ser explorados.',
    color: '#ffffff',
    site: 'Polo Sur Lunar (Artemis)',
    pitch: 'El próximo salto de la humanidad comienza aquí.'
  },
  mars: {
    title: 'MARTE',
    subtitle: 'El Planeta Rojo',
    description: 'Buscando rastros de vida antigua en el Cráter Jezero y más allá.',
    color: '#ff6b4a',
    site: 'Cráter Jezero',
    pitch: 'Buscando rastros de vida en el suelo rojo.'
  }
};

const MATCH_EXAMPLES = [
  { earth: 'Desierto de Utah', space: 'Cráter Jezero', type: 'Marte', similarity: 94, img: '/analysis/utah-context.png' },
  { earth: 'Desierto de Atacama', space: 'Cráter Shackleton', type: 'Luna', similarity: 88, img: '/analysis/utah-context.png' },
  { earth: 'Volcanes de Islandia', space: 'Olympus Mons', type: 'Marte', similarity: 82, img: '/analysis/utah-context.png' },
];

export function LandingPage({ onStart }: { onStart: () => void }) {
  const [currentPlanet, setCurrentPlanet] = useState('earth');
  const [activeMatch, setActiveMatch] = useState(0);
  const [isMatchingAuto, setIsMatchingAuto] = useState(true);

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentPlanet(prev => {
        if (prev === 'earth') return 'moon';
        if (prev === 'moon') return 'mars';
        return 'earth';
      });
    }, 10000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (isMatchingAuto) {
      const timer = setInterval(() => {
        setActiveMatch(prev => (prev + 1) % MATCH_EXAMPLES.length);
      }, 5000);
      return () => clearInterval(timer);
    }
  }, [isMatchingAuto]);

  const planetInfo = PLANETS_DATA[currentPlanet as keyof typeof PLANETS_DATA];

  return (
    <div className="regolith-landing-v4">
      {/* 3D Background Journey */}
      <div className="journey-container">
        <CinematicJourney 
          currentPlanet={currentPlanet} 
          onPlanetSelect={(id) => setCurrentPlanet(id)} 
          isMatching={!isMatchingAuto}
        />
        <div className="journey-overlay" />
      </div>

      {/* Navigation */}
      <nav className="glass-nav">
        <div className="nav-content">
          <div className="logo-group">
            <div className="logo-icon-wrapper">
              <Rocket size={20} className="text-gold" />
            </div>
            <div className="logo-text-group">
              <span className="logo-text">REGOLITH</span>
              <span className="logo-tag">ATLAS 2.0</span>
            </div>
          </div>
          <div className="nav-links">
            <a href="#problem">EL RETO</a>
            <a href="#matching">MOTOR DE ANÁLOGOS</a>
            <a href="#pillars">CIENCIA</a>
          </div>
          <div className="nav-actions">
            <button className="btn-launch" onClick={onStart}>
              INICIAR ATLAS
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </nav>

      {/* Hero Content */}
      <main className="hero-section">
        <div className="hero-grid">
          <AnimatePresence mode="wait">
            <motion.div 
              key={currentPlanet}
              initial={{ opacity: 0, x: -30 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 30 }}
              transition={{ duration: 0.8 }}
              className="hero-text-content"
            >
              <div className="status-badge">
                <span className="pulse-dot" style={{ backgroundColor: planetInfo.color }} />
                {planetInfo.subtitle}
              </div>
              <h1 className="main-title">
                {planetInfo.title.split(' ')[0]} <br />
                <span className="text-gradient" style={{ '--target-color': planetInfo.color } as any}>
                  {planetInfo.title.split(' ').slice(1).join(' ')}
                </span>
              </h1>
              <p className="description">
                {planetInfo.description}
              </p>
              
              <div className="planet-meta-card">
                <div className="meta-item">
                  <MapPin size={18} className="text-gold" />
                  <div>
                    <span className="meta-label">SITIO ANÁLOGO</span>
                    <span className="meta-value">{planetInfo.site}</span>
                  </div>
                </div>
                <div className="meta-divider" />
                <div className="meta-item">
                  <Info size={18} className="text-gold" />
                  <div>
                    <span className="meta-label">MISIÓN</span>
                    <span className="meta-value">{planetInfo.pitch}</span>
                  </div>
                </div>
              </div>

              <div className="action-buttons">
                <button className="btn-primary" onClick={onStart}>
                  EXPLORAR ANÁLOGOS
                </button>
                <button className="btn-secondary" onClick={() => {
                  document.getElementById('matching')?.scrollIntoView({ behavior: 'smooth' });
                }}>
                  VER CÓMO FUNCIONA
                </button>
              </div>
            </motion.div>
          </AnimatePresence>

          <div className="hero-visual-stats">
            <div className="stat-card">
              <BarChart3 size={24} className="text-gold" />
              <div className="stat-info">
                <span className="stat-num">99.8%</span>
                <span className="stat-desc">Precisión de Datos</span>
              </div>
            </div>
            <div className="stat-card">
              <Layers size={24} className="text-gold" />
              <div className="stat-info">
                <span className="stat-num">15+</span>
                <span className="stat-desc">Sitios Terrestres</span>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Problem Section */}
      <section id="problem" className="problem-section">
        <div className="container">
          <div className="problem-header">
            <span className="eyebrow">EL DESAFÍO CIENTÍFICO</span>
            <h2>La fama no garantiza la <span className="text-gold">exactitud.</span></h2>
          </div>
          <div className="problem-grid-v4">
            <div className="problem-card">
              <div className="card-icon"><Shield size={32} /></div>
              <h3>Riesgo de Misión</h3>
              <p>Elegir un sitio análogo basado solo en la fama puede comprometer años de investigación.</p>
              <div className="comparison-visual">
                <div className="comp-item">
                  <span>Atacama vs Jezero</span>
                  <div className="comp-bar"><div className="fill error" style={{ width: '80%' }}></div></div>
                  <span className="comp-val">Δ 5.0°</span>
                </div>
                <div className="comp-item">
                  <span>Utah vs Jezero</span>
                  <div className="fill success" style={{ width: '20%' }}></div>
                  <span className="comp-val">Δ 1.5°</span>
                </div>
              </div>
            </div>
            <div className="problem-image-placeholder">
              <div className="wireframe-sphere">
                <div className="scanner-line" />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Matching Engine Section */}
      <section id="matching" className="matching-section">
        <div className="container">
          <div className="section-header-center">
            <span className="eyebrow">TECNOLOGÍA REGOLITH</span>
            <h2>Motor de <span className="text-gold">Coincidencias</span></h2>
            <p>Algoritmos avanzados que conectan mundos a través de su geología.</p>
          </div>

          <div className="match-visualizer-v4">
            <div className="match-controls">
              {MATCH_EXAMPLES.map((m, i) => (
                <button 
                  key={i}
                  className={`control-btn ${activeMatch === i ? 'active' : ''}`}
                  onClick={() => { setActiveMatch(i); setIsMatchingAuto(false); }}
                >
                  {m.earth} → {m.space}
                </button>
              ))}
            </div>

            <AnimatePresence mode="wait">
              <motion.div 
                key={activeMatch}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="match-display-card"
              >
                <div className="display-grid">
                  <div className="display-side earth">
                    <div className="side-tag">TIERRA</div>
                    <div className="side-img-container">
                      <img src="/analysis/utah-context.png" alt="Earth site" />
                      <div className="scan-effect" />
                    </div>
                    <h4>{MATCH_EXAMPLES[activeMatch].earth}</h4>
                  </div>

                  <div className="display-center">
                    <div className="similarity-gauge">
                      <svg viewBox="0 0 100 100">
                        <circle cx="50" cy="50" r="45" className="gauge-bg" />
                        <motion.circle 
                          cx="50" cy="50" r="45" 
                          className="gauge-progress"
                          initial={{ pathLength: 0 }}
                          animate={{ pathLength: MATCH_EXAMPLES[activeMatch].similarity / 100 }}
                          transition={{ duration: 1.5 }}
                        />
                      </svg>
                      <div className="gauge-text">
                        <span className="percent">{MATCH_EXAMPLES[activeMatch].similarity}%</span>
                        <span className="label">MATCH</span>
                      </div>
                    </div>
                    <div className="connection-line">
                      <motion.div 
                        className="line-flow"
                        initial={{ left: '-100%' }}
                        animate={{ left: '100%' }}
                        transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                      />
                    </div>
                  </div>

                  <div className="display-side space">
                    <div className="side-tag">{MATCH_EXAMPLES[activeMatch].type.toUpperCase()}</div>
                    <div className="side-img-container space-bg">
                      <Target size={40} className="text-gold" />
                      <div className="scan-effect invert" />
                    </div>
                    <h4>{MATCH_EXAMPLES[activeMatch].space}</h4>
                  </div>
                </div>

                <div className="match-analysis-details">
                  <div className="detail">
                    <Zap size={16} />
                    <span>Coincidencia Mineralógica: <strong>92%</strong></span>
                  </div>
                  <div className="detail">
                    <Layers size={16} />
                    <span>Similitud Topográfica: <strong>96%</strong></span>
                  </div>
                </div>
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </section>

      {/* Pillars Section */}
      <section id="pillars" className="pillars-section">
        <div className="container">
          <div className="pillars-grid">
            <div className="pillar-item">
              <div className="pillar-icon">📏</div>
              <h3>Escala Real</h3>
              <p>Comparamos terrenos con la misma ventana espacial y rampa unificada.</p>
            </div>
            <div className="pillar-item">
              <div className="pillar-icon">🛰️</div>
              <h3>Multifuente</h3>
              <p>Integramos datos de Copernicus, SRTM y HiRISE en un solo lugar.</p>
            </div>
            <div className="pillar-item">
              <div className="pillar-icon">⚖️</div>
              <h3>Rigor Científico</h3>
              <p>Declaramos los límites de los datos y la incertidumbre en cada modelo.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="footer-v4">
        <div className="footer-main">
          <div className="footer-cta">
            <h2>¿Listo para descubrir tu próximo análogo?</h2>
            <button className="btn-primary-large" onClick={onStart}>
              ACCEDER AL ATLAS COMPLETO
            </button>
          </div>
        </div>
        <div className="footer-bottom">
          <div className="container">
            <div className="bottom-content">
              <p>© 2026 PROYECTO REGOLITH · NASA SPACE APPS CHALLENGE</p>
              <div className="bottom-links">
                <a href="#">GITHUB</a>
                <a href="#">NASA PDS</a>
                <a href="#">METODOLOGÍA</a>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
