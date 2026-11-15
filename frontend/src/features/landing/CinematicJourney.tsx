import React, { useRef, useMemo } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Stars, Float } from '@react-three/drei';
import * as THREE from 'three';

// ── Paleta oficial de colores ────────────────────────────────
export const PLANET_COLORS = {
  earth: '#4a9eff',
  moon:  '#c5e59e',
  mars:  '#e05222', // Rojo marciano vibrante auténtico
};

// ── Configuración espacial fotorrealista (NASA) ───────────────
export const PLANET_CONFIG = [
  {
    id: 'earth',
    pos: [0, 0, 0] as [number, number, number],
    size: 5.5,
    textureUrl: `${import.meta.env.BASE_URL}surface/blue-marble.png`,
    // Blanco puro para preservar los colores reales del Blue Marble de la NASA
    color: '#ffffff',
    emissive: '#000000',
    emissiveIntensity: 0.0,
    roughness: 0.65,
    metalness: 0.02,
    atmColor: '#64b5f6', // Dispersión Rayleigh azul celeste en el limbo
    atmOpacity: 0.32,
    hasAtmosphere: true,
  },
  {
    id: 'moon',
    pos: [36, 10, -26] as [number, number, number],
    size: 1.8,
    textureUrl: '/textures/moon.jpg',
    color: '#ffffff',
    emissive: '#000000',
    emissiveIntensity: 0.0,
    roughness: 0.95,
    metalness: 0.0,
    atmColor: '#000000',
    atmOpacity: 0.0,
    hasAtmosphere: false, // Vacío lunar sin atmósfera
  },
  {
    id: 'mars',
    pos: [-52, 18, -50] as [number, number, number],
    size: 4.0,
    textureUrl: `${import.meta.env.BASE_URL}surface/mars-globe.png`,
    color: '#ffffff',
    emissive: '#250802',
    emissiveIntensity: 0.08,
    roughness: 0.88,
    metalness: 0.02,
    atmColor: '#f26838', // Atmósfera tenue de polvo rojizo
    atmOpacity: 0.28,
    hasAtmosphere: true,
  },
];

// ── Shader de atmósfera Fresnel (dispersión física de borde) ──
const atmosphereVertexShader = /* glsl */ `
  varying vec3 vNormal;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const atmosphereFragmentShader = /* glsl */ `
  varying vec3 vNormal;
  uniform vec3 uColor;
  uniform float uOpacity;
  void main() {
    float intensity = pow(1.0 - abs(dot(vNormal, vec3(0.0, 0.0, 1.0))), 3.0);
    gl_FragColor = vec4(uColor, intensity * uOpacity);
  }
