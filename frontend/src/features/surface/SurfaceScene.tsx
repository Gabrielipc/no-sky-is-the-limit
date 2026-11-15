import { useEffect, useRef, useState } from 'react';
import {
  ArcGisMapServerImageryProvider, ArcGISTiledElevationTerrainProvider, BoundingSphere, Cartesian2, Cartesian3, Cartographic, CustomDataSource, EllipsoidGeodesic, Cesium3DTileset, CesiumTerrainProvider,
  Color, ComponentDatatype, CustomHeightmapTerrainProvider, Ellipsoid, EllipsoidTerrainProvider,
  GeographicProjection, GeographicTilingScheme, Geometry, GeometryAttribute, GeometryAttributes, GeometryInstance, GeometryPipeline,
  Globe, HeadingPitchRange, HeightReference, ImageryLayer, Material, MaterialAppearance, Math as CesiumMath,
  Matrix4, Primitive, PrimitiveType, Rectangle, SingleTileImageryProvider, Transforms, Viewer,
} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import { asset, pixels } from './assets';
import { localGuides } from './guides';
import { decodeGray, decodeMola, elevationColor, metricScale, meshArrays, type SurfaceManifest, type SurfaceMode, type SurfaceSite, type RemoteLayer } from './terrain';

const earthTerrain = 'https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer';
const duration = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 2.4;

