import React, { useRef, useMemo, useState, useEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import {
  createPhotorealisticTerrainTextures,
  createGeologicalStrataTexture,
  type ProcessedTerrainTextures,
} from './terrainMaterials';

export interface TerrainConfig {
  id: string;
  name: string;
  body: 'Tierra' | 'Marte' | 'Luna';
  siteSubtitle: string;
  heightmapUrl: string;
  satelliteUrl: string;
  reliefMapUrl?: string;
  colorTheme: string;
  stats: {
    medianSlope: string;
    elevationRange: string;
    cellSize: string;
    geology: string;
  };
}

// ── Terrain Mesh Fotorrealista con Normales PBR y Microtextura ──────────────
function TerrainBlock({
  config,
  exaggeration = 2.0,
  showWireframe = false,
  viewMode = '3d',
  isScanning = false,
  scanProgress = 100,
}: {
  config: TerrainConfig;
  exaggeration: number;
  showWireframe: boolean;
  viewMode: '3d' | 'satellite';
  isScanning?: boolean;
  scanProgress?: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const groupRef = useRef<THREE.Group>(null);
  const [textures, setTextures] = useState<ProcessedTerrainTextures | null>(null);

  // Procesamiento fotorrealista de alta resolución
  useEffect(() => {
    createPhotorealisticTerrainTextures(
      config.heightmapUrl,
      config.satelliteUrl,
      config.body,
      config.id,
      (processed) => {
        setTextures(processed);
      }
    );
  }, [config.heightmapUrl, config.satelliteUrl, config.body, config.id]);

  // Geometría del terreno de alta densidad (120x120) para suavidad orgánica
  const geometry = useMemo(() => {
    const geo = new THREE.PlaneGeometry(5, 5, 120, 120);
    geo.rotateX(-Math.PI / 2);
    return geo;
  }, []);

  // Textura geológica de estratos para los bordes cortados de la roca
  const strataTex = useMemo(() => {
    return createGeologicalStrataTexture(config.body, config.id);
  }, [config.body, config.id]);

  // Zócalo geológico inferior (bloque de corteza)
  const baseGeometry = useMemo(() => {
    const geo = new THREE.BoxGeometry(5, 1.35, 5);
    geo.translate(0, -0.72, 0);
    return geo;
  }, []);

  // Rotación suave continua para percibir la tridimensionalidad y sombras
  useFrame((_, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * (isScanning ? 0.05 : 0.12);
    }
  });

  // Posición del haz de escaneo láser sobre el bloque Z en [-2.5, 2.5]
  const scanZ = (scanProgress / 100) * 5.0 - 2.5;

  return (
    <group ref={groupRef}>
      {/* Superficie con relieve fotorrealista, elevación PBR y textura seleccionada */}
      <mesh
        ref={meshRef}
        geometry={geometry}
        castShadow
        receiveShadow
      >
        <meshStandardMaterial
          map={viewMode === 'satellite' ? (textures?.satelliteMap || undefined) : (textures?.geologyMap || undefined)}
          displacementMap={textures?.displacementMap || undefined}
          displacementScale={0.72 * exaggeration}
          displacementBias={-0.10}
          normalMap={textures?.normalMap || undefined}
          normalScale={new THREE.Vector2(1.25, 1.25)}
          roughnessMap={textures?.roughnessMap || undefined}
          roughness={viewMode === 'satellite' ? 0.90 : 0.85}
          metalness={0.05}
          wireframe={showWireframe}
        />
      </mesh>

      {/* Haz láser altimétrico durante el escaneo activo */}
      {isScanning && (
        <group position={[0, 0.45, scanZ]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[5.05, 0.14]} />
            <meshBasicMaterial
              color={config.body === 'Marte' ? '#f2a64e' : config.body === 'Luna' ? '#c5e59e' : '#4a9eff'}
              side={THREE.DoubleSide}
              transparent
              opacity={0.9}
            />
          </mesh>
          <pointLight
            color={config.body === 'Marte' ? '#f2a64e' : config.body === 'Luna' ? '#c5e59e' : '#4a9eff'}
            intensity={3.5}
            distance={2.8}
          />
        </group>
      )}

      {/* Bloque de corteza con estratos sedimentarios visibles */}
      <mesh geometry={baseGeometry} receiveShadow>
        <meshStandardMaterial
          map={strataTex}
          roughness={0.92}
          metalness={0.04}
        />
      </mesh>

      {/* Rejilla de borde sutil para marco de laboratorio */}
      <lineSegments>
        <edgesGeometry args={[new THREE.BoxGeometry(5.01, 0.04, 5.01)]} />
        <lineBasicMaterial color={config.colorTheme} transparent opacity={0.35} />
      </lineSegments>
    </group>
  );
}

// ══════════════════════════════════════════════════════════════
// VISOR DE TERRENO 3D INDIVIDUAL CON ILUMINACIÓN FOTORREALISTA
// ══════════════════════════════════════════════════════════════
export function SingleTerrainViewer({
  config,
  exaggeration = 2.0,
  showWireframe = false,
  viewMode = '3d',
  isScanning = false,
  scanProgress = 100,
}: {
  config: TerrainConfig;
  exaggeration?: number;
  showWireframe?: boolean;
  viewMode?: '3d' | 'satellite';
  isScanning?: boolean;
  scanProgress?: number;
}) {
  return (
    <div className="terrain-3d-canvas-wrap">
      <Canvas
        shadows
        camera={{ position: [4.4, 4.0, 4.4], fov: 40 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.15 }}
      >
        {/* Luz solar orbital con sombras nítidas (hillshading cinematográfico) */}
        <ambientLight intensity={0.42} />
        <directionalLight
          position={[9, 14, 7]}
          intensity={2.85}
          castShadow
          shadow-mapSize-width={2048}
          shadow-mapSize-height={2048}
          shadow-bias={-0.0001}
        />
        {/* Luz de rebote planetaria */}
        <directionalLight
          position={[-7, 5, -7]}
          intensity={0.45}
          color={config.colorTheme}
        />

        <TerrainBlock
          config={config}
          exaggeration={exaggeration}
          showWireframe={showWireframe}
          viewMode={viewMode}
          isScanning={isScanning}
          scanProgress={scanProgress}
        />

        <OrbitControls
          enableZoom={false}
          enablePan={false}
          minPolarAngle={Math.PI / 6}
          maxPolarAngle={Math.PI / 2.2}
          autoRotate={false}
        />
      </Canvas>

      {/* Overlay informativo de la muestra geológica */}
      <div className="terrain-overlay-badge">
        <div className="terrain-body-tag" style={{ color: config.colorTheme }}>
          <span className="terrain-dot" style={{ background: config.colorTheme }} />
          {config.body.toUpperCase()} · {config.stats.cellSize}
        </div>
        <div className="terrain-site-title">{config.name}</div>
        <div className="terrain-site-sub">{config.siteSubtitle}</div>
      </div>

      {/* Datos cuantitativos de relieve y geología */}
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
// CATÁLOGO DE TERRENOS CON ORTOFOTOS SATELITALES Y ELEVACIONES
// ══════════════════════════════════════════════════════════════
export const TERRAIN_CATALOG: Record<string, TerrainConfig> = {
  utah: {
    id: 'utah',
    name: 'Desierto de Utah',
    body: 'Tierra',
    siteSubtitle: 'EE.UU. · Formación Morrison (Análogo Jezero)',
    heightmapUrl: '/surface/earth-utah-height.png',
    satelliteUrl: '/analysis/utah-context.png',
    colorTheme: '#F2A64E',
    stats: {
      medianSlope: '4.8° (Δ 1.5° vs Jezero)',
      elevationRange: '84 m',
      cellSize: 'Ventana 1.8 km',
      geology: 'Areniscas y arcillas sedimentarias',
    },
  },
  atacama: {
    id: 'atacama',
    name: 'Desierto de Atacama',
    body: 'Tierra',
    siteSubtitle: 'Chile · Cuenca Yungay (El más famoso)',
    heightmapUrl: '/surface/earth-atacama-height.png',
    satelliteUrl: '/analysis/atacama-context.png',
    colorTheme: '#4a9eff',
    stats: {
      medianSlope: '8.3° (Δ 5.0° vs Jezero)',
      elevationRange: '196 m',
      cellSize: 'Ventana 1.8 km',
      geology: 'Costras salinas e hiperaridez',
    },
  },
  jezero: {
    id: 'jezero',
    name: 'Delta Cráter Jezero',
    body: 'Marte',
    siteSubtitle: 'Marte · 18.4°N, 77.7°E (Sitio Perseverance)',
    heightmapUrl: '/surface/mars-jezero-fan-height.png',
    satelliteUrl: '/analysis/jezero-context.png',
    colorTheme: '#e05222',
    stats: {
      medianSlope: '3.3° de inclinación',
      elevationRange: '112 m',
      cellSize: 'Ventana 1.8 km',
      geology: 'Delta fluvial y arcillas lacustres',
    },
  },
  shackleton: {
    id: 'shackleton',
    name: 'Cráter Shackleton',
    body: 'Luna',
    siteSubtitle: 'Polo Sur Lunar · 89.9°S (Misión Artemis)',
    heightmapUrl: '/surface/moon-shackleton-height.png',
    satelliteUrl: '/analysis/shackleton-context.png',
    colorTheme: '#c5e59e',
    stats: {
      medianSlope: '12.4° (Escarpas polares)',
      elevationRange: '340 m',
      cellSize: 'Ventana 1.8 km',
      geology: 'Regolito anortosítico y hielo permanente',
    },
  },
};
