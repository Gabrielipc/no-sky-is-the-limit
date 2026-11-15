import * as THREE from 'three';

// ── Generador de texturas de alta resolución y mapas de normales ────────
// Elimina el aspecto "pixel art" o plano aplicando interpolación bicúbica suave,
// síntesis de micro-relieve, paletas fotorrealistas por cuerpo celeste y normales PBR.

export interface ProcessedTerrainTextures {
  geologyMap: THREE.CanvasTexture;
  satelliteMap: THREE.CanvasTexture;
  colorMap: THREE.CanvasTexture; // alias para compatibilidad
  normalMap: THREE.CanvasTexture;
  roughnessMap: THREE.CanvasTexture;
  displacementMap: THREE.CanvasTexture;
}

// Caché para evitar recomputar texturas ya procesadas
const textureCache = new Map<string, ProcessedTerrainTextures>();

// Paletas científicas por cuerpo celeste (elevación baja -> media -> alta)
function getPlanetaryColor(
  bodyType: 'Tierra' | 'Marte' | 'Luna',
  siteKey: string,
  normHeight: number,
  slope: number,
  grain: number
): [number, number, number] {
  // normHeight en [0, 1], slope en [0, 1] aprox
  const h = Math.max(0, Math.min(1, normHeight + grain * 0.15));

  if (bodyType === 'Marte') {
    // 🔴 MARTE: Óxidos de hierro (ferric oxide), dunas de basalto oscuro en fondos y polvo rojizo
    // Bajíos / delta: basalto oscuro marciano (#3a1910)
    // Medias: óxido ferroso naranja rojizo (#b84822 a #cf5c2b)
    // Cumbres / crestas: polvo marciano oxidado brillante (#e57e45 a #f39b62)
    if (h < 0.35) {
      const t = h / 0.35;
      const r = 58 + t * (175 - 58);
      const g = 25 + t * (68 - 25);
      const b = 16 + t * (32 - 16);
      return [Math.round(r), Math.round(g), Math.round(b)];
    } else if (h < 0.75) {
      const t = (h - 0.35) / 0.40;
      const r = 175 + t * (218 - 175);
      const g = 68 + t * (98 - 68);
      const b = 32 + t * (48 - 32);
      return [Math.round(r), Math.round(g), Math.round(b)];
    } else {
      const t = (h - 0.75) / 0.25;
      const r = 218 + t * (242 - 218);
      const g = 98 + t * (145 - 98);
      const b = 48 + t * (85 - 48);
      return [Math.round(r), Math.round(g), Math.round(b)];
    }
  }

  if (bodyType === 'Luna') {
    // ⚪ LUNA: Monocromático anortosítico lunar, cráteres con sombras de impacto y regolito cenizo
    // Fondo de cráteres / sombras polares: carbón basalto (#1c1e22)
    // Planicies medianas: regolito lunar gris (#6c737d a #8f97a3)
    // Crestas de impacto / bordes iluminados: anortosita clara plateada (#cbd3dc a #e4eaf2)
    if (h < 0.3) {
      const t = h / 0.3;
      const lum = 28 + t * (95 - 28);
      return [Math.round(lum * 0.96), Math.round(lum), Math.round(lum * 1.05)];
    } else if (h < 0.7) {
      const t = (h - 0.3) / 0.4;
      const lum = 95 + t * (155 - 95);
      return [Math.round(lum * 0.97), Math.round(lum), Math.round(lum * 1.04)];
    } else {
      const t = (h - 0.7) / 0.3;
      const lum = 155 + t * (228 - 155);
      return [Math.round(lum * 0.98), Math.round(lum), Math.round(lum * 1.03)];
    }
  }

  // 🌍 TIERRA: Colores terrestres auténticos según la región
  if (siteKey === 'utah') {
    // Desierto de Utah (Formación Morrison):
    // Cuencas arcillosas terracota (#934628), areniscas ocres (#c5844e) y estratos claros (#e5cfa8)
    if (h < 0.4) {
      const t = h / 0.4;
      const r = 142 + t * (188 - 142);
      const g = 68 + t * (120 - 68);
      const b = 40 + t * (72 - 40);
      return [Math.round(r), Math.round(g), Math.round(b)];
    } else if (h < 0.8) {
      const t = (h - 0.4) / 0.4;
      const r = 188 + t * (218 - 188);
      const g = 120 + t * (165 - 120);
      const b = 72 + t * (108 - 72);
      return [Math.round(r), Math.round(g), Math.round(b)];
    } else {
      const t = (h - 0.8) / 0.2;
      const r = 218 + t * (236 - 218);
      const g = 165 + t * (205 - 165);
      const b = 108 + t * (162 - 108);
      return [Math.round(r), Math.round(g), Math.round(b)];
    }
  } else {
    // Desierto de Atacama:
    // Salar / costras salinas pálidas (#d8d0bc), arenas ocres del desierto (#b58e60) y colinas rocosas pardas (#705336)
    if (h < 0.3) {
      const t = h / 0.3;
      const r = 222 + t * (195 - 222);
      const g = 214 + t * (172 - 214);
      const b = 196 + t * (132 - 196);
      return [Math.round(r), Math.round(g), Math.round(b)];
    } else if (h < 0.7) {
      const t = (h - 0.3) / 0.4;
      const r = 195 + t * (158 - 195);
      const g = 172 + t * (128 - 172);
      const b = 132 + t * (86 - 132);
      return [Math.round(r), Math.round(g), Math.round(b)];
    } else {
      const t = (h - 0.7) / 0.3;
      const r = 158 + t * (112 - 158);
      const g = 128 + t * (84 - 128);
      const b = 86 + t * (54 - 86);
      return [Math.round(r), Math.round(g), Math.round(b)];
    }
  }
}