type Props = { site: SurfaceSite; manifest: SurfaceManifest; mode: SurfaceMode; exaggeration: number; texture: 'elevation' | 'relief' | 'height'; remote: RemoteLayer };
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
  const [scale, setScale] = useState<ReturnType<typeof metricScale>>(null);
  const [imageryStatus,setImageryStatus] = useState('');
  const [attempt, setAttempt] = useState(0);
  const meshRef = useRef<Primitive | null>(null);
  const tilesRef = useRef<Cesium3DTileset | null>(null);
  const guidesRef = useRef<CustomDataSource | null>(null);
  const detailRef = useRef<ImageryLayer | null>(null);
  const modeRef = useRef(mode); modeRef.current = mode;
  const [topView,setTopView]=useState(false);
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
    setError(''); setMeshError(''); setHeights(null); setReady(false); setScale(null);
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
        if(modeRef.current==='regional') {
          const canvas=viewer.scene.canvas, cx=canvas.clientWidth/2, cy=canvas.clientHeight*.65;
          const a=viewer.camera.getPickRay(new Cartesian2(cx-60,cy)), b=viewer.camera.getPickRay(new Cartesian2(cx+60,cy));
          const p=a&&viewer.scene.globe.pick(a,viewer.scene) || viewer.camera.pickEllipsoid(new Cartesian2(cx-60,cy),viewer.scene.globe.ellipsoid), q=b&&viewer.scene.globe.pick(b,viewer.scene) || viewer.camera.pickEllipsoid(new Cartesian2(cx+60,cy),viewer.scene.globe.ellipsoid);
          if(p&&q){const e=viewer.scene.globe.ellipsoid; const distance=new EllipsoidGeodesic(Cartographic.fromCartesian(p,e),Cartographic.fromCartesian(q,e),e).surfaceDistance;setScale(metricScale(distance/120));}
          else setScale(null);
        }
        setAltitude(h>10000 ? `${(h/1000).toLocaleString('es',{maximumFractionDigits:0})} km` : `${h.toLocaleString('es',{maximumFractionDigits:0})} m`);
      });
      removeRenderError = viewer.scene.renderError.addEventListener(() => {
        if (!disposed) setError('El dispositivo no pudo renderizar la escena. Reintenta el visor o revisa la aceleración WebGL.');
      });
      SingleTileImageryProvider.fromUrl(mars ? `${import.meta.env.BASE_URL}surface/mars-globe.png` : asset('blue-marble.png'), { ellipsoid,
        credit: mars ? 'NASA MOLA · relieve en tonos naturales' : 'NASA Earth Observatory / GIBS · Blue Marble (2004)' })
        .then(provider => { if (!disposed && viewer && !viewer.isDestroyed()) { viewer.imageryLayers.add(new ImageryLayer(provider),0); viewer.scene.requestRender(); } })
        .catch(() => { if (!disposed) setError('La textura global no está disponible. Se conserva el relieve con un fondo uniforme.'); });
      pixels(asset(site.heightmap),controller.signal,site.width,site.height)
        .then(data => { if (!disposed) setHeights(decodeGray(data,site)); })
        .catch(() => { if (!disposed) setMeshError('No se pudo leer el DEM local. Reintenta para cargar su malla.'); });
      setReady(true);
    } catch { setError('No se pudo iniciar WebGL. Activa la aceleración gráfica y reintenta el visor.'); }
    return () => {
      disposed=true; controller.abort(); removeChanged?.(); removeRenderError?.();
      viewerRef.current=null; meshRef.current=null; tilesRef.current=null; guidesRef.current=null; detailRef.current=null;
      if (viewer && !viewer.isDestroyed()) viewer.destroy();
    };
  }, [site, mars, manifest, attempt]);

  useEffect(()=>{
    const viewer=viewerRef.current;if(!ready||!viewer)return;
    let disposed=false, layer:ImageryLayer|undefined;let removeError:(()=>void)|undefined;
    setImageryStatus('Cargando imagen regional…');
    const task=mars ? fetch(asset('regional-preview.json')).then(response=>{if(!response.ok)throw new Error('CTX metadata');return response.json();}).then(metadata=>SingleTileImageryProvider.fromUrl(asset(metadata.file),{
      rectangle:Rectangle.fromDegrees(...metadata.rectangle_degrees as [number,number,number,number]),ellipsoid:viewer.scene.globe.ellipsoid,
      credit:metadata.credit,
    })) : ArcGisMapServerImageryProvider.fromUrl('https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer');
    task.then(provider=>{
      if(disposed||viewer.isDestroyed())return;
      layer=new ImageryLayer(provider,{show:modeRef.current==='regional'});viewer.imageryLayers.add(layer);detailRef.current=layer;
      setImageryStatus(mars?'CTX · recorte regional ~81 m/píxel':'Esri · imagen satelital');
      removeError=provider.errorEvent.addEventListener(()=>{if(!disposed)setImageryStatus('Imagen regional incompleta · revisa la conexión');});
      viewer.scene.requestRender();
    }).catch(()=>{if(!disposed)setImageryStatus('Imagen regional no disponible · se muestra contexto global');});
    const e=viewer.scene.globe.ellipsoid, center=Cartesian3.fromDegrees(site.longitude,site.latitude,0,e);
    const transform=Transforms.eastNorthUpToFixedFrame(center,e), half=site.window_m/2;
    const corners=[[-half,-half],[half,-half],[half,half],[-half,half],[-half,-half]].map(([x,y])=>{
      const c=Cartographic.fromCartesian(Matrix4.multiplyByPoint(transform,new Cartesian3(x,y,0),new Cartesian3()),e);
      return Cartesian3.fromRadians(c.longitude,c.latitude,0,e);
    });
    const footprint=viewer.entities.add({polyline:{positions:corners,width:3,clampToGround:true,material:Color.fromCssColorString('#e5f9a4')}});
    const caption=viewer.entities.add({position:center,label:{text:'Ventana local · 1,8 × 1,8 km',font:'13px sans-serif',heightReference:HeightReference.CLAMP_TO_GROUND,pixelOffset:new Cartesian2(0,-25),fillColor:Color.WHITE,showBackground:true,backgroundColor:Color.fromCssColorString('#10201be6'),disableDepthTestDistance:Infinity}});
    return()=>{disposed=true;removeError?.();if(!viewer.isDestroyed()){if(layer)viewer.imageryLayers.remove(layer);viewer.entities.remove(footprint);viewer.entities.remove(caption);}if(detailRef.current===layer)detailRef.current=null;};
  },[ready,site,mars,attempt]);

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
      const { tile_size: size, max_level: baseMax, regional } = manifest.mola;
      const max=regional?.max_level ?? baseMax, available=new Set(regional?.tiles || []);
      const provider = new CustomHeightmapTerrainProvider({ width:size,height:size,tilingScheme,credit:'NASA MGS / MOLA MEGDR · 4 píxeles/grado',
        callback: (x,y,level) => level>max ? undefined : pixels(asset(`mola/${level}/${x}/${y}.png`),controller.signal,size,size).then(decodeMola),
      });
      provider.getTileDataAvailable=(x,y,level)=>level<=baseMax || available.has(`${level}/${x}/${y}`);
      // Stop at the published regional grid; outside it Cesium upsamples coarse parents.
      const geometricError = provider.getLevelMaximumGeometricError.bind(provider);
      provider.getLevelMaximumGeometricError = level => level >= max ? 0 : geometricError(level);
      install(provider,regional?'MOLA · global + Jezero 128 ppd':'MOLA · teselas bajo demanda');
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
    let image: string | HTMLCanvasElement=asset(texture==='height' ? site.heightmap : site.texture);
    if(texture==='elevation') {
      const canvas=document.createElement('canvas');canvas.width=site.width;canvas.height=site.height;
      const ctx=canvas.getContext('2d')!;const rgba=ctx.createImageData(site.width,site.height);
      heights.forEach((h,i)=>{if(Number.isFinite(h))rgba.data.set([...elevationColor(h,site.min_m,site.max_m),255],i*4);});
      ctx.putImageData(rgba,0,0);image=canvas;
    }
    const guides=localGuides(site,heights,exaggeration,modelMatrix);guides.show=modeRef.current==='mesh';
    guidesRef.current=guides;void viewer.dataSources.add(guides);
    const mesh = viewer.scene.primitives.add(new Primitive({ geometryInstances:new GeometryInstance({geometry,modelMatrix}),
      appearance:new MaterialAppearance({material:Material.fromType('Image',{image}),
        translucent:false,faceForward:true,closed:false}),asynchronous:false,show:false }));
    meshRef.current=mesh;
    mesh.show=modeRef.current==='mesh'; viewer.scene.requestRender();
    return () => { if (!viewer.isDestroyed()) {viewer.scene.primitives.remove(mesh);viewer.dataSources.remove(guides,true);}if(guidesRef.current===guides)guidesRef.current=null; if (meshRef.current===mesh) meshRef.current=null; };
  }, [ready, heights, site, exaggeration, texture]);

  useEffect(() => {
    const viewer=viewerRef.current;
    if (!ready || !viewer) return;
    const local=mode==='mesh'; viewer.scene.globe.show=!local;
    viewer.entities.show=mode==='regional';
    if(guidesRef.current)guidesRef.current.show=local;
    if(detailRef.current)detailRef.current.show=mode==='regional';
    if (viewer.scene.skyAtmosphere) viewer.scene.skyAtmosphere.show=!local && !mars;
    if (viewer.scene.skyBox) viewer.scene.skyBox.show=!local;
    if (meshRef.current) meshRef.current.show=local;
    if (tilesRef.current) tilesRef.current.show=!local;
    viewer.scene.screenSpaceCameraController.enableCollisionDetection=!local;
    viewer.scene.verticalExaggeration=exaggeration;
    viewer.camera.cancelFlight(); viewer.camera.lookAtTransform(Matrix4.IDENTITY);
    const ellipsoid=viewer.scene.globe.ellipsoid;
    const center=Cartesian3.fromDegrees(site.longitude,site.latitude,0,ellipsoid);
    if (local) viewer.camera.lookAtTransform(Transforms.eastNorthUpToFixedFrame(center,ellipsoid),new HeadingPitchRange(CesiumMath.toRadians(0),CesiumMath.toRadians(topView?-90:-48),3700));
    else if (mode==='space') viewer.camera.flyTo({destination:Cartesian3.fromDegrees(site.longitude,site.latitude,ellipsoid.maximumRadius*1.8,ellipsoid),duration:duration()});
    else viewer.camera.flyToBoundingSphere(new BoundingSphere(center,22000),{offset:new HeadingPitchRange(0,CesiumMath.toRadians(-45),mars?65000:16000),duration:duration()});
    viewer.scene.requestRender();
  }, [ready, mode, site, mars, attempt, frame, topView]);

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
    <div className="surface-hud"><span className="surface-live-dot"/><span>{mode==='mesh' ? `${site.source} · malla local` : mode==='regional' ? imageryStatus : terrainStatus}</span></div>
    <div className="surface-altitude"><small>{mode==='mesh'?'VENTANA DEL TERRENO':'ALTURA DE LA CÁMARA'}</small><strong>{mode==='mesh'?'1,8 × 1,8 km':altitude || '—'}</strong></div>
    <div className="surface-navigation" role="group" aria-label="Navegación 3D">{mode==='mesh'&&<button aria-label={topView?'Vista oblicua del terreno':'Vista cenital, norte arriba'} title={topView?'Vista oblicua':'Vista cenital · norte arriba'} onClick={()=>setTopView(v=>!v)}>N</button>}<button aria-label="Restablecer encuadre" title="Restablecer encuadre" onClick={()=>setFrame(n=>n+1)}>⌖</button><button aria-label="Acercar" onClick={()=>{const v=viewerRef.current;if(v){v.camera.zoomIn(Math.max(100,(mode==='mesh'?Cartesian3.magnitude(v.camera.position):Math.abs(v.camera.positionCartographic.height))*.2));v.scene.requestRender();}}}>+</button><button aria-label="Alejar" onClick={()=>{const v=viewerRef.current;if(v){v.camera.zoomOut(Math.max(100,(mode==='mesh'?Cartesian3.magnitude(v.camera.position):Math.abs(v.camera.positionCartographic.height))*.2));v.scene.requestRender();}}}>−</button></div>
    {mode==='regional' && <div className="surface-map-scale">{scale && <><span style={{width:scale.pixels}}/>{scale.distance>=1000?`${(scale.distance/1000).toLocaleString('es')} km`:`${scale.distance.toLocaleString('es')} m`}<small>Distancia horizontal en el centro de la vista</small></>}</div>}
    {mode==='mesh' && <div className="surface-elevation-legend"><strong>{texture==='elevation'?'Altura del terreno':texture==='height'?'Gris → altura':'Relieve sombreado'}</strong>{texture!=='relief' && <><div className={texture==='height'?'gray-ramp':'height-ramp'}/><span>{site.min_m.toFixed(0)} m <b>{site.max_m.toFixed(0)} m</b></span></>}<p>{exaggeration===1?'Escala vertical real · 1×':`Altura exagerada ${exaggeration}× · distancias sin cambio`}</p><small>A–B: corte central · N: norte</small></div>}
    <p className="surface-gesture">Arrastrar: mover · rueda: acercar · Ctrl + arrastrar: inclinar</p>
    <div className="surface-notices" aria-live="polite">{mode==='mesh' && !heights && !meshError && <p role="status">Leyendo mapa de alturas…</p>}{remoteStatus && <p>{remoteStatus}</p>}{(error || (mode==='mesh' && meshError)) && <div role="alert"><p>{error || meshError}</p><button onClick={()=>setAttempt(n=>n+1)}>Reintentar visor</button></div>}</div>
  </div>;
}
