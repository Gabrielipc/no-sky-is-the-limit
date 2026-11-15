import {useEffect,useRef,useState} from 'react';
import {ArcGisMapServerImageryProvider,BoundingSphere,Cartesian2,Cartesian3,Color,Entity,HeadingPitchRange,ImageryLayer,Math as CMath,ScreenSpaceEventHandler,ScreenSpaceEventType,SingleTileImageryProvider,Viewer} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import type {Match} from './model';

export default function ResultGlobe({rows,selected,choose,regional=false}:{rows:Match[];selected:string;choose:(id:string)=>void;regional?:boolean}) {
  const root=useRef<HTMLDivElement>(null),viewer=useRef<Viewer|null>(null),chooseRef=useRef(choose);chooseRef.current=choose;
  const [ready,setReady]=useState(false),[error,setError]=useState('');
  useEffect(()=>{
    if(!root.current)return;let v:Viewer|undefined,handler:ScreenSpaceEventHandler|undefined,disposed=false;
    try {
      v=new Viewer(root.current,{baseLayer:false,baseLayerPicker:false,geocoder:false,homeButton:false,sceneModePicker:false,navigationHelpButton:false,animation:false,timeline:false,fullscreenButton:false,infoBox:false,selectionIndicator:false,requestRenderMode:true,maximumRenderTimeChange:Infinity,scene3DOnly:true});
      viewer.current=v;v.scene.backgroundColor=Color.fromCssColorString('#091517');v.resolutionScale=1;v.scene.globe.baseColor=Color.fromCssColorString('#24434c');
      v.scene.screenSpaceCameraController.minimumZoomDistance=500;
      SingleTileImageryProvider.fromUrl(`${import.meta.env.BASE_URL}surface/blue-marble.png`,{credit:'NASA Blue Marble / GIBS'}).then(p=>{if(!disposed&&v&&!v.isDestroyed()){v.imageryLayers.add(new ImageryLayer(p),0);v.scene.requestRender();}}).catch(()=>{if(!disposed)setError('Textura de contexto no disponible. Las coordenadas de las candidatas siguen visibles.');});
      if(regional)ArcGisMapServerImageryProvider.fromUrl('https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer').then(p=>{if(!disposed&&v&&!v.isDestroyed()){v.imageryLayers.add(new ImageryLayer(p));v.scene.requestRender();}}).catch(()=>{if(!disposed)setError('Imagen regional no disponible. Se muestra Blue Marble como contexto.');});
      handler=new ScreenSpaceEventHandler(v.scene.canvas);
      handler.setInputAction((event:{position:Cartesian2})=>{const hit=v?.scene.pick(event.position);if(hit?.id instanceof Entity&&hit.id.id.startsWith('match:'))chooseRef.current(hit.id.id.slice(6));},ScreenSpaceEventType.LEFT_CLICK);
      v.camera.setView({destination:Cartesian3.fromDegrees(0,10,24000000)});setReady(true);
    }catch{setError('No se pudo iniciar WebGL. Utiliza la lista de candidatas.');}
    return()=>{disposed=true;handler?.destroy();viewer.current=null;if(v&&!v.isDestroyed())v.destroy();};
  },[regional]);
  useEffect(()=>{
    const v=viewer.current;if(!ready||!v)return;v.entities.removeAll();
    for(const row of rows){const active=row.region_id===selected;
      v.entities.add({id:`match:${row.region_id}`,position:Cartesian3.fromDegrees(row.longitude,row.latitude),point:{pixelSize:active?14:9,color:Color.fromCssColorString(active?'#f0cb75':'#c5e59e'),outlineColor:Color.BLACK,outlineWidth:2,disableDepthTestDistance:Infinity},label:{text:String(row.rank),font:'12px sans-serif',pixelOffset:new Cartesian2(0,-20),showBackground:true,backgroundColor:Color.fromCssColorString('#0d1b1ae6'),disableDepthTestDistance:Infinity}});
    }
    const row=rows.find(r=>r.region_id===selected);const motion=window.matchMedia('(prefers-reduced-motion: reduce)').matches?0:1.2;
    if(row&&regional)v.camera.flyToBoundingSphere(new BoundingSphere(Cartesian3.fromDegrees(row.longitude,row.latitude),2500),{duration:motion,offset:new HeadingPitchRange(0,CMath.toRadians(-65),24000)});
    else if(row)v.camera.flyTo({destination:Cartesian3.fromDegrees(row.longitude,row.latitude,16000000),duration:motion});
    v.scene.requestRender();
  },[ready,rows,selected,regional]);
  return <><div className="simulation-globe" ref={root} role="region" aria-label="Mapa 3D de candidatas terrestres"/><div className="simulation-map-caption">{regional?'Contexto satelital · sin DEM local de esta ventana':'Tierra · NASA Blue Marble'}<small>Selecciona un punto o usa la lista de resultados.</small></div>{error&&<p className="simulation-map-error" role="alert">{error}</p>}</>;
}