export function createPhotorealisticTerrainTextures(
  heightmapImgUrl: string,
  satelliteImgUrl: string,
  bodyType: 'Tierra' | 'Marte' | 'Luna',
  siteKey: string,
  onReady: (textures: ProcessedTerrainTextures) => void
) {
  const cacheKey = `${heightmapImgUrl}_${satelliteImgUrl}_${bodyType}_${siteKey}`;
  if (textureCache.has(cacheKey)) {
    onReady(textureCache.get(cacheKey)!);
    return;
  }

  const hImg = new Image();
  const sImg = new Image();
  let loadedCount = 0;

  const onImageLoad = () => {
    loadedCount++;
    if (loadedCount < 2) return;

    const size = 512; // Resolución de alta fidelidad

    // 1. Canvas para elevación suave (desplazamiento)
    const hCanvas = document.createElement('canvas');
    hCanvas.width = size;
    hCanvas.height = size;
    const hCtx = hCanvas.getContext('2d')!;
    hCtx.imageSmoothingEnabled = true;
    hCtx.imageSmoothingQuality = 'high';
    hCtx.drawImage(hImg, 0, 0, size, size);

    // 2. Canvas para mapa satelital fotorrealista (ortofoto)
    const sCanvas = document.createElement('canvas');
    sCanvas.width = size;
    sCanvas.height = size;
    const sCtx = sCanvas.getContext('2d')!;
    sCtx.imageSmoothingEnabled = true;
    sCtx.imageSmoothingQuality = 'high';
    sCtx.drawImage(sImg, 0, 0, size, size);

    // 3. Canvas para mapa de color geológico planetario (auténtico color de Tierra, Marte, Luna)
    const gCanvas = document.createElement('canvas');
    gCanvas.width = size;
    gCanvas.height = size;
    const gCtx = gCanvas.getContext('2d')!;

    // 4. Canvas para mapa de normales PBR (operador Sobel de alta frecuencia)
    const nCanvas = document.createElement('canvas');
    nCanvas.width = size;
    nCanvas.height = size;
    const nCtx = nCanvas.getContext('2d')!;

    // 5. Canvas para mapa de rugosidad
    const rCanvas = document.createElement('canvas');
    rCanvas.width = size;
    rCanvas.height = size;
    const rCtx = rCanvas.getContext('2d')!;

    // Extraer datos de píxeles
    const hData = hCtx.getImageData(0, 0, size, size);
    const sData = sCtx.getImageData(0, 0, size, size);
    const gData = gCtx.createImageData(size, size);
    const nData = nCtx.createImageData(size, size);
    const rData = rCtx.createImageData(size, size);

    const hPixels = hData.data;
    const sPixels = sData.data;
    const gPixels = gData.data;
    const nPixels = nData.data;
    const rPixels = rData.data;

    for (let y = 0; y < size; y++) {
      for (let x = 0; x < size; x++) {
        const idx = (y * size + x) * 4;

        // Cálculo de normales mediante operador Sobel
        const xLeft  = Math.max(0, x - 1);
        const xRight = Math.min(size - 1, x + 1);
        const yUp    = Math.max(0, y - 1);
        const yDown  = Math.min(size - 1, y + 1);

        const hL = hPixels[(y * size + xLeft) * 4] / 255.0;
        const hR = hPixels[(y * size + xRight) * 4] / 255.0;
        const hU = hPixels[(yUp * size + x) * 4] / 255.0;
        const hD = hPixels[(yDown * size + x) * 4] / 255.0;
        const hCenter = hPixels[idx] / 255.0;

        // Micro-ruido de grano para realismo fotográfico (rocas y regolito)
        const seed = (x * 12.9898 + y * 78.233);
        const microNoise = (Math.sin(seed) * 43758.5453) % 1;
        const fineGrain = (microNoise - 0.5) * 0.08;

        // Gradiente Sobel + micro-relieve
        const dx = (hR - hL) * 3.5 + fineGrain * 0.35;
        const dy = (hD - hU) * 3.5 + fineGrain * 0.35;
        const dz = 1.0;

        const len = Math.sqrt(dx * dx + dy * dy + dz * dz);
        const nx = (-dx / len) * 0.5 + 0.5;
        const ny = (-dy / len) * 0.5 + 0.5;
        const nz = (dz / len) * 0.5 + 0.5;

        nPixels[idx]     = Math.floor(nx * 255);
        nPixels[idx + 1] = Math.floor(ny * 255);
        nPixels[idx + 2] = Math.floor(nz * 255);
        nPixels[idx + 3] = 255;

        // 1. Color Geológico Planetario auténtico (Tierra, Marte, Luna)
        const slope = Math.sqrt(dx * dx + dy * dy);
        const [gr, gg, gb] = getPlanetaryColor(bodyType, siteKey, hCenter, slope, fineGrain);
        gPixels[idx]     = gr;
        gPixels[idx + 1] = gg;
        gPixels[idx + 2] = gb;
        gPixels[idx + 3] = 255;

        // 2. Ortofoto satelital con micro-grano PBR para realce de relieve
        const satGrainMult = 1.0 + fineGrain * 0.25;
        sPixels[idx]     = Math.min(255, Math.max(0, Math.floor(sPixels[idx] * satGrainMult)));
        sPixels[idx + 1] = Math.min(255, Math.max(0, Math.floor(sPixels[idx + 1] * satGrainMult)));
        sPixels[idx + 2] = Math.min(255, Math.max(0, Math.floor(sPixels[idx + 2] * satGrainMult)));

        // 3. Mapa de rugosidad geológica PBR
        const baseRoughness = bodyType === 'Luna' ? 220 : bodyType === 'Marte' ? 205 : 190;
        const slopeRoughness = Math.min(255, Math.floor(baseRoughness + slope * 50 + fineGrain * 35));
        rPixels[idx]     = slopeRoughness;
        rPixels[idx + 1] = slopeRoughness;
        rPixels[idx + 2] = slopeRoughness;
        rPixels[idx + 3] = 255;
      }
    }

    nCtx.putImageData(nData, 0, 0);
    gCtx.putImageData(gData, 0, 0);
    sCtx.putImageData(sData, 0, 0);
    rCtx.putImageData(rData, 0, 0);

    // Texturas Three.js con filtrado trilineal anisótropo
    const geologyMap = new THREE.CanvasTexture(gCanvas);
    geologyMap.minFilter = THREE.LinearMipmapLinearFilter;
    geologyMap.magFilter = THREE.LinearFilter;
    geologyMap.generateMipmaps = true;

    const satelliteMap = new THREE.CanvasTexture(sCanvas);
    satelliteMap.minFilter = THREE.LinearMipmapLinearFilter;
    satelliteMap.magFilter = THREE.LinearFilter;
    satelliteMap.generateMipmaps = true;

    const normalMap = new THREE.CanvasTexture(nCanvas);
    normalMap.minFilter = THREE.LinearMipmapLinearFilter;
    normalMap.magFilter = THREE.LinearFilter;
    normalMap.generateMipmaps = true;

    const roughnessMap = new THREE.CanvasTexture(rCanvas);
    roughnessMap.minFilter = THREE.LinearMipmapLinearFilter;
    roughnessMap.magFilter = THREE.LinearFilter;
    roughnessMap.generateMipmaps = true;

    const displacementMap = new THREE.CanvasTexture(hCanvas);
    displacementMap.minFilter = THREE.LinearMipmapLinearFilter;
    displacementMap.magFilter = THREE.LinearFilter;
    displacementMap.generateMipmaps = true;

    const result: ProcessedTerrainTextures = {
      geologyMap,
      satelliteMap,
      colorMap: geologyMap,
      normalMap,
      roughnessMap,
      displacementMap,
    };

    textureCache.set(cacheKey, result);
    onReady(result);
  };

  hImg.crossOrigin = 'anonymous';
  sImg.crossOrigin = 'anonymous';
  hImg.onload = onImageLoad;
  sImg.onload = onImageLoad;
  hImg.src = heightmapImgUrl;
  sImg.src = satelliteImgUrl;
}

