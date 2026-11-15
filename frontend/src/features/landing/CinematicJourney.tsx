import React, { useRef, useMemo, useEffect, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Stars, Float } from '@react-three/drei';
import * as THREE from 'three';
import {
  earthVertexShader, earthFragmentShader,
  moonVertexShader, moonFragmentShader,
  marsVertexShader, marsFragmentShader,
  atmosphereVertexShader, atmosphereFragmentShader,
} from './shaders';

// ── Paleta de colores por planeta ────────────────────────────
export const PLANET_COLORS = {
  earth: '#4a9eff',
  moon:  '#c5e59e',
  mars:  '#F2A64E',
};

// ── Configuración espacial precisa (sin anillos) ─────────────
export const PLANET_CONFIG = [
  {
    id: 'earth',
    pos: [0, 0, 0] as [number, number, number],
    size: 5.5,
    color: PLANET_COLORS.earth,
    atmColor: new THREE.Color(0.12, 0.45, 1.0),
    atmIntensity: 0.85,
  },
  {
    id: 'moon',
    pos: [36, 10, -26] as [number, number, number],
    size: 1.8,
    color: PLANET_COLORS.moon,
    atmColor: new THREE.Color(0.35, 0.45, 0.35),
    atmIntensity: 0.1, // Luna casi sin atmósfera
  },
  {
    id: 'mars',
    pos: [-52, 18, -50] as [number, number, number],
    size: 4.0,
    color: PLANET_COLORS.mars,
    atmColor: new THREE.Color(0.9, 0.32, 0.1),
    atmIntensity: 0.5,
  },
];

// ── Ciclo cinematográfico automático exacto ──────────────────
// "de la tierra a marte y de nuevo de la tierra a la luna"
export const MISSION_CYCLE = ['earth', 'mars', 'earth', 'moon'] as const;
export type PlanetKey = typeof MISSION_CYCLE[number];

// ══════════════════════════════════════════════════════════════
// PLANETA ESFÉRICO PURO (SIN ANILLOS)
// ══════════════════════════════════════════════════════════════
function Planet({
  config,
  isActive,
}: {
  config: typeof PLANET_CONFIG[0];
  isActive: boolean;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const glowRef = useRef<THREE.Mesh>(null);

  const { vertShader, fragShader } = useMemo(() => {
    if (config.id === 'earth') return { vertShader: earthVertexShader, fragShader: earthFragmentShader };
    if (config.id === 'moon')  return { vertShader: moonVertexShader,  fragShader: moonFragmentShader };
    return { vertShader: marsVertexShader, fragShader: marsFragmentShader };
  }, [config.id]);

  const planetMaterial = useMemo(() => new THREE.ShaderMaterial({
    vertexShader: vertShader,
    fragmentShader: fragShader,
    uniforms: { uTime: { value: 0 } },
  }), [vertShader, fragShader]);

  const atmMaterial = useMemo(() => new THREE.ShaderMaterial({
    vertexShader: atmosphereVertexShader,
    fragmentShader: atmosphereFragmentShader,
    uniforms: {
      uColor:     { value: config.atmColor },
      uIntensity: { value: config.atmIntensity },
    },
    transparent: true,
    side: THREE.BackSide,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  }), [config.atmColor, config.atmIntensity]);

  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    if (meshRef.current) {
      meshRef.current.rotation.y += 0.0016;
      if (planetMaterial.uniforms.uTime) {
        planetMaterial.uniforms.uTime.value = t;
      }
    }
    if (glowRef.current) {
      const pulse = isActive ? 1.0 + Math.sin(t * 1.8) * 0.02 : 1.0;
      glowRef.current.scale.setScalar(pulse);
      (glowRef.current.material as THREE.MeshBasicMaterial).opacity +=
        ((isActive ? 0.07 : 0.0) - (glowRef.current.material as THREE.MeshBasicMaterial).opacity) * 0.05;
    }
  });

  return (
    <group position={config.pos}>
      <Float speed={1.2} rotationIntensity={isActive ? 0.2 : 0.05} floatIntensity={isActive ? 0.4 : 0.1}>
        {/* Cuerpo esférico del planeta */}
        <mesh ref={meshRef} material={planetMaterial}>
          <sphereGeometry args={[config.size, 96, 96]} />
        </mesh>

        {/* Capa atmosférica esférica (fresnel) */}
        <mesh material={atmMaterial}>
          <sphereGeometry args={[config.size * 1.15, 48, 48]} />
        </mesh>

        {/* Resplandor esférico difuso */}
        <mesh ref={glowRef}>
          <sphereGeometry args={[config.size * 1.35, 32, 32]} />
          <meshBasicMaterial
            color={config.color}
            transparent
            opacity={0}
            side={THREE.BackSide}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </mesh>
      </Float>
    </group>
  );
}

