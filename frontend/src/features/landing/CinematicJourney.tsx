import React, { useRef, useMemo, useState } from 'react';
import { Canvas, useFrame, useLoader } from '@react-three/fiber';
import { Sphere, Stars, Float, Text, PerspectiveCamera, Environment, Points, PointMaterial } from '@react-three/drei';
import * as THREE from 'three';

// Shaders para atmósfera cinemática
const atmosphereVertexShader = `
  varying vec3 vNormal;
  varying vec3 vPosition;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    vPosition = (modelViewMatrix * vec4(position, 1.0)).xyz;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const atmosphereFragmentShader = `
  varying vec3 vNormal;
  varying vec3 vPosition;
  uniform vec3 color;
  uniform float coeficient;
  uniform float power;
  void main() {
    float intensity = pow(coeficient - dot(vNormal, vec3(0, 0, 1.0)), power);
    gl_FragColor = vec4(color, intensity);
  }
`;

const SpaceParticles = ({ count = 2000 }) => {
  const points = useMemo(() => {
    const p = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      p[i * 3] = (Math.random() - 0.5) * 100;
      p[i * 3 + 1] = (Math.random() - 0.5) * 100;
      p[i * 3 + 2] = (Math.random() - 0.5) * 100;
    }
    return p;
  }, [count]);

  const ref = useRef<THREE.Points>(null);
  useFrame((state) => {
    if (ref.current) {
      ref.current.rotation.y += 0.0005;
      ref.current.rotation.x += 0.0002;
    }
  });

  return (
    <Points ref={ref} positions={points} stride={3} frustumCulled={false}>
      <PointMaterial
        transparent
        color="#ffffff"
        size={0.05}
        sizeAttenuation={true}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </Points>
  );
};

const Planet = ({ 
  position, 
  textureUrl, 
  size, 
  label, 
  sublabel,
  isActive,
  color,
  onClick 
}: { 
  position: [number, number, number], 
  textureUrl: string, 
  size: number, 
  label: string, 
  sublabel: string,
  isActive: boolean,
  color: string,
  onClick: () => void
}) => {
  const meshRef = useRef<THREE.Mesh>(null);
  const atmosphereRef = useRef<THREE.ShaderMaterial>(null);
  const texture = useLoader(THREE.TextureLoader, textureUrl);

  useFrame((state) => {
    if (meshRef.current) {
      meshRef.current.rotation.y += 0.002;
    }
  });

  return (
    <group position={position} onClick={onClick}>
      <Float speed={2} rotationIntensity={0.5} floatIntensity={0.5}>
        {/* Cuerpo del planeta */}
        <Sphere ref={meshRef} args={[size, 64, 64]}>
          <meshStandardMaterial 
            map={texture} 
            roughness={0.8}
            metalness={0.1}
            emissive={isActive ? new THREE.Color(color).multiplyScalar(0.3) : new THREE.Color(0x000000)}
          />
        </Sphere>
        
        {/* Atmósfera Cinematográfica con Shader */}
        <Sphere args={[size * 1.15, 64, 64]}>
          <shaderMaterial
            ref={atmosphereRef}
            vertexShader={atmosphereVertexShader}
            fragmentShader={atmosphereFragmentShader}
            uniforms={{
              color: { value: new THREE.Color(color) },
              coeficient: { value: 0.8 },
              power: { value: 2.5 }
            }}
            transparent
            side={THREE.BackSide}
            blending={THREE.AdditiveBlending}
          />
        </Sphere>

        {/* Resplandor externo suave */}
        <Sphere args={[size * 1.3, 32, 32]}>
          <meshBasicMaterial 
            color={color}
            transparent 
            opacity={0.03}
            side={THREE.BackSide}
          />
        </Sphere>
      </Float>
      
      {/* Etiqueta UI 3D */}
      <group position={[0, size + 2.5, 0]}>
        <Text
          fontSize={size * 0.35}
          color="white"
          anchorX="center"
          anchorY="middle"
          font="/fonts/Inter-Bold.ttf"
        >
          {label}
        </Text>
        <Text
          fontSize={size * 0.18}
          color={color}
          position={[0, -size * 0.3, 0]}
          anchorX="center"
          anchorY="middle"
        >
          {sublabel}
        </Text>
      </group>
    </group>
  );
};

const CinematicCamera = ({ targetPosition, isTraveling }: { targetPosition: [number, number, number], isTraveling: boolean }) => {
  const cameraRef = useRef<THREE.PerspectiveCamera>(null);
  const vec = new THREE.Vector3();
  const lookAtVec = new THREE.Vector3();

  useFrame((state) => {
    if (cameraRef.current) {
      const target = vec.set(...targetPosition);
      const dist = target.length();
      
      // Movimiento de cámara cinemático: Dolly Zoom + Shake suave
      const time = state.clock.getElapsedTime();
      const shake = new THREE.Vector3(
        Math.sin(time * 2) * 0.05,
        Math.cos(time * 1.5) * 0.05,
        0
      );

      const baseOffset = new THREE.Vector3(0, dist > 0 ? 5 : 8, dist > 0 ? 15 : 25);
      const idealPosition = target.clone().add(baseOffset).add(shake);
      
      // Suavizado dinámico basado en si está viajando
      const lerpFactor = isTraveling ? 0.02 : 0.08;
      state.camera.position.lerp(idealPosition, lerpFactor);
      
      lookAtVec.lerp(target, 0.1);
      state.camera.lookAt(lookAtVec);

      // Ajuste de FOV para efecto de velocidad
      if (isTraveling) {
        state.camera.fov = THREE.MathUtils.lerp(state.camera.fov, 55, 0.05);
      } else {
        state.camera.fov = THREE.MathUtils.lerp(state.camera.fov, 45, 0.05);
      }
      state.camera.updateProjectionMatrix();
    }
  });

  return <PerspectiveCamera ref={cameraRef} makeDefault />;
};

export const CinematicJourney = ({ 
  currentPlanet, 
  onPlanetSelect,
  isMatching = false
}: { 
  currentPlanet: string, 
  onPlanetSelect: (id: string) => void,
  isMatching?: boolean
}) => {
  const [isTraveling, setIsTraveling] = useState(false);
  
  const planets = useMemo(() => [
    { id: 'earth', name: 'TIERRA', sub: 'PUNTO DE ORIGEN', pos: [0, 0, 0], size: 6, tex: '/textures/earth.png', color: '#4a9eff' },
    { id: 'moon', name: 'LUNA', sub: 'MISIÓN ARTEMIS', pos: [40, 15, -30], size: 2, tex: '/textures/mars.png', color: '#d1d1d1' },
    { id: 'mars', name: 'MARTE', sub: 'CRÁTER JEZERO', pos: [-60, 25, -60], size: 4.5, tex: '/textures/mars.png', color: '#ff6b4a' },
  ], []);

  const activePlanet = planets.find(p => p.id === currentPlanet) || planets[0];

  useEffect(() => {
    setIsTraveling(true);
    const timer = setTimeout(() => setIsTraveling(false), 2000);
    return () => clearTimeout(timer);
  }, [currentPlanet]);

  return (
    <div style={{ width: '100%', height: '100%', position: 'absolute', top: 0, left: 0 }}>
      <Canvas shadows dpr={[1, 2]} gl={{ antialias: true }}>
        <color attach="background" args={['#020406']} />
        
        {/* Efectos de Ambiente Cinematográfico */}
        <Stars radius={200} depth={60} count={10000} factor={5} saturation={0} fade speed={2} />
        <SpaceParticles count={3000} />
        
        <ambientLight intensity={0.4} />
        <pointLight position={[100, 100, 100]} intensity={3} color="#ffffff" />
        <pointLight position={[-50, -50, -50]} intensity={1.5} color="#4a9eff" />
        
        <Environment preset="night" />

        <CinematicCamera 
          targetPosition={activePlanet.pos as [number, number, number]} 
          isTraveling={isTraveling || isMatching}
        />

        {planets.map((planet) => (
          <Planet
            key={planet.id}
            position={planet.pos as [number, number, number]}
            textureUrl={planet.tex}
            size={planet.size}
            label={planet.name}
            sublabel={planet.sub}
            color={planet.color}
            isActive={currentPlanet === planet.id}
            onClick={() => onPlanetSelect(planet.id)}
          />
        ))}

        {/* Líneas de Trayectoria Hiperespacial */}
        {planets.slice(0, -1).map((p, i) => (
          <line key={i}>
            <bufferGeometry attach="geometry">
              <bufferAttribute
                attach="attributes-position"
                count={2}
                array={new Float32Array([...p.pos, ...planets[i+1].pos])}
                itemSize={3}
              />
            </bufferGeometry>
            <lineBasicMaterial attach="material" color="#F2A64E" opacity={0.05} transparent />
          </line>
        ))}
      </Canvas>
    </div>
  );
};