`;

// ══════════════════════════════════════════════════════════════
// PLANETA FOTORREALISTA (SIN SUSPENSE; CARGA INMEDIATA)
// ══════════════════════════════════════════════════════════════
function PlanetMesh({
  config,
  isActive,
}: {
  config: typeof PLANET_CONFIG[0];
  isActive: boolean;
}) {
  const meshRef = useRef<THREE.Mesh>(null);

  // Carga asíncrona no bloqueante de textura (inicio automático inmediato)
  const texture = useMemo(() => {
    const loader = new THREE.TextureLoader();
    const tex = loader.load(config.textureUrl);
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }, [config.textureUrl]);

  // Material de atmósfera Fresnel en el limbo
  const atmMaterial = useMemo(() => {
    if (!config.hasAtmosphere) return null;
    return new THREE.ShaderMaterial({
      vertexShader: atmosphereVertexShader,
      fragmentShader: atmosphereFragmentShader,
      uniforms: {
        uColor:   { value: new THREE.Color(config.atmColor) },
        uOpacity: { value: config.atmOpacity },
      },
      transparent: true,
      side: THREE.BackSide,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
  }, [config.hasAtmosphere, config.atmColor, config.atmOpacity]);

  // Rotación axial continua automática desde el primer fotograma
  useFrame((_, delta) => {
    if (meshRef.current) {
      meshRef.current.rotation.y += delta * 0.05;
    }
  });

  return (
    <group position={config.pos}>
      <Float speed={1.2} rotationIntensity={isActive ? 0.15 : 0.05} floatIntensity={isActive ? 0.35 : 0.1}>
        {/* Esfera planetaria de alta resolución (128x128) */}
        <mesh ref={meshRef} castShadow receiveShadow>
          <sphereGeometry args={[config.size, 128, 128]} />
          <meshStandardMaterial
            map={texture}
            color={config.color}
            emissive={config.emissive}
            emissiveIntensity={config.emissiveIntensity}
            roughness={config.roughness}
            metalness={config.metalness}
          />
        </mesh>

        {/* Halo atmosférico en el limbo (sin anillos) */}
        {config.hasAtmosphere && atmMaterial && (
          <mesh material={atmMaterial}>
            <sphereGeometry args={[config.size * 1.15, 64, 64]} />
          </mesh>
        )}
      </Float>
    </group>
  );
}

// ══════════════════════════════════════════════════════════════
// PARTÍCULAS ESTELARES Y SALTO HIPERESPACIAL
// ══════════════════════════════════════════════════════════════
function WarpParticles({ isTraveling }: { isTraveling: boolean }) {
  const count = 2400;
  const pointsRef = useRef<THREE.Points>(null);

  const { positions } = useMemo(() => {
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const r = Math.random() * 85 + 5;
      const theta = Math.random() * Math.PI * 2;
      pos[i * 3]     = Math.cos(theta) * r;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 85;
      pos[i * 3 + 2] = Math.sin(theta) * r;
    }
    return { positions: pos };
  }, []);

  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    return g;
  }, [positions]);

  const progress = useRef(0);

  useFrame((_, delta) => {
    const target = isTraveling ? 1 : 0;
    progress.current += (target - progress.current) * delta * 2.2;

    if (pointsRef.current) {
      const mat = pointsRef.current.material as THREE.PointsMaterial;
      mat.opacity = 0.15 + progress.current * 0.75;
      mat.size    = 0.06 + progress.current * 0.35;
      pointsRef.current.scale.z = 1 + progress.current * 16;
      pointsRef.current.rotation.y += 0.0003 + progress.current * 0.002;
    }
  });

  return (
    <points ref={pointsRef} geometry={geo}>
      <pointsMaterial
        color="#F2A64E"
        size={0.06}
        transparent
        opacity={0.15}
        sizeAttenuation
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

// ══════════════════════════════════════════════════════════════
// CÁMARA CINEMÁTICA AUTOMATIZADA CON MOVIMIENTO CONTINUO
// ══════════════════════════════════════════════════════════════
function CinematicCamera({
  targetPos,
  isTraveling,
}: {
  targetPos: [number, number, number];
  isTraveling: boolean;
}) {
  const { camera } = useThree();
  const currentPos = useRef(new THREE.Vector3(targetPos[0], targetPos[1] + 6, targetPos[2] + 20));
  const currentLookAt = useRef(new THREE.Vector3(...targetPos));

  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    const target = new THREE.Vector3(...targetPos);
    const dist = target.length() || 1;

    // Órbita cinematográfica con cabeceo suave
    const cameraOffset = new THREE.Vector3(
      Math.sin(t * 0.05) * 3.0,
      dist * 0.28 + 5.5,
      dist * 0.55 + 18,
    );

    const shake = new THREE.Vector3(
      Math.sin(t * 2.2) * (isTraveling ? 0.45 : 0.04),
      Math.cos(t * 1.6) * (isTraveling ? 0.35 : 0.03),
      0,
    );

    const idealPosition = target.clone().add(cameraOffset).add(shake);
    const lerpSpeed = isTraveling ? 0.035 : 0.065;

    currentPos.current.lerp(idealPosition, lerpSpeed);
    camera.position.copy(currentPos.current);

    currentLookAt.current.lerp(target, 0.09);
    camera.lookAt(currentLookAt.current);

    const cam = camera as THREE.PerspectiveCamera;
    const targetFov = isTraveling ? 68 : 44;
    cam.fov += (targetFov - cam.fov) * 0.05;
    cam.updateProjectionMatrix();
  });

  return null;
}

// ══════════════════════════════════════════════════════════════
// RUTAS DE NAVEGACIÓN EN ESPACIO PROFUNDO (TIERRA -> MARTE -> LUNA -> TIERRA)
// ══════════════════════════════════════════════════════════════
function InterplanetaryTrajectory() {
  const lines = useMemo(() => {
    const earthPos = new THREE.Vector3(0, 0, 0);
    const marsPos  = new THREE.Vector3(-52, 18, -50);
    const moonPos  = new THREE.Vector3(36, 10, -26);

    // Ruta 1: Tierra -> Marte
    const curveMars = new THREE.QuadraticBezierCurve3(
      earthPos,
      new THREE.Vector3(-22, 32, -22),
      marsPos,
    );
    // Ruta 2: Marte -> Luna
    const curveMarsMoon = new THREE.QuadraticBezierCurve3(
      marsPos,
      new THREE.Vector3(-8, 22, -35),
      moonPos,
    );
    // Ruta 3: Luna -> Tierra
    const curveMoonEarth = new THREE.QuadraticBezierCurve3(
      moonPos,
      new THREE.Vector3(18, 14, -12),
      earthPos,
    );

    const geo1 = new THREE.BufferGeometry().setFromPoints(curveMars.getPoints(50));
    const geo2 = new THREE.BufferGeometry().setFromPoints(curveMarsMoon.getPoints(50));
    const geo3 = new THREE.BufferGeometry().setFromPoints(curveMoonEarth.getPoints(50));

    const matMars = new THREE.LineDashedMaterial({
      color: '#e05222',
      dashSize: 1.5,
      gapSize: 1.2,
      opacity: 0.15,
      transparent: true,
      depthWrite: false,
    });
    const matMoon = new THREE.LineDashedMaterial({
      color: '#d0d4d8',
      dashSize: 1.2,
      gapSize: 1.0,
      opacity: 0.15,
      transparent: true,
      depthWrite: false,
    });
    const matEarth = new THREE.LineDashedMaterial({
      color: '#4a9eff',
      dashSize: 1.2,
      gapSize: 1.0,
      opacity: 0.15,
      transparent: true,
      depthWrite: false,
    });

    const line1 = new THREE.Line(geo1, matMars);
    line1.computeLineDistances();

    const line2 = new THREE.Line(geo2, matMoon);
    line2.computeLineDistances();

    const line3 = new THREE.Line(geo3, matEarth);
    line3.computeLineDistances();

    return [line1, line2, line3];
  }, []);

  return (
    <group>
      {lines.map((l, i) => (
        <primitive key={i} object={l} />
      ))}
    </group>
  );
}

// ══════════════════════════════════════════════════════════════
// ESCENA COMPLETA 3D CON INICIO AUTOMÁTICO INMEDIATO
// ══════════════════════════════════════════════════════════════
function SpaceScene({
  currentPlanet,
  isTraveling,
}: {
  currentPlanet: string;
  isTraveling: boolean;
}) {
  const activePlanet = PLANET_CONFIG.find(p => p.id === currentPlanet) || PLANET_CONFIG[0];

  return (
    <>
      <Stars radius={300} depth={90} count={14000} factor={4.5} saturation={0} fade speed={isTraveling ? 4 : 1} />

      {/* Luz solar orbital limpia y sombras naturales astronómicas */}
      <ambientLight intensity={0.25} />
      <directionalLight
        position={[100, 60, 85]}
        intensity={3.2}
        color="#fffcf5"
      />
      <directionalLight
        position={[-80, -30, -50]}
        intensity={0.25}
        color="#c8dcff"
      />

      {/* Planetas esféricos puros (Tierra, Luna, Marte rojizo) */}
      {PLANET_CONFIG.map(cfg => (
        <PlanetMesh
          key={cfg.id}
          config={cfg}
          isActive={currentPlanet === cfg.id}
        />
      ))}

      <InterplanetaryTrajectory />
      <WarpParticles isTraveling={isTraveling} />
      <CinematicCamera targetPos={activePlanet.pos} isTraveling={isTraveling} />
    </>
  );
}

// ══════════════════════════════════════════════════════════════
// EXPORT PRINCIPAL: ANIMACIÓN 100% AUTOMÁTICA AL INICIAR LA WEB
// ══════════════════════════════════════════════════════════════
export function CinematicJourney({
  activePlanet,
  isTraveling,
}: {
  activePlanet: string;
  isTraveling: boolean;
}) {
  return (
    <div style={{ width: '100%', height: '100%', position: 'absolute', top: 0, left: 0 }}>
      <Canvas
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: false, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.15 }}
        camera={{ position: [0, 8, 22], fov: 44, near: 0.1, far: 2500 }}
      >
        <color attach="background" args={['#030508']} />
        <SpaceScene
          currentPlanet={activePlanet}
          isTraveling={isTraveling}
        />
      </Canvas>
    </div>
  );
}
