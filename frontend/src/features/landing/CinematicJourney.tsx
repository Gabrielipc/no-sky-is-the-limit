import React, { useRef, useMemo, useEffect } from 'react';
import { Canvas, useFrame, useLoader } from '@react-three/fiber';
import { Sphere, Stars, Float, Text, PerspectiveCamera, Environment, Trail } from '@react-three/drei';
import * as THREE from 'three';

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
  const texture = useLoader(THREE.TextureLoader, textureUrl);

  useFrame((state) => {
    if (meshRef.current) {
      meshRef.current.rotation.y += 0.001;
    }
  });

  return (
    <group position={position} onClick={onClick}>
      <Float speed={1.5} rotationIntensity={0.2} floatIntensity={0.5}>
        <Sphere ref={meshRef} args={[size, 64, 64]}>
          <meshStandardMaterial 
            map={texture} 
            roughness={0.7}
            metalness={0.2}
            emissive={isActive ? new THREE.Color(color).multiplyScalar(0.2) : new THREE.Color(0x000000)}
          />
        </Sphere>
        
        {/* Atmosphere/Glow */}
        <Sphere args={[size * 1.05, 64, 64]}>
          <meshStandardMaterial 
            color={color}
            transparent 
            opacity={0.05}
            side={THREE.BackSide}
          />
        </Sphere>
      </Float>
      
      {/* Label UI */}
      <group position={[0, size + 2, 0]}>
        <Text
          fontSize={size * 0.3}
          color="white"
          anchorX="center"
          anchorY="middle"
          outlineWidth={0.05}
          outlineColor="#000"
        >
          {label}
        </Text>
        <Text
          fontSize={size * 0.15}
          color="#F2A64E"
          position={[0, -size * 0.25, 0]}
          anchorX="center"
          anchorY="middle"
        >
          {sublabel}
        </Text>
      </group>
    </group>
  );
};

const JourneyCamera = ({ targetPosition, zoomLevel = 1 }: { targetPosition: [number, number, number], zoomLevel?: number }) => {
  const cameraRef = useRef<THREE.PerspectiveCamera>(null);
  const vec = new THREE.Vector3();

  useFrame((state) => {
    if (cameraRef.current) {
      const target = vec.set(...targetPosition);
      const dist = target.length();
      // Adjust offset based on zoomLevel
      const baseOffset = new THREE.Vector3(0, dist > 0 ? 3 : 5, dist > 0 ? 10 : 15);
      const idealPosition = target.clone().add(baseOffset.multiplyScalar(zoomLevel));
      
      state.camera.position.lerp(idealPosition, 0.03);
      state.camera.lookAt(target);
    }
  });

  return <PerspectiveCamera ref={cameraRef} makeDefault fov={45} />;
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
  const planets = useMemo(() => [
    { id: 'earth', name: 'TIERRA', sub: 'Punto de Partida', pos: [0, 0, 0], size: 5, tex: '/textures/earth.png', color: '#4a9eff' },
    { id: 'moon', name: 'LUNA', sub: 'Misión Artemis', pos: [25, 10, -25], size: 1.8, tex: '/textures/mars.png', color: '#ffffff' },
    { id: 'mars', name: 'MARTE', sub: 'Cráter Jezero', pos: [-40, 15, -45], size: 3.5, tex: '/textures/mars.png', color: '#ff6b4a' },
  ], []);

  const activePlanet = planets.find(p => p.id === currentPlanet) || planets[0];

  return (
    <div style={{ width: '100%', height: '100%', position: 'absolute', top: 0, left: 0 }}>
      <Canvas shadows dpr={[1, 2]}>
        <color attach="background" args={['#05070a']} />
        <Stars radius={150} depth={50} count={7000} factor={4} saturation={0} fade speed={1} />
        
        <ambientLight intensity={0.5} />
        <pointLight position={[100, 100, 100]} intensity={2.5} color="#fff" />
        <pointLight position={[-50, -50, -50]} intensity={1} color="#4a9eff" />
        
        <Environment preset="night" />

        <JourneyCamera 
          targetPosition={activePlanet.pos as [number, number, number]} 
          zoomLevel={isMatching ? 0.4 : 1}
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

        {/* Trail effect connecting planets */}
        <Trail
          width={1}
          length={8}
          color={new THREE.Color('#F2A64E')}
          attenuation={(t) => t * t}
        >
          <mesh position={activePlanet.pos as [number, number, number]}>
            <sphereGeometry args={[0.1]} />
            <meshBasicMaterial color="#F2A64E" transparent opacity={0} />
          </mesh>
        </Trail>

        {/* Cinematic Path Lines */}
        <line>
          <bufferGeometry attach="geometry">
            <bufferAttribute
              attach="attributes-position"
              count={3}
              array={new Float32Array([...planets[0].pos, ...planets[1].pos, ...planets[2].pos])}
              itemSize={3}
            />
          </bufferGeometry>
          <lineBasicMaterial attach="material" color="#F2A64E" opacity={0.1} transparent />
        </line>
      </Canvas>
    </div>
  );
};