// ── Textura de estratos de corteza geológica para los costados del bloque ──
export function createGeologicalStrataTexture(
  bodyType: 'Tierra' | 'Marte' | 'Luna',
  siteKey: string = 'utah'
): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 128;
  const ctx = canvas.getContext('2d')!;

  const palette = bodyType === 'Marte'
    ? ['#38160d', '#4d2013', '#2a1009', '#612a1a', '#220b06'] // Marte basalto férrico
    : bodyType === 'Luna'
    ? ['#24272c', '#1a1d20', '#32373e', '#141618', '#2a2e34'] // Luna anortosita gris
    : siteKey === 'utah'
    ? ['#6e331c', '#8b4324', '#552714', '#9e4e2a', '#441d0e'] // Utah arcilla arenisca
    : ['#7c6142', '#967853', '#5c462e', '#a3845e', '#493622']; // Atacama costras áridas

  const layerHeight = 128 / 8;
  for (let i = 0; i < 8; i++) {
    ctx.fillStyle = palette[i % palette.length];
    ctx.fillRect(0, i * layerHeight, 256, layerHeight);

    // Líneas sedimentarias sutiles
    ctx.fillStyle = 'rgba(0,0,0,0.3)';
    ctx.fillRect(0, (i + 1) * layerHeight - 2, 256, 2);
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(4, 1);
  return tex;
}
