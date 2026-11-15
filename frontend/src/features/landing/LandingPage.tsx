import { useState, useEffect, useRef } from 'react';
import { ArrowRight, Pause, Play } from 'lucide-react';
import { CinematicJourney, PLANET_COLORS } from './CinematicJourney';
import { MockMatchPanel } from './MockMatchPanel';
import { LanguageSwitch, useI18n } from '../../i18n/I18nProvider';
import type { Msg } from '../../i18n/lang';
import './LandingPage.css';

const PLANETS: { id: 'earth' | 'mars' | 'moon'; label: Msg; color: string }[] = [
  { id: 'earth', label: ['Tierra', 'Earth'], color: PLANET_COLORS.earth },
  { id: 'mars', label: ['Marte', 'Mars'], color: PLANET_COLORS.mars },
  { id: 'moon', label: ['Luna', 'Moon'], color: PLANET_COLORS.moon },
];

export function LandingPage({ onStart }: { onStart: () => void }) {
  const { t } = useI18n();
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
          <a href="#inicio" className="rl-logo-link" aria-label={t('Regolith, inicio', 'Regolith, home')}>
            <img
              src={`${import.meta.env.BASE_URL}regolith-lockup-noche.png`}
              alt="Regolith"
              className="rl-official-logo"
            />
          </a>

          <nav className="rl-nav-links" aria-label={t('Secciones de la página', 'Page sections')}>
            <a href="#relato">{t('El reto', 'The challenge')}</a>
            <a href="#reglas">{t('Mismas reglas', 'Same rules')}</a>
            <a href="#impacto">{t('Misión abierta', 'Open mission')}</a>
          </nav>

          <div className="rl-nav-actions">
            <LanguageSwitch className="rl-lang" />
            <button type="button" className="rl-btn-launch" onClick={onStart}>
              {t('Abrir Atlas', 'Open Atlas')}
            </button>
          </div>
        </div>
      </header>

      <main>
        {/* 1. HERO: MENSAJE INICIAL SOBRE EL LIENZO 3D */}
        <section id="inicio" className="rl-hero">
          <div className="rl-container rl-hero-layout">
            <div className="rl-hero-copy">
              <p className="rl-kicker">{t('Tres cuerpos, un mismo suelo', 'Three bodies, one ground')}</p>

              <h1 className="rl-hero-title">
                {t('Antes de ir a Marte o la Luna,', 'Before going to Mars or the Moon,')}{' '}
                <span className="rl-accent">{t('todo se prueba primero aquí, en la Tierra.', 'everything is first tested here, on Earth.')}</span>
              </h1>

              <p className="rl-hero-lead">
                {t(
                  'El espacio nunca había estado tan cerca como ahora. Pero si el terreno difiere mucho a la hora de evaluar cómo se desempeña un rover, puede que lo aprendido aquí no sirva de mucho allá.',
                  'Space has never been as close as it is now. But if the terrain differs a lot when assessing how a rover performs, what we learn here may not be much use out there.',
                )}
              </p>

              <div className="rl-hero-actions">
                <button type="button" className="rl-btn-primary" onClick={onStart}>
                  <span>{t('Explorar el atlas', 'Explore the atlas')}</span>
                  <ArrowRight size={16} aria-hidden="true" />
                </button>
                <a className="rl-btn-ghost" href="#relato">
                  {t('Conocer la historia', 'Read the story')}
                </a>
              </div>
            </div>

            {/* Indicador discreto de cuerpo celeste y pausa de animación */}
            <div className="rl-orbit-bar" aria-label={t('Vista orbital de fondo', 'Background orbital view')}>
              <div className="rl-orbit-planets" role="group" aria-label={t('Seleccionar cuerpo celeste', 'Choose a celestial body')}>
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
                      <span>{t(...planet.label)}</span>
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
                    ? t('Pausar recorrido orbital automático', 'Pause the automatic orbital tour')
                    : t('Reanudar recorrido orbital automático', 'Resume the automatic orbital tour')
                }
              >
                {isAutoPlaying ? (
                  <>
                    <Pause size={12} aria-hidden="true" />
                    <span>{t('Pausar', 'Pause')}</span>
                  </>
                ) : (
                  <>
                    <Play size={12} aria-hidden="true" />
                    <span>{t('Reanudar', 'Resume')}</span>
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
              <span className="rl-eyebrow">{t('El reto', 'The challenge')}</span>
              <h2 className="rl-hook-statement">
                {t(
                  'Ser una región famosa no garantiza parecerse al lugar exacto al que vamos.',
                  'Being a famous region does not guarantee resembling the exact place we are going to.',
                )}{' '}
                <span className="rl-accent">
                  {t('Por eso Regolith mide esas diferencias antes de ensayar.', 'That is why Regolith measures those differences before testing.')}
                </span>
              </h2>
            </div>

            <div className="rl-cases-grid">
              <article className="rl-case-item">
                <h3 className="rl-case-place">{t('Nicaragua · Volcán Cerro Negro', 'Nicaragua · Cerro Negro Volcano')}</h3>
                <p>
                  {t(
                    'En Nicaragua: científicos con apoyo de la NASA han estudiado el volcán Cerro Negro porque sus rocas se parecen a las de Marte.',
                    'In Nicaragua, NASA-supported scientists have studied Cerro Negro volcano because its rocks resemble those of Mars.',
                  )}
                </p>
              </article>

              <article className="rl-case-item">
                <h3 className="rl-case-place">{t('Atacama y Utah · Cráter Jezero', 'Atacama and Utah · Jezero Crater')}</h3>
                <p>
                  {t(
                    'El desierto de Atacama, en Chile, es uno de los lugares más citados por su parecido con Marte. Pero cuando comparamos sus laderas con las de un sector del cráter donde aterrizó Perseverance, encontramos que las de una zona de Utah se parecían más.',
                    'The Atacama Desert in Chile is one of the places most often cited for resembling Mars. But when we compared its slopes with those of a sector of the crater where Perseverance landed, we found that the slopes of an area in Utah were more similar.',
                  )}
                </p>
              </article>
            </div>
          </div>
        </section>

        {/* 3. MISMAS REGLAS Y DEMOSTRACIÓN VISUAL */}
        <section id="reglas" className="rl-section rl-rules-section">
          <div className="rl-container">
            <div className="rl-rules-header">
              <span className="rl-eyebrow">{t('Mismas reglas', 'Same rules')}</span>
              <h2>
                {t('Regolith mide la Tierra, la Luna y Marte', 'Regolith measures Earth, the Moon and Mars')}{' '}
                <span className="rl-accent">{t('con las mismas reglas.', 'by the same rules.')}</span>
              </h2>
              <p className="rl-section-lead">
                {t(
                  'Fusionamos miles de datos de seis instrumentos de la NASA, desde sus misiones a Marte, la Luna y la Estación Espacial Internacional, hasta los modelos de la Agencia Espacial Europea. Ponemos todo en un mismo mapa y comparamos lo que más le importa a un rover o a los próximos habitantes lunares y marcianos:',
                  'We combine thousands of data points from six NASA instruments, from its missions to Mars, the Moon and the International Space Station, to models from the European Space Agency. We put everything on one map and compare what matters most to a rover or to the next lunar and Martian inhabitants:',
                )}
              </p>
            </div>

            <ol className="rl-axes-list">
              <li className="rl-axis-item">
                <span className="rl-axis-num" aria-hidden="true">01</span>
                <h3>{t('La inclinación del terreno', 'How steep the terrain is')}</h3>
              </li>
              <li className="rl-axis-item">
                <span className="rl-axis-num" aria-hidden="true">02</span>
                <h3>{t('Qué tan accidentado es', 'How rugged it is')}</h3>
              </li>
              <li className="rl-axis-item">
                <span className="rl-axis-num" aria-hidden="true">03</span>
                <h3>{t('Los minerales que lo componen', 'The minerals it is made of')}</h3>
              </li>
            </ol>

            <MockMatchPanel />
          </div>
        </section>

        {/* 4. COMUNIDAD Y SOSTENIBILIDAD */}
        <section id="impacto" className="rl-section rl-open-section">
          <div className="rl-container">
            <div className="rl-open-header">
              <span className="rl-eyebrow">{t('Misión abierta', 'Open mission')}</span>
              <h2>{t('Abierto, reproducible y sin fines de lucro.', 'Open, reproducible and non-profit.')}</h2>
            </div>

            <div className="rl-open-grid">
              <article className="rl-open-item">
                <h3>{t('Para quiénes construimos', 'Who we build for')}</h3>
                <p>
                  {t(
                    'El sistema está dirigido a equipos de misión que buscan dónde ensayar, universidades que estudian otros planetas y países como el nuestro, que pueden aportar sitios y datos. Todo es abierto y reproducible.',
                    'The system is aimed at mission teams looking for where to test, universities that study other planets and countries like ours, which can contribute sites and data. Everything is open and reproducible.',
                  )}
                </p>
              </article>

              <article className="rl-open-item">
                <h3>{t('Cómo crece la plataforma', 'How the platform grows')}</h3>
                <p>
                  {t(
                    'Regolith es una plataforma sin fines de lucro, con código abierto. Para crecer, proponemos alianzas con agencias espaciales, fondos canalizados por un socio internacional y el apoyo de universidades.',
                    'Regolith is a non-profit, open-source platform. To grow, we propose partnerships with space agencies, funding channelled through an international partner and support from universities.',
                  )}
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
            {t(
              'Nuestro sistema no pregunta qué lugar es famoso, sino cuál es análogo de verdad.',
              'Our system does not ask which place is famous, but which one is truly analogous.',
            )}
          </p>
          <h2 className="rl-closing-step">
            {t('El próximo paso en otro mundo empieza aquí,', 'The next step on another world starts here,')}{' '}
            <span className="rl-accent">{t('en el lugar correcto de la Tierra.', 'in the right place on Earth.')}</span>
          </h2>
          <p className="rl-closing-motto">{t('Regolith; tres cuerpos, un mismo suelo.', 'Regolith: three bodies, one ground.')}</p>

          <button type="button" className="rl-btn-primary rl-btn-primary--lg" onClick={onStart}>
            <span>{t('Explorar el atlas', 'Explore the atlas')}</span>
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
              <span>{t('Tres cuerpos, un mismo suelo.', 'Three bodies, one ground.')}</span>
            </div>

            <div className="rl-footer-links">
              <a href="#relato">{t('El reto', 'The challenge')}</a>
              <a href="#reglas">{t('Mismas reglas', 'Same rules')}</a>
              <a href="#impacto">{t('Misión abierta', 'Open mission')}</a>
              <button type="button" className="rl-link-btn" onClick={onStart}>
                {t('Abrir Atlas', 'Open Atlas')}
              </button>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
