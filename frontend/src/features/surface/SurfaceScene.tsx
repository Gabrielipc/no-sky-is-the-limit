import { useEffect, useRef, useState } from 'react';
import {
  ArcGISTiledElevationTerrainProvider, BoundingSphere, Cartesian3, Cesium3DTileset, CesiumTerrainProvider,
  Color, ComponentDatatype, CustomHeightmapTerrainProvider, Ellipsoid, EllipsoidTerrainProvider,
  GeographicProjection, GeographicTilingScheme, Geometry, GeometryAttribute, GeometryAttributes, GeometryInstance, GeometryPipeline,
  Globe, HeadingPitchRange, HeightReference, ImageryLayer, Material, MaterialAppearance, Math as CesiumMath,
  Matrix4, Primitive, PrimitiveType, SingleTileImageryProvider, Transforms, Viewer,
} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import { asset, pixels } from './assets';
import { decodeGray, decodeMola, meshArrays, type SurfaceManifest, type SurfaceMode, type SurfaceSite, type RemoteLayer } from './terrain';

const earthTerrain = 'https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer';
const duration = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 2.4;

type Props = { site: SurfaceSite; manifest: SurfaceManifest; mode: SurfaceMode; exaggeration: number; texture: 'relief' | 'height'; remote: RemoteLayer };
export default function SurfaceScene({ site, manifest, mode, exaggeration, texture, remote }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const [ready, setReady] = useState(false);
  const [heights, setHeights] = useState<Float32Array | null>(null);
  const [error, setError] = useState('');
  const [terrainStatus, setTerrainStatus] = useState('Preparando relieve…');
  const [remoteStatus, setRemoteStatus] = useState('');
  const [meshError, setMeshError] = useState('');
  const [altitude, setAltitude] = useState('');
  const [attempt, setAttempt] = useState(0);
  const meshRef = useRef<Primitive | null>(null);
  const tilesRef = useRef<Cesium3DTileset | null>(null);
  const modeRef = useRef(mode); modeRef.current = mode;
  const [frame, setFrame] = useState(0);
  const remoteTerrainURL = remote?.kind === 'terrain' ? remote.url : null;
  const mars = site.body === 'Mars';

  useEffect(() => {
    if (!container.current) return;
    const controller = new AbortController();
    let viewer: Viewer | undefined;
    let removeChanged: (() => void) | undefined;
    let removeRenderError: (() => void) | undefined;
    let disposed = false;
    setError(''); setMeshError(''); setHeights(null); setReady(false);
    const ellipsoid = mars ? new Ellipsoid(manifest.mola.radius_m,manifest.mola.radius_m,manifest.mola.radius_m) : Ellipsoid.WGS84;
    try {
      viewer = new Viewer(container.current, {
        ellipsoid, globe: new Globe(ellipsoid), mapProjection: new GeographicProjection(ellipsoid),
        terrainProvider: new EllipsoidTerrainProvider({ ellipsoid }), baseLayer: false,
        baseLayerPicker: false, geocoder: false, homeButton: false, sceneModePicker: false,
        navigationHelpButton: false, animation: false, timeline: false, fullscreenButton: false,
        infoBox: false, selectionIndicator: false, requestRenderMode: true, maximumRenderTimeChange: Infinity,
        skyAtmosphere: mars ? false : undefined, scene3DOnly: true,
      });
      viewerRef.current = viewer;
      viewer.useBrowserRecommendedResolution = false;
      viewer.resolutionScale = Math.min(window.devicePixelRatio || 1, 1.5) / (window.devicePixelRatio || 1);
      viewer.scene.backgroundColor = Color.fromCssColorString('#080e12');
      viewer.scene.globe.baseColor = Color.fromCssColorString(mars ? '#754b37' : '#233f4c');
      viewer.scene.globe.maximumScreenSpaceError = 2;
      viewer.scene.globe.tileCacheSize = 100;
      viewer.scene.screenSpaceCameraController.minimumZoomDistance = 50;
      viewer.scene.screenSpaceCameraController.maximumZoomDistance = ellipsoid.maximumRadius * 5;
      viewer.scene.globe.enableLighting = false;
      viewer.entities.add({ position: Cartesian3.fromDegrees(site.longitude,site.latitude,0,ellipsoid),
        point: { pixelSize: 9, color: Color.fromCssColorString('#d3f0aa'), outlineColor: Color.BLACK, outlineWidth: 2,
          heightReference: HeightReference.CLAMP_TO_GROUND, disableDepthTestDistance: Number.POSITIVE_INFINITY } });
      viewer.camera.setView({ destination: Cartesian3.fromDegrees(site.longitude,site.latitude,ellipsoid.maximumRadius*1.8,ellipsoid) });
      let last = 0;
      removeChanged = viewer.scene.postRender.addEventListener(() => {
        if (performance.now()-last < 250 || !viewer || viewer.isDestroyed()) return;
        last=performance.now(); const h=viewer.camera.positionCartographic.height;
        setAltitude(h>10000 ? `${(h/1000).toLocaleString('es',{maximumFractionDigits:0})} km` : `${h.toLocaleString('es',{maximumFractionDigits:0})} m`);
      });
      removeRenderError = viewer.scene.renderError.addEventListener(() => {
        if (!disposed) setError('El dispositivo no pudo renderizar la escena. Reintenta el visor o revisa la aceleración WebGL.');
      });
      SingleTileImageryProvider.fromUrl(mars ? `${import.meta.env.BASE_URL}textures/mars.png` : asset('blue-marble.png'), { ellipsoid,
        credit: mars ? 'NASA / Mars Trek · MOLA, color de elevación' : 'NASA Earth Observatory / GIBS · Blue Marble (2004)' })
        .then(provider => { if (!disposed && viewer && !viewer.isDestroyed()) { viewer.imageryLayers.add(new ImageryLayer(provider)); viewer.scene.requestRender(); } })
        .catch(() => { if (!disposed) setError('La textura global no está disponible. Se conserva el relieve con un fondo uniforme.'); });
      pixels(asset(site.heightmap),controller.signal,site.width,site.height)
        .then(data => { if (!disposed) setHeights(decodeGray(data,site)); })
        .catch(() => { if (!disposed) setMeshError('No se pudo leer el DEM local. Reintenta para cargar su malla.'); });
      setReady(true);
    } catch { setError('No se pudo iniciar WebGL. Activa la aceleración gráfica y reintenta el visor.'); }
    return () => {
      disposed=true; controller.abort(); removeChanged?.(); removeRenderError?.();
      viewerRef.current=null; meshRef.current=null; tilesRef.current=null;
      if (viewer && !viewer.isDestroyed()) viewer.destroy();
    };
  }, [site, mars, manifest, attempt]);

  // Native terrain providers: local streamed MOLA tiles, Esri elevation tiles, or quantized-mesh.
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!ready || !viewer) return;
    let disposed = false;
    let removeError: (() => void) | undefined;
    const controller = new AbortController();
    setTerrainStatus('Cargando relieve…');
    const install = (provider: typeof viewer.terrainProvider, label: string) => {
      if (disposed || viewer.isDestroyed()) return;
      viewer.terrainProvider = provider;
      removeError = provider.errorEvent.addEventListener(() => {
        if (!disposed) setTerrainStatus('Faltan teselas de relieve · revisa la conexión');
      });
      setTerrainStatus(label); viewer.scene.requestRender();
    };
    if (mars) {
      const tilingScheme = new GeographicTilingScheme({ ellipsoid: viewer.scene.globe.ellipsoid });
      const { tile_size: size, max_level: max } = manifest.mola;
      const provider = new CustomHeightmapTerrainProvider({ width:size,height:size,tilingScheme,credit:'NASA MGS / MOLA MEGDR · 4 píxeles/grado',
        callback: (x,y,level) => level>max ? undefined : pixels(asset(`mola/${level}/${x}/${y}.png`),controller.signal,size,size).then(decodeMola),
      });
      // Prevent refinement beyond the published DEM pyramid (no invented detail or retry loops).
      const geometricError = provider.getLevelMaximumGeometricError.bind(provider);
      provider.getLevelMaximumGeometricError = level => level >= max ? 0 : geometricError(level);
      install(provider,'MOLA · teselas bajo demanda');
    } else {
      const task = remoteTerrainURL
        ? CesiumTerrainProvider.fromUrl(remoteTerrainURL, { requestVertexNormals:true })
        : ArcGISTiledElevationTerrainProvider.fromUrl(earthTerrain);
      task.then(provider => install(provider,remoteTerrainURL ? 'Terreno externo · streaming' : 'Esri World Elevation · streaming'))
        .catch(() => { if (!disposed && !viewer.isDestroyed()) {
          viewer.terrainProvider=new EllipsoidTerrainProvider();
          setTerrainStatus('Relieve global no disponible · globo sin elevación');
        } });
    }
    return () => { disposed=true; removeError?.(); controller.abort(); };
  }, [ready, mars, manifest, remoteTerrainURL, attempt]);

  useEffect(() => {
    const viewer=viewerRef.current;
    if (!ready || !viewer || !heights) return;
    const a=meshArrays(heights,site,exaggeration);
    if (!a.indices.length) { setMeshError('No hay caras con soporte válido en este DEM.'); return; }
    const geometry=GeometryPipeline.computeNormal(new Geometry({ attributes: Object.assign(new GeometryAttributes(), {
      position: new GeometryAttribute({componentDatatype:ComponentDatatype.DOUBLE,componentsPerAttribute:3,values:a.positions}),
      st: new GeometryAttribute({componentDatatype:ComponentDatatype.FLOAT,componentsPerAttribute:2,values:a.uv}),
    }),indices:a.indices,primitiveType:PrimitiveType.TRIANGLES,boundingSphere:BoundingSphere.fromVertices(a.positions) }));
    const origin=Cartesian3.fromDegrees(site.longitude,site.latitude,0,viewer.scene.globe.ellipsoid);
    const modelMatrix=Transforms.eastNorthUpToFixedFrame(origin,viewer.scene.globe.ellipsoid);
    const mesh = viewer.scene.primitives.add(new Primitive({ geometryInstances:new GeometryInstance({geometry,modelMatrix}),
      appearance:new MaterialAppearance({material:Material.fromType('Image',{image:asset(texture==='height' ? site.heightmap : site.texture)}),
        translucent:false,faceForward:true,closed:false}),asynchronous:false,show:false }));
    meshRef.current=mesh;
    mesh.show=modeRef.current==='mesh'; viewer.scene.requestRender();
    return () => { if (!viewer.isDestroyed()) viewer.scene.primitives.remove(mesh); if (meshRef.current===mesh) meshRef.current=null; };
  }, [ready, heights, site, exaggeration, texture]);

  useEffect(() => {
    const viewer=viewerRef.current;
    if (!ready || !viewer) return;
    const local=mode==='mesh'; viewer.scene.globe.show=!local;
    viewer.entities.show=!local;
    if (viewer.scene.skyAtmosphere) viewer.scene.skyAtmosphere.show=!local && !mars;
    if (viewer.scene.skyBox) viewer.scene.skyBox.show=!local;
    if (meshRef.current) meshRef.current.show=local;
    if (tilesRef.current) tilesRef.current.show=!local;
    viewer.scene.screenSpaceCameraController.enableCollisionDetection=!local;
    viewer.scene.verticalExaggeration=exaggeration;
    viewer.camera.cancelFlight(); viewer.camera.lookAtTransform(Matrix4.IDENTITY);
    const ellipsoid=viewer.scene.globe.ellipsoid;
    const center=Cartesian3.fromDegrees(site.longitude,site.latitude,0,ellipsoid);
    if (local) viewer.camera.lookAtTransform(Transforms.eastNorthUpToFixedFrame(center,ellipsoid),new HeadingPitchRange(CesiumMath.toRadians(18),CesiumMath.toRadians(-38),3100));
    else if (mode==='space') viewer.camera.flyTo({destination:Cartesian3.fromDegrees(site.longitude,site.latitude,ellipsoid.maximumRadius*1.8,ellipsoid),duration:duration()});
    else viewer.camera.flyToBoundingSphere(new BoundingSphere(center,22000),{offset:new HeadingPitchRange(0,CesiumMath.toRadians(-45),mars?95000:60000),duration:duration()});
    viewer.scene.requestRender();
  }, [ready, mode, site, mars, attempt, frame]);

  useEffect(() => { const v=viewerRef.current; if (ready && v) { v.scene.verticalExaggeration=exaggeration; v.scene.requestRender(); } },[ready,exaggeration]);

  useEffect(() => {
    const viewer=viewerRef.current;
    if (!ready || !viewer || mars || remote?.kind!=='tiles') { setRemoteStatus(''); return; }
    let disposed=false; let tiles: Cesium3DTileset | undefined; let removeError: (()=>void) | undefined;
    setRemoteStatus('Cargando 3D Tiles…');
    Cesium3DTileset.fromUrl(remote.url,{maximumScreenSpaceError:8,cacheBytes:128*1024*1024})
      .then(result=>{
        if (disposed || viewer.isDestroyed()) { result.destroy(); return; }
        tiles=result; tilesRef.current=result; viewer.scene.primitives.add(result); result.show=modeRef.current!=='mesh';
        removeError=result.tileFailed.addEventListener(()=>{if(!disposed)setRemoteStatus('Algunas teselas 3D no se pudieron descargar.');});
        setRemoteStatus('3D Tiles conectado');
        if(modeRef.current!=='mesh') void viewer.flyTo(result,{duration:duration()});
        viewer.scene.requestRender();
      }).catch(()=>{if(!disposed)setRemoteStatus('No se pudo abrir 3D Tiles. Comprueba la URL y el acceso CORS.');});
    return ()=>{disposed=true;removeError?.();if(tiles && !viewer.isDestroyed())viewer.scene.primitives.remove(tiles);if(tilesRef.current===tiles)tilesRef.current=null;};
  }, [ready, remote, mars]);

  return <div className="surface-scene">
    <div className="surface-canvas" ref={container} role="region" aria-label={`Visor 3D de ${site.name}`} />
    <div className="surface-hud"><span className="surface-live-dot"/><span>{mode==='mesh' ? `${site.source} · malla local` : terrainStatus}</span></div>
    <div className="surface-altitude"><small>{mode==='mesh'?'MUESTRAS DEL DEM':'ALTURA SOBRE EL ELIPSOIDE'}</small><strong>{mode==='mesh'?`${site.width} × ${site.height}`:altitude || '—'}</strong></div>
    <div className="surface-navigation" role="group" aria-label="Navegación 3D"><button aria-label="Restablecer encuadre" title="Restablecer encuadre" onClick={()=>setFrame(n=>n+1)}>⌖</button><button aria-label="Acercar" onClick={()=>{const v=viewerRef.current;if(v){v.camera.zoomIn(Math.max(100,(mode==='mesh'?Cartesian3.magnitude(v.camera.position):Math.abs(v.camera.positionCartographic.height))*.2));v.scene.requestRender();}}}>+</button><button aria-label="Alejar" onClick={()=>{const v=viewerRef.current;if(v){v.camera.zoomOut(Math.max(100,(mode==='mesh'?Cartesian3.magnitude(v.camera.position):Math.abs(v.camera.positionCartographic.height))*.2));v.scene.requestRender();}}}>−</button></div>
    <p className="surface-gesture">Arrastrar: mover · rueda: acercar · Ctrl + arrastrar: inclinar</p>
    <div className="surface-notices" aria-live="polite">{mode==='mesh' && !heights && !meshError && <p role="status">Leyendo mapa de alturas…</p>}{remoteStatus && <p>{remoteStatus}</p>}{(error || (mode==='mesh' && meshError)) && <div role="alert"><p>{error || meshError}</p><button onClick={()=>setAttempt(n=>n+1)}>Reintentar visor</button></div>}</div>
  </div>;
}
