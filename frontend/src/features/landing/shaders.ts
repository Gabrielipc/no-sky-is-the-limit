// ============================================================
// GLSL Procedural Shaders — Regolith Atlas
// Texturas 100% procedurales: sin PNG de plataforma externa
// Paleta alineada a tokens.css
// ============================================================

// ── Noise helpers compartidos (FBm) ─────────────────────────
const NOISE_HELPERS = /* glsl */ `
  // Hash sin
  float hash(vec2 p) {
    p = fract(p * vec2(234.34, 435.345));
    p += dot(p, p + 34.23);
    return fract(p.x * p.y);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(hash(i + vec2(0,0)), hash(i + vec2(1,0)), u.x),
      mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), u.x),
      u.y
    );
  }

  float fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    for(int i = 0; i < 6; i++) {
      v += a * noise(p);
      p = p * 2.1 + vec2(1.7, 9.2);
      a *= 0.5;
    }
    return v;
  }

  float fbm3(vec3 p) {
    return fbm(p.xy + p.z * 0.3) * 0.6 + fbm(p.yz * 1.3) * 0.4;
  }
`;

// ══════════════════════════════════════════════════════════════
// TIERRA — océano azul + continentes + nubes procedurales
// ══════════════════════════════════════════════════════════════
export const earthVertexShader = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vPosition;
  varying vec2 vUv;
  void main() {
    vUv = uv;
    vNormal = normalize(normalMatrix * normal);
    vPosition = (modelMatrix * vec4(position, 1.0)).xyz;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const earthFragmentShader = /* glsl */ `
  ${NOISE_HELPERS}
  varying vec3 vNormal;
  varying vec3 vPosition;
  varying vec2 vUv;
  uniform float uTime;

  void main() {
    vec2 uv = vUv;
    
    // Coordenadas esféricas para el noise
    vec3 np = normalize(vPosition) * 2.5;
    
    // Masa continental base
    float continent = fbm3(np + vec3(1.3, 2.1, 0.7));
    float isLand = smoothstep(0.47, 0.53, continent);
    
    // Colores de base
    vec3 oceanDeep  = vec3(0.08, 0.22, 0.52);  // azul profundo
    vec3 oceanShelf = vec3(0.12, 0.35, 0.65);  // azul agua
    vec3 landLow    = vec3(0.18, 0.28, 0.14);  // verde oscuro
    vec3 landHigh   = vec3(0.38, 0.30, 0.18);  // café/tierra
    vec3 ice        = vec3(0.88, 0.92, 0.95);  // casquetes polares

    // Mezcla de océano con profundidad
    float depthNoise = fbm3(np * 1.8 + vec3(5.0));
    vec3 ocean = mix(oceanDeep, oceanShelf, depthNoise * 0.6);

    // Mezcla de tierra con relieve
    float elevation = fbm3(np * 3.0 + vec3(2.5));
    vec3 land = mix(landLow, landHigh, smoothstep(0.4, 0.7, elevation));

    // Casquetes polares (latitud)
    float lat = abs(vUv.y - 0.5) * 2.0;
    float polarIce = smoothstep(0.78, 0.92, lat);
    land = mix(land, ice, polarIce);
    ocean = mix(ocean, ice, polarIce * 0.6);

    // Nubes procedurales rotantes
    float cloudSpeed = uTime * 0.012;
    float cloud = fbm(uv * 6.0 + vec2(cloudSpeed, 0.0));
    cloud = smoothstep(0.52, 0.72, cloud);
    vec3 cloudColor = vec3(0.95, 0.96, 0.98);

    // Color final de superficie
    vec3 surface = mix(ocean, land, isLand);
    surface = mix(surface, cloudColor, cloud * 0.85);

    // Iluminación simple (fresnel + diffuse)
    vec3 lightDir = normalize(vec3(5.0, 3.0, 5.0));
    float diff = max(0.0, dot(vNormal, lightDir));
    float fresnel = pow(1.0 - max(0.0, dot(vNormal, vec3(0,0,1))), 3.0);
    
    // Especular oceánico
    float spec = 0.0;
    if (isLand < 0.5) {
      vec3 halfVec = normalize(lightDir + vec3(0,0,1));
      spec = pow(max(0.0, dot(vNormal, halfVec)), 32.0) * 0.4;
    }

    vec3 color = surface * (0.15 + 0.85 * diff) + spec;
    // Rim atmosférico azul
    color += vec3(0.1, 0.3, 0.8) * fresnel * 0.5;

    gl_FragColor = vec4(color, 1.0);
  }
`;

// ══════════════════════════════════════════════════════════════
// LUNA — gris craterizado + regiones mare oscuras
// ══════════════════════════════════════════════════════════════
export const moonVertexShader = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vPosition;
  varying vec2 vUv;
  void main() {
    vUv = uv;
    vNormal = normalize(normalMatrix * normal);
    vPosition = (modelMatrix * vec4(position, 1.0)).xyz;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const moonFragmentShader = /* glsl */ `
  ${NOISE_HELPERS}
  varying vec3 vNormal;
  varying vec3 vPosition;
  varying vec2 vUv;

  // Cráteres via SDF circular en espacio 3D
  float crater(vec3 p, vec3 center, float radius) {
    float d = distance(p, center);
    float rim = smoothstep(radius * 1.1, radius, d);
    float floor = smoothstep(radius * 0.4, radius * 0.5, d);
    return rim - floor * 0.3;
  }

  void main() {
    vec3 np = normalize(vPosition);

    // Base gris lunar con variación sutil
    float base = fbm3(np * 3.5 + vec3(7.1));
    vec3 highland = vec3(0.72, 0.70, 0.68);  // gris claro
    vec3 mare     = vec3(0.28, 0.27, 0.26);  // gris oscuro (mare)

    // Regiones mare basaltáticas
    float mareMap = fbm3(np * 1.5 + vec3(3.3));
    float isMare = smoothstep(0.52, 0.56, mareMap);
    vec3 surface = mix(highland, mare, isMare);

    // Cráteres principales
    float c1 = crater(np, normalize(vec3(0.6, 0.4, 0.7)), 0.18);
    float c2 = crater(np, normalize(vec3(-0.5, -0.6, 0.6)), 0.12);
    float c3 = crater(np, normalize(vec3(0.1, 0.8, 0.6)), 0.09);
    float c4 = crater(np, normalize(vec3(-0.3, 0.2, 0.9)), 0.22); // Shackleton
    float c5 = crater(np, normalize(vec3(0.7, -0.2, 0.7)), 0.07);

    // Ruido fino de regolito
    float regolith = fbm3(np * 12.0) * 0.08;

    surface += (c1 + c2 + c3 + c4 + c5) * 0.12 + regolith;
    surface = clamp(surface, 0.0, 1.0);

    // Spot del Polo Sur (Artemis / Shackleton) — tinte azulado frío
    float poleLat = abs(np.y);
    float poleGlow = smoothstep(0.75, 0.95, poleLat);
    surface = mix(surface, vec3(0.6, 0.65, 0.75), poleGlow * 0.4);

    // Iluminación
    vec3 lightDir = normalize(vec3(5.0, 3.0, 5.0));
    float diff = max(0.0, dot(vNormal, lightDir));
    float ambient = 0.08;
    float fresnel = pow(1.0 - max(0.0, dot(vNormal, vec3(0,0,1))), 4.0);

    vec3 color = surface * (ambient + (1.0 - ambient) * diff);
    // Sin atmósfera, rim casi inexistente
    color += vec3(0.2, 0.22, 0.28) * fresnel * 0.15;

    gl_FragColor = vec4(color, 1.0);
  }
`;

// ══════════════════════════════════════════════════════════════
// MARTE — rojo-naranja, polvo, Cráter Jezero marcado
// ══════════════════════════════════════════════════════════════
export const marsVertexShader = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vPosition;
  varying vec2 vUv;
  void main() {
    vUv = uv;
    vNormal = normalize(normalMatrix * normal);
    vPosition = (modelMatrix * vec4(position, 1.0)).xyz;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const marsFragmentShader = /* glsl */ `
  ${NOISE_HELPERS}
  varying vec3 vNormal;
  varying vec3 vPosition;
  varying vec2 vUv;
  uniform float uTime;

  void main() {
    vec3 np = normalize(vPosition);

    // Colores marcianos
    vec3 basaltDark  = vec3(0.42, 0.18, 0.09);  // rojo-café oscuro
    vec3 dustLight   = vec3(0.78, 0.42, 0.24);  // anaranjado polvo
    vec3 poleIce     = vec3(0.88, 0.84, 0.80);  // casquete polar CO2
    vec3 vallesColor = vec3(0.32, 0.12, 0.06);  // cañones oscuros

    // Mapa base con variación FBm
    float elevation = fbm3(np * 2.5 + vec3(1.1, 3.3, 5.5));
    vec3 surface = mix(basaltDark, dustLight, smoothstep(0.35, 0.65, elevation));

    // Valles Marineris — franja ecuatorial oscura
    float valles = smoothstep(0.06, 0.0, abs(np.y - 0.0)) * smoothstep(-0.1, 0.5, np.x);
    surface = mix(surface, vallesColor, valles * 0.5);

    // Casquetes polares
    float polar = smoothstep(0.72, 0.88, abs(np.y));
    surface = mix(surface, poleIce, polar);

    // Spot del Cráter Jezero (posición aproximada: lat ~18°N, lon ~77°E)
    vec3 jezeroDir = normalize(vec3(0.22, 0.31, 0.92));
    float jDist = distance(np, jezeroDir);
    float jezeroRim  = smoothstep(0.14, 0.12, jDist);
    float jezeroFloor = smoothstep(0.06, 0.08, jDist);
    float jezeroRing  = jezeroRim - jezeroFloor * 0.6;
    // Delta fan marcado con tono más claro
    float fan = smoothstep(0.055, 0.04, distance(np, jezeroDir + vec3(-0.02, 0.01, 0.0)));
    surface = mix(surface, vec3(0.88, 0.60, 0.35), jezeroRing * 0.6 + fan * 0.9);

    // Halo dorado de Jezero (pulso suave — indica el sitio análogo)
    float jezeroPulse = sin(uTime * 2.0) * 0.5 + 0.5;
    vec3 jezeroGlow = vec3(0.95, 0.65, 0.19) * jezeroRing * jezeroPulse * 0.3;

    // Polvo atmosférico fino
    float dust = fbm3(np * 8.0 + vec3(uTime * 0.005)) * 0.06;
    surface += dust;
    surface = clamp(surface + jezeroGlow, 0.0, 1.0);

    // Iluminación
    vec3 lightDir = normalize(vec3(5.0, 3.0, 5.0));
    float diff = max(0.0, dot(vNormal, lightDir));
    float ambient = 0.12;
    float fresnel = pow(1.0 - max(0.0, dot(vNormal, vec3(0,0,1))), 3.0);

    vec3 color = surface * (ambient + (1.0 - ambient) * diff);
    // Atmósfera marciana — tinte rojizo sutil
    color += vec3(0.6, 0.25, 0.1) * fresnel * 0.35;

    gl_FragColor = vec4(color, 1.0);
  }
`;

// ══════════════════════════════════════════════════════════════
// ATMÓSFERA — Shader Fresnel compartido
// ══════════════════════════════════════════════════════════════
export const atmosphereVertexShader = /* glsl */ `
  varying vec3 vNormal;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const atmosphereFragmentShader = /* glsl */ `
  varying vec3 vNormal;
  uniform vec3 uColor;
  uniform float uIntensity;
  void main() {
    float fresnel = pow(1.0 - abs(dot(vNormal, vec3(0.0, 0.0, 1.0))), 3.0);
    gl_FragColor = vec4(uColor * fresnel * uIntensity, fresnel * uIntensity);
  }
`;

// ══════════════════════════════════════════════════════════════
// WARP PARTICLES — efecto hyperspace en viaje
// ══════════════════════════════════════════════════════════════
export const warpVertexShader = /* glsl */ `
  attribute float aSpeed;
  uniform float uProgress;
  uniform float uTime;
  varying float vOpacity;
  void main() {
    vec3 pos = position;
    // Acelerar hacia adelante según el progreso del warp
    pos.z -= uProgress * aSpeed * 50.0;
    // Streaking radial
    float dist = length(pos.xy);
    vOpacity = smoothstep(1.0, 0.0, uProgress) * 0.8 + uProgress * 0.9;
    vOpacity *= (1.0 - smoothstep(0.0, 80.0, dist));
    gl_PointSize = mix(1.0, 3.0, uProgress);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  }
`;

export const warpFragmentShader = /* glsl */ `
  varying float vOpacity;
  uniform vec3 uColor;
  void main() {
    float d = distance(gl_PointCoord, vec2(0.5));
    if (d > 0.5) discard;
    gl_FragColor = vec4(uColor, vOpacity * (1.0 - d * 2.0));
  }
`;

