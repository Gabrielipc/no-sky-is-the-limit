import { useState, useEffect, useRef } from 'react';
import { ArrowRight, Pause, Play } from 'lucide-react';
import { CinematicJourney, PLANET_COLORS } from './CinematicJourney';
import { MockMatchPanel } from './MockMatchPanel';
import './LandingPage.css';

const PLANETS = [
  { id: 'earth' as const, label: 'Tierra', color: PLANET_COLORS.earth },
  { id: 'mars' as const, label: 'Marte', color: PLANET_COLORS.mars },
  { id: 'moon' as const, label: 'Luna', color: PLANET_COLORS.moon },
];

export function LandingPage({ onStart }: { onStart: () => void }) {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [isTraveling, setIsTraveling] = useState(false);
  const [isAutoPlaying, setIsAutoPlaying] = useState(() => {
    if (typeof window === 'undefined') return true;
    return !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });

  const timeoutsRef = useRef<number[]>([]);

  const clearScheduled = () => {
    for (const id of timeoutsRef.current) {
      window.clearTimeout(id);
    }
    timeoutsRef.current = [];
  };

  const transitionToIndex = (nextIndex: number) => {
    clearScheduled();
    const reduced =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (reduced) {
      setIsTraveling(false);
      setCurrentStepIndex(nextIndex);
      return;
    }

    setIsTraveling(true);
    const t1 = window.setTimeout(() => {
      setCurrentStepIndex(nextIndex);
      const t2 = window.setTimeout(() => {
        setIsTraveling(false);
      }, 900);
      timeoutsRef.current.push(t2);
    }, 1100);
    timeoutsRef.current.push(t1);
  };

  useEffect(() => {
    if (!isAutoPlaying) {
      return clearScheduled;
    }

    const intervalId = window.setInterval(() => {
      setIsTraveling(true);
      const t1 = window.setTimeout(() => {
        setCurrentStepIndex((prev) => (prev + 1) % PLANETS.length);
        const t2 = window.setTimeout(() => {
          setIsTraveling(false);
        }, 900);
        timeoutsRef.current.push(t2);
      }, 1200);
      timeoutsRef.current.push(t1);
    }, 7000);

    return () => {
      window.clearInterval(intervalId);
      clearScheduled();
    };
  }, [isAutoPlaying]);

  const activePlanet = PLANETS[currentStepIndex];

  const handleSelectPlanet = (idx: number) => {
    if (idx === currentStepIndex) return;
    setIsAutoPlaying(false);
    transitionToIndex(idx);
  };

  return (
    <div className="rl-landing">
      {/* Fondo espacial 3D */}
      <div className="rl-canvas-bg" aria-hidden="true">
        <CinematicJourney activePlanet={activePlanet.id} isTraveling={isTraveling} />
        <div className="rl-canvas-vignette" />
      </div>

      {/* Navegación superior minimalista */}
      <header className="rl-nav">
        <div className="rl-nav-inner">
          <a href="#inicio" className="rl-logo-link" aria-label="Regolith, inicio">
            <img
              src={`${import.meta.env.BASE_URL}regolith-lockup-noche.png`}
              alt="Regolith"
              className="rl-official-logo"
            />
          </a>

          <nav className="rl-nav-links" aria-label="Secciones de la página">
            <a href="#relato">El reto</a>
            <a href="#reglas">Mismas reglas</a>
            <a href="#impacto">Misión abierta</a>
          </nav>

          <button type="button" className="rl-btn-launch" onClick={onStart}>
            Abrir Atlas
          </button>
        </div>
      </header>

      <main>
        {/* 1. HERO: MENSAJE INICIAL SOBRE EL LIENZO 3D */}
        <section id="inicio" className="rl-hero">
          <div className="rl-container rl-hero-layout">
            <div className="rl-hero-copy">
              <p className="rl-kicker">Tres cuerpos, un mismo suelo</p>

              <h1 className="rl-hero-title">
                Antes de ir a Marte o la Luna,{' '}
                <span className="rl-accent">todo se prueba primero aquí, en la Tierra.</span>
              </h1>

              <p className="rl-hero-lead">
                El espacio nunca había estado tan cerca como ahora. Pero si el terreno difiere mucho
                a la hora de evaluar cómo se desempeña un rover, puede que lo aprendido aquí no
                sirva de mucho allá.
              </p>

              <div className="rl-hero-actions">
                <button type="button" className="rl-btn-primary" onClick={onStart}>
                  <span>Explorar el atlas</span>
                  <ArrowRight size={16} aria-hidden="true" />
                </button>
                <a className="rl-btn-ghost" href="#relato">
                  Conocer la historia
                </a>
              </div>
            </div>

            {/* Indicador discreto de cuerpo celeste y pausa de animación */}
            <div className="rl-orbit-bar" aria-label="Vista orbital de fondo">
              <div className="rl-orbit-planets" role="group" aria-label="Seleccionar cuerpo celeste">
                {PLANETS.map((planet, idx) => {
                  const isActive = idx === currentStepIndex;
                  return (
                    <button
                      key={planet.id}
                      type="button"
                      aria-pressed={isActive}
                      className={`rl-orbit-btn ${isActive ? 'is-active' : ''}`}
                      onClick={() => handleSelectPlanet(idx)}
                    >
                      <span
                        className="rl-orbit-dot"
                        style={{ backgroundColor: planet.color }}
                        aria-hidden="true"
                      />
                      <span>{planet.label}</span>
                    </button>
                  );
                })}
              </div>

              <button
                type="button"
                className="rl-orbit-pause"
                onClick={() => setIsAutoPlaying((prev) => !prev)}
                aria-label={
                  isAutoPlaying
                    ? 'Pausar recorrido orbital automático'
                    : 'Reanudar recorrido orbital automático'
                }
              >
                {isAutoPlaying ? (
                  <>
                    <Pause size={12} aria-hidden="true" />
                    <span>Pausar</span>
                  </>
                ) : (
                  <>
                    <Play size={12} aria-hidden="true" />
                    <span>Reanudar</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </section>

        {/* 2. EL RETO: LA FAMA NO GARANTIZA PARECIDO */}
        <section id="relato" className="rl-section rl-story-section">
          <div className="rl-container">
            <div className="rl-story-hook">
              <span className="rl-eyebrow">El reto</span>
              <h2 className="rl-hook-statement">
                Ser una región famosa no garantiza parecerse al lugar exacto al que vamos.{' '}
                <span className="rl-accent">
                  Por eso Regolith mide esas diferencias antes de ensayar.
                </span>
              </h2>
            </div>

            <div className="rl-cases-grid">
              <article className="rl-case-item">
                <h3 className="rl-case-place">Nicaragua · Volcán Cerro Negro</h3>
                <p>
                  En Nicaragua: científicos con apoyo de la NASA han estudiado el volcán Cerro Negro
                  porque sus rocas se parecen a las de Marte.
                </p>
              </article>

              <article className="rl-case-item">
                <h3 className="rl-case-place">Atacama y Utah · Cráter Jezero</h3>
                <p>
                  El desierto de Atacama, en Chile, es uno de los lugares más citados por su
                  parecido con Marte. Pero cuando comparamos sus laderas con las de un sector del
                  cráter donde aterrizó Perseverance, encontramos que las de una zona de Utah se
                  parecían más.
                </p>
              </article>
            </div>
          </div>
        </section>

        {/* 3. MISMAS REGLAS Y DEMOSTRACIÓN VISUAL */}
        <section id="reglas" className="rl-section rl-rules-section">
          <div className="rl-container">
            <div className="rl-rules-header">
              <span className="rl-eyebrow">Mismas reglas</span>
              <h2>
                Regolith mide la Tierra, la Luna y Marte{' '}
                <span className="rl-accent">con las mismas reglas.</span>
              </h2>
              <p className="rl-section-lead">
                Fusionamos miles de datos de seis instrumentos de la NASA, desde sus misiones a
                Marte, la Luna y la Estación Espacial Internacional, hasta los modelos de la Agencia
                Espacial Europea. Ponemos todo en un mismo mapa y comparamos lo que más le importa a
                un rover o a los próximos habitantes lunares y marcianos:
              </p>
            </div>

            <ol className="rl-axes-list">
              <li className="rl-axis-item">
                <span className="rl-axis-num" aria-hidden="true">01</span>
                <h3>La inclinación del terreno</h3>
              </li>
              <li className="rl-axis-item">
                <span className="rl-axis-num" aria-hidden="true">02</span>
                <h3>Qué tan accidentado es</h3>
              </li>
              <li className="rl-axis-item">
                <span className="rl-axis-num" aria-hidden="true">03</span>
                <h3>Los minerales que lo componen</h3>
              </li>
            </ol>

            <MockMatchPanel />
          </div>
        </section>

        {/* 4. COMUNIDAD Y SOSTENIBILIDAD */}
        <section id="impacto" className="rl-section rl-open-section">
          <div className="rl-container">
            <div className="rl-open-header">
              <span className="rl-eyebrow">Misión abierta</span>
              <h2>Abierto, reproducible y sin fines de lucro.</h2>
            </div>

            <div className="rl-open-grid">
              <article className="rl-open-item">
                <h3>Para quiénes construimos</h3>
                <p>
                  El sistema está dirigido a equipos de misión que buscan dónde ensayar,
                  universidades que estudian otros planetas y países como el nuestro, que pueden
                  aportar sitios y datos. Todo es abierto y reproducible.
                </p>
              </article>

              <article className="rl-open-item">
                <h3>Cómo crece la plataforma</h3>
                <p>
                  Regolith es una plataforma sin fines de lucro, con código abierto. Para crecer,
                  proponemos alianzas con agencias espaciales, fondos canalizados por un socio
                  internacional y el apoyo de universidades.
                </p>
              </article>
            </div>
          </div>
        </section>
      </main>

      {/* 5. CIERRE DEL PITCH */}
      <footer className="rl-footer">
        <div className="rl-container rl-footer-closing">
          <p className="rl-closing-question">
            Nuestro sistema no pregunta qué lugar es famoso, sino cuál es análogo de verdad.
          </p>
          <h2 className="rl-closing-step">
            El próximo paso en otro mundo empieza aquí,{' '}
            <span className="rl-accent">en el lugar correcto de la Tierra.</span>
          </h2>
          <p className="rl-closing-motto">Regolith; tres cuerpos, un mismo suelo.</p>

          <button type="button" className="rl-btn-primary rl-btn-primary--lg" onClick={onStart}>
            <span>Explorar el atlas</span>
            <ArrowRight size={17} aria-hidden="true" />
          </button>
        </div>

        <div className="rl-footer-bottom">
          <div className="rl-container rl-footer-row">
            <div className="rl-footer-brand">
              <img
                src={`${import.meta.env.BASE_URL}regolith-lockup-noche.png`}
                alt="Regolith"
                className="rl-footer-logo"
              />
              <span>Tres cuerpos, un mismo suelo.</span>
            </div>

            <div className="rl-footer-links">
              <a href="#relato">El reto</a>
              <a href="#reglas">Mismas reglas</a>
              <a href="#impacto">Misión abierta</a>
              <button type="button" className="rl-link-btn" onClick={onStart}>
                Abrir Atlas
              </button>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