// ══════════════════════════════════════════════════════════════
// CAMPO DE ESTRELLAS HIPERESPACIAL (WARP SPEED)
// ══════════════════════════════════════════════════════════════
function WarpParticles({ isTraveling }: { isTraveling: boolean }) {
  const count = 2200;
  const pointsRef = useRef<THREE.Points>(null);

  const { positions } = useMemo(() => {
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const r = Math.random() * 80 + 5;
      const theta = Math.random() * Math.PI * 2;
      pos[i * 3]     = Math.cos(theta) * r;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 80;
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
    progress.current += (target - progress.current) * delta * 2.0;

    if (pointsRef.current) {
      const mat = pointsRef.current.material as THREE.PointsMaterial;
      mat.opacity = 0.15 + progress.current * 0.75;
      mat.size    = 0.06 + progress.current * 0.35;
      // Estiramiento longitudinal en el eje Z para simular warp
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
// CÁMARA CINEMÁTICA AUTOMATIZADA
// ══════════════════════════════════════════════════════════════
function CinematicCamera({
  targetPos,
  isTraveling,
}: {
  targetPos: [number, number, number];
  isTraveling: boolean;
}) {
  const { camera } = useThree();
  const currentPos = useRef(new THREE.Vector3(0, 8, 22));
  const currentLookAt = useRef(new THREE.Vector3());

  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    const target = new THREE.Vector3(...targetPos);
    const dist = target.length() || 1;

    // Órbita cinematográfica con cabeceo suave
    const cameraOffset = new THREE.Vector3(
      Math.sin(t * 0.06) * 3,
      dist * 0.28 + 5.5,
      dist * 0.55 + 18,
    );

    // Temblor cinemático sutil (shake durante el salto warp)
    const shake = new THREE.Vector3(
      Math.sin(t * 2.2) * (isTraveling ? 0.45 : 0.05),
      Math.cos(t * 1.6) * (isTraveling ? 0.35 : 0.04),
      0,
    );

    const idealPosition = target.clone().add(cameraOffset).add(shake);
    const lerpSpeed = isTraveling ? 0.024 : 0.055;

    currentPos.current.lerp(idealPosition, lerpSpeed);
    camera.position.copy(currentPos.current);

    currentLookAt.current.lerp(target, 0.08);
    camera.lookAt(currentLookAt.current);

    // Ajuste dinámico de campo visual (FOV warp)
    const cam = camera as THREE.PerspectiveCamera;
    const targetFov = isTraveling ? 68 : 44;
    cam.fov += (targetFov - cam.fov) * 0.045;
    cam.updateProjectionMatrix();
  });

  return null;
}

// ══════════════════════════════════════════════════════════════
// TRAYECTORIA DE TRANSFERENCIA INTERPLANETARIA EN ESPACIO PROFUNDO
// (NO es un anillo alrededor de los planetas, sino la ruta orbital)
// ══════════════════════════════════════════════════════════════
function InterplanetaryTrajectory() {
  const lines = useMemo(() => {
    const earthPos = new THREE.Vector3(0, 0, 0);
    const marsPos  = new THREE.Vector3(-52, 18, -50);
    const moonPos  = new THREE.Vector3(36, 10, -26);

    // Curva Tierra -> Marte
    const curveMars = new THREE.QuadraticBezierCurve3(
      earthPos,
      new THREE.Vector3(-20, 35, -20),
      marsPos,
    );
    // Curva Tierra -> Luna
    const curveMoon = new THREE.QuadraticBezierCurve3(
      earthPos,
      new THREE.Vector3(20, 18, -10),
      moonPos,
    );

    const geoMars = new THREE.BufferGeometry().setFromPoints(curveMars.getPoints(50));
    const geoMoon = new THREE.BufferGeometry().setFromPoints(curveMoon.getPoints(50));

    const matMars = new THREE.LineDashedMaterial({
      color: '#F2A64E',
      dashSize: 1.5,
      gapSize: 1.2,
      opacity: 0.12,
      transparent: true,
      depthWrite: false,
    });
    const matMoon = new THREE.LineDashedMaterial({
      color: '#c5e59e',
      dashSize: 1.2,
      gapSize: 1.0,
      opacity: 0.12,
      transparent: true,
      depthWrite: false,
    });

    const lineMars = new THREE.Line(geoMars, matMars);
    lineMars.computeLineDistances();

    const lineMoon = new THREE.Line(geoMoon, matMoon);
    lineMoon.computeLineDistances();

    return [lineMars, lineMoon];
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
// ESCENA COMPLETA DE FONDO
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
      {/* Estrellas estáticas en el fondo */}
      <Stars radius={300} depth={90} count={14000} factor={4.5} saturation={0} fade speed={isTraveling ? 4 : 1} />

      {/* Iluminación estelar (sol distante) */}
      <ambientLight intensity={0.25} />
      <pointLight position={[90, 90, 90]} intensity={4.5} color="#ffffff" />
      <pointLight position={[-70, -40, 30]} intensity={1.2} color="#4a9eff" />
      <pointLight position={[0, 0, 70]} intensity={0.6} color="#F2A64E" />

      {/* Planetas esféricos puros */}
      {PLANET_CONFIG.map(cfg => (
        <Planet
          key={cfg.id}
          config={cfg}
          isActive={currentPlanet === cfg.id}
        />
      ))}

      {/* Trayectorias interplanetarias discretas */}
      <InterplanetaryTrajectory />

      {/* Partículas de hiperespacio durante el viaje */}
      <WarpParticles isTraveling={isTraveling} />

      {/* Cámara guiada */}
      <CinematicCamera targetPos={activePlanet.pos} isTraveling={isTraveling} />
    </>
  );
}

// ══════════════════════════════════════════════════════════════
// EXPORT PRINCIPAL: VIAJE 100% AUTOMÁTICO EN BUCLE CONTINUO
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
        gl={{ antialias: true, alpha: false }}
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
