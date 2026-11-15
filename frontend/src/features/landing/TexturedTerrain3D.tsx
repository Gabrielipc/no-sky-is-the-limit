import React, { useRef, useMemo, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';

export interface TerrainConfig {
  id: string;
  name: string;
  body: 'Tierra' | 'Marte' | 'Luna';
  siteSubtitle: string;
  heightmapUrl: string;
  reliefMapUrl: string;
  colorTheme: string;
  stats: {
    medianSlope: string;
    elevationRange: string;
    cellSize: string;
    geology: string;
  };
}

// ── Terrain Mesh con desplazamiento y relieve ───────────────
function TerrainBlock({
  config,
  exaggeration = 2.0,
  showWireframe = false,
  colorMode = 'geology',
}: {
  config: TerrainConfig;
  exaggeration: number;
  showWireframe: boolean;
  colorMode: 'geology' | 'elevation' | 'slope';
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const groupRef = useRef<THREE.Group>(null);

  // Carga de texturas con fallback procedural
  const { heightTex, reliefTex } = useMemo(() => {
    const loader = new THREE.TextureLoader();
    const hTex = loader.load(config.heightmapUrl);
    const rTex = loader.load(config.reliefMapUrl);
    hTex.wrapS = hTex.wrapT = THREE.ClampToEdgeWrapping;
    rTex.wrapS = rTex.wrapT = THREE.ClampToEdgeWrapping;
    return { heightTex: hTex, reliefTex: rTex };
  }, [config.heightmapUrl, config.reliefMapUrl]);

  // Geometría del terreno: plano de alta densidad
  const geometry = useMemo(() => {
    const geo = new THREE.PlaneGeometry(5, 5, 80, 80);
    geo.rotateX(-Math.PI / 2); // plano horizontal XZ
    return geo;
  }, []);

  // Base geológica (cuerpo inferior del bloque)
  const baseGeometry = useMemo(() => {
    const geo = new THREE.BoxGeometry(5, 1.2, 5);
    geo.translate(0, -0.65, 0);
    return geo;
  }, []);

  // Color de base según cuerpo celeste
  const baseColor = useMemo(() => {
    if (config.body === 'Marte') return '#2b140a';
    if (config.body === 'Luna')  return '#181b1d';
    return '#1c1b18'; // Tierra
  }, [config.body]);

  // Rotación lenta suave
  useFrame((_, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * 0.15;
    }
  });

  return (
    <group ref={groupRef}>
      {/* Superficie del terreno con elevación real */}
      <mesh
        ref={meshRef}
        geometry={geometry}
        castShadow
        receiveShadow
      >
        <meshStandardMaterial
          map={colorMode === 'geology' ? reliefTex : undefined}
          color={colorMode === 'elevation' ? config.colorTheme : colorMode === 'slope' ? '#e9ede5' : undefined}
          displacementMap={heightTex}
          displacementScale={0.7 * exaggeration}
          displacementBias={-0.1}
          roughness={0.88}
          metalness={0.08}
          wireframe={showWireframe}
        />
      </mesh>

      {/* Zócalo / Bloque geológico de corteza inferior */}
      <mesh geometry={baseGeometry} receiveShadow>
        <meshStandardMaterial
          color={baseColor}
          roughness={0.95}
          metalness={0.05}
        />
      </mesh>

      {/* Borde sutil del marco de medición */}
      <lineSegments>
        <edgesGeometry args={[new THREE.BoxGeometry(5.02, 0.05, 5.02)]} />
        <lineBasicMaterial color={config.colorTheme} transparent opacity={0.35} />
      </lineSegments>
    </group>
  );
}

// ══════════════════════════════════════════════════════════════
// VISOR DE TERRENO 3D INDIVIDUAL
// ══════════════════════════════════════════════════════════════
export function SingleTerrainViewer({
  config,
  exaggeration = 2.0,
  showWireframe = false,
  colorMode = 'geology',
}: {
  config: TerrainConfig;
  exaggeration?: number;
  showWireframe?: boolean;
  colorMode?: 'geology' | 'elevation' | 'slope';
}) {
  return (
    <div className="terrain-3d-canvas-wrap">
      <Canvas
        shadows
        camera={{ position: [4.5, 4.2, 4.5], fov: 42 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: true }}
      >
        {/* Iluminación tipo sol orbital (hillshading con sombras marcadas) */}
        <ambientLight intensity={0.5} />
        <directionalLight
          position={[8, 12, 6]}
          intensity={2.2}
          castShadow
          shadow-mapSize-width={1024}
          shadow-mapSize-height={1024}
        />
        {/* Luz de relleno suave */}
        <directionalLight
          position={[-6, 4, -6]}
          intensity={0.4}
          color={config.colorTheme}
        />

        <TerrainBlock
          config={config}
          exaggeration={exaggeration}
          showWireframe={showWireframe}
          colorMode={colorMode}
        />

        {/* Controles de órbita interactivos con auto-rotación */}
        <OrbitControls
          enableZoom={false}
          enablePan={false}
          minPolarAngle={Math.PI / 6}
          maxPolarAngle={Math.PI / 2.2}
          autoRotate={false}
        />
      </Canvas>

      {/* Overlay informativo del terreno */}
      <div className="terrain-overlay-badge">
        <div className="terrain-body-tag" style={{ color: config.colorTheme }}>
          <span className="terrain-dot" style={{ background: config.colorTheme }} />
          {config.body.toUpperCase()} · {config.stats.cellSize}
        </div>
        <div className="terrain-site-title">{config.name}</div>
        <div className="terrain-site-sub">{config.siteSubtitle}</div>
      </div>

      {/* Regla de escala vertical y datos de terreno */}
      <div className="terrain-stats-bar">
        <div>
          <span className="stat-label">Inclinación mediana</span>
          <strong className="stat-val" style={{ color: config.colorTheme }}>
            {config.stats.medianSlope}
          </strong>
        </div>
        <div>
          <span className="stat-label">Relieve (p95-p5)</span>
          <strong className="stat-val">{config.stats.elevationRange}</strong>
        </div>
        <div>
          <span className="stat-label">Geología</span>
          <span className="stat-subval">{config.stats.geology}</span>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// CATÁLOGO DE TERRENOS MOCKEADOS LOCALES
// ══════════════════════════════════════════════════════════════
export const TERRAIN_CATALOG: Record<string, TerrainConfig> = {
  utah: {
    id: 'utah',
    name: 'Desierto de Utah',
    body: 'Tierra',
    siteSubtitle: 'EE.UU. · Formación Morrison (Análogo Jezero)',
    heightmapUrl: '/surface/earth-utah-height.png',
    reliefMapUrl: '/surface/earth-utah-relief.png',
    colorTheme: '#c5e59e',
    stats: {
      medianSlope: '4.8° (Δ 1.5° vs Jezero)',
      elevationRange: '84 m',
      cellSize: 'Ventana 1.8 km',
      geology: 'Sedimentario / Areniscas',
    },
  },
  atacama: {
    id: 'atacama',
    name: 'Desierto de Atacama',
    body: 'Tierra',
    siteSubtitle: 'Chile · Cuenca Yungay (El más famoso)',
    heightmapUrl: '/surface/earth-atacama-height.png',
    reliefMapUrl: '/surface/earth-atacama-relief.png',
    colorTheme: '#4a9eff',
    stats: {
      medianSlope: '8.3° (Δ 5.0° vs Jezero)',
      elevationRange: '196 m',
      cellSize: 'Ventana 1.8 km',
      geology: 'Hiperárido / Costras salinas',
    },
  },
  jezero: {
    id: 'jezero',
    name: 'Delta Cráter Jezero',
    body: 'Marte',
    siteSubtitle: 'Marte · 18.4°N, 77.7°E (Sitio Perseverance)',
    heightmapUrl: '/surface/mars-jezero-fan-height.png',
    reliefMapUrl: '/surface/mars-jezero-fan-relief.png',
    colorTheme: '#F2A64E',
    stats: {
      medianSlope: '3.3° de inclinación',
      elevationRange: '112 m',
      cellSize: 'Ventana 1.8 km',
      geology: 'Delta fluvial / Arcillas',
    },
  },
  shackleton: {
    id: 'shackleton',
    name: 'Cráter Shackleton',
    body: 'Luna',
    siteSubtitle: 'Polo Sur Lunar · 89.9°S (Misión Artemis)',
    // Reutiliza mapa de altura con textura lunar fría
    heightmapUrl: '/surface/mars-jezero-fan-height.png',
    reliefMapUrl: '/surface/earth-atacama-relief.png',
    colorTheme: '#e9ede5',
    stats: {
      medianSlope: '12.4° (Escarpas polares)',
      elevationRange: '340 m',
      cellSize: 'Ventana 1.8 km',
      geology: 'Regolito anortosítico / Hielo',
    },
  },
};

