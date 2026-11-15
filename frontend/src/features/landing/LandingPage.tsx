import React, { useEffect, useRef, useState } from 'react';
import { Viewer, Cartesian3, Color, Ellipsoid, Globe, ImageryLayer, SingleTileImageryProvider, EllipsoidTerrainProvider, HeadingPitchRange, Math as CesiumMath } from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import './LandingPage.css';

const PLANETS = [
  { name: 'Earth', texture: '/textures/earth.png', color: '#315c67', radius: 6378137, lat: 38.4, lon: -110.9, label: 'TIERRA (Utah)' },
  { name: 'Mars', texture: '/textures/mars.png', color: '#8d4936', radius: 3394839.8, lat: 18.4, lon: 77.4, label: 'MARTE (Jezero)' },
  { name: 'Moon', texture: '/textures/mars.png', color: '#444444', radius: 1737400, lat: -85.0, lon: 0.0, label: 'LUNA (Polo Sur)' }
];

export function LandingPage({ onStart }: { onStart: () => void }) {
  const observerRef = useRef<IntersectionObserver | null>(null);
  const backgroundGlobe = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const [currentPlanetIdx, setCurrentPlanetIdx] = useState(0);

  useEffect(() => {
    // Scroll reveal
    observerRef.current = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) entry.target.classList.add('visible');
      });
    }, { threshold: 0.1 });
    document.querySelectorAll('.reveal').forEach(el => observerRef.current?.observe(el));

    // Background Cycle Globe
    if (backgroundGlobe.current && !viewerRef.current) {
      try {
        const viewer = new Viewer(backgroundGlobe.current, {
          baseLayer: false, baseLayerPicker: false, geocoder: false, homeButton: false,
          sceneModePicker: false, navigationHelpButton: false, animation: false, timeline: false,
          fullscreenButton: false, infoBox: false, selectionIndicator: false,
          creditContainer: document.createElement('div'),
          scene3DOnly: true,
        });
        viewerRef.current = viewer;
        viewer.scene.backgroundColor = Color.TRANSPARENT;
        viewer.scene.globe.showGroundAtmosphere = true;
        
        // Auto-rotation
        viewer.scene.postRender.addEventListener(() => {
          viewer.camera.rotate(Cartesian3.UNIT_Z, 0.001);
        });
      } catch (e) { console.error(e); }
    }

    return () => {
      observerRef.current?.disconnect();
      viewerRef.current?.destroy(); viewerRef.current = null;
    };
  }, []);

  // Planet Cycling Logic
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    const planet = PLANETS[currentPlanetIdx];
    const ellipsoid = new Ellipsoid(planet.radius, planet.radius, planet.radius);
    
    // Smooth transition
    viewer.imageryLayers.removeAll();
    viewer.scene.globe.baseColor = Color.fromCssColorString(planet.color);
    
    SingleTileImageryProvider.fromUrl(planet.texture, { ellipsoid })
      .then(provider => {
        if (!viewer.isDestroyed()) {
          viewer.imageryLayers.add(new ImageryLayer(provider));
          viewer.camera.flyTo({
            destination: Cartesian3.fromDegrees(planet.lon, planet.lat, planet.radius * 2.5, ellipsoid),
            duration: 4,
            easingFunction: CesiumMath.linear
          });
        }
      });

    const timer = setTimeout(() => {
      setCurrentPlanetIdx((prev) => (prev + 1) % PLANETS.length);
    }, 12000); // Change planet every 12s

    return () => clearTimeout(timer);
  }, [currentPlanetIdx]);

  return (
    <div className="regolith-landing-premium">
      {/* Background Cinematic Engine */}
      <div className="cinematic-background" ref={backgroundGlobe}></div>
      <div className="cinematic-overlay"></div>

      {/* Navigation */}
      <nav className="ultra-nav">
        <div className="container nav-wrap">
          <a href="/" className="nav-logo">
            <img src="/assets/logos/regolith-lockup-noche-600px.png" alt="Regolith" />
          </a>
          <div className="nav-actions">
            <div className="planet-status">
              <span className="pulse-dot"></span>
              {PLANETS[currentPlanetIdx].label}
            </div>
            <button className="nav-btn-main" onClick={onStart}>Entrar al Atlas</button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="hero-premium">
        <div className="container hero-inner reveal">
          <div className="hero-badge">NASA SPACE APPS CHALLENGE 2026</div>
          <h1 className="hero-title-main">
            Tres cuerpos, <br />
            <span className="gradient-text">un mismo suelo.</span>
          </h1>
          <p className="hero-sub">
            Midiendo la Tierra, la Luna y Marte bajo una misma regla. <br />
            La ciencia de análogos, rediseñada para la próxima frontera.
          </p>
          <div className="hero-cta-group">
            <button className="btn-glow-gold" onClick={onStart}>Comenzar Exploración</button>
            <button className="btn-outline" onClick={() => document.getElementById('story').scrollIntoView()}>Nuestra Historia</button>
          </div>
        </div>
      </section>

      {/* Story / Pitch Section */}
      <section id="story" className="section-story">
        <div className="container grid-2 reveal">
          <div className="story-content">
            <div className="eyebrow">El Gancho</div>
            <h2>Nicaragua y el espacio nunca estuvieron tan cerca.</h2>
            <p>
              Desde el <strong>Cerro Negro</strong> hasta el <strong>Desierto de Atacama</strong>, hemos buscado a Marte en casa. Pero la fama no es precisión.
            </p>
            <div className="data-comparison">
              <div className="data-card error">
                <span className="val">Δ 5.0°</span>
                <span className="lbl">Atacama vs Jezero</span>
                <div className="bar"><div className="fill" style={{width: '100%'}}></div></div>
              </div>
              <div className="data-card success">
                <span className="val">Δ 1.5°</span>
                <span className="lbl">Utah vs Jezero</span>
                <div className="bar"><div className="fill" style={{width: '30%'}}></div></div>
              </div>
            </div>
            <p className="story-conclusion">
              Una diferencia de 5 grados puede invalidar meses de pruebas. <strong>Regolith mide antes de ensayar.</strong>
            </p>
          </div>
          <div className="story-visual">
            <div className="abstract-3d-box">
              <div className="face f1"></div>
              <div className="face f2"></div>
              <div className="face f3"></div>
            </div>
          </div>
        </div>
      </section>

      {/* Solución / Tres Pilares */}
      <section className="section-pillars">
        <div className="container">
          <div className="text-center mb-6 reveal">
            <div className="eyebrow amber">Metodología</div>
            <h2 className="title-large">Comparaciones rigurosas, <br />datos a la vista.</h2>
          </div>
          <div className="grid-3 reveal">
            <div className="pillar-premium">
              <div className="pillar-num">01</div>
              <h3>Misma Escala</h3>
              <p>Rampa unificada y ventanas espaciales idénticas para evitar sesgos de percepción entre mundos.</p>
            </div>
            <div className="pillar-premium">
              <div className="pillar-num">02</div>
              <h3>Multicriterio</h3>
              <p>Inclinación, rugosidad y composición mineralógica bajo un mismo análisis riguroso de 30m/60m.</p>
            </div>
            <div className="pillar-premium">
              <div className="pillar-num">03</div>
              <h3>Honestidad Técnica</h3>
              <p>Declaramos abiertamente qué se evaluó y qué se ignoró. Sin datos falsos, solo ciencia abierta.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Impacto & Sostenibilidad */}
      <section className="section-impact">
        <div className="container reveal">
          <div className="impact-box">
            <div className="grid-2">
              <div className="impact-text">
                <div className="eyebrow">Impacto Social & Científico</div>
                <h2>Sostenible. Abierto. Nicaragüense.</h2>
                <p>
                  Regolith funciona como una organización sin fines de lucro. Mantener la ciencia planetaria abierta cuesta menos de <strong>$1,700 al año</strong>.
                </p>
                <div className="impact-list">
                  <div className="impact-item">
                    <strong>Misiones:</strong> Optimización de sitios de ensayo para rovers y hábitats.
                  </div>
                  <div className="impact-item">
                    <strong>Academia:</strong> Datos reproducibles para investigación planetaria global.
                  </div>
                  <div className="impact-item">
                    <strong>Naciones:</strong> Nuevas oportunidades para países emergentes en la exploración espacial.
                  </div>
                </div>
              </div>
              <div className="impact-stats-circle">
                <div className="circle-wrap">
                  <div className="circle-inner">
                    <span className="big">100%</span>
                    <span className="small">OPEN SOURCE</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer Final */}
      <footer className="footer-premium reveal">
        <div className="container">
          <div className="footer-grid">
            <div className="footer-brand-large">
              <img src="/assets/logos/regolith-lockup-noche-600px.png" alt="Regolith" />
              <p className="tagline">Nuestro sistema no pregunta qué lugar es famoso, sino cuál es análogo de verdad.</p>
            </div>
            <div className="footer-credits">
              <div className="team-badge">
                <small>DESARROLLADO POR</small>
                <strong>NO SKY IS THE LIMIT</strong>
                <p>UAM, Nicaragua · 2026</p>
              </div>
            </div>
          </div>
          <div className="footer-legal-bar">
            <span>NASA Space Apps Challenge · Ciencia Planetaria y de la Tierra</span>
            <div className="legal-links">
              <a href="#">Datos</a>
              <a href="#">GitHub</a>
              <a href="#">Metodología</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
