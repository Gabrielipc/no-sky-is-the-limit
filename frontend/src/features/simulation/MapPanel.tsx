import {Component,lazy,Suspense,type ReactNode} from 'react';
import {loadCesium} from '../../data/loadCesium';
import type {Match} from './model';
const Globe=lazy(async()=>{await loadCesium();return import('./ResultGlobe');});
class MapBoundary extends Component<{children:ReactNode},{failed:boolean}> {
  state={failed:false};static getDerivedStateFromError(){return{failed:true};}
  render(){return this.state.failed?<p role="alert">El mapa 3D no está disponible. Puedes seleccionar todas las candidatas en la lista.</p>:this.props.children;}
}
export function MapPanel(props:{rows:Match[];selected:string;choose:(id:string)=>void;regional?:boolean}) {
  return <div className="simulation-map"><MapBoundary><Suspense fallback={<p role="status">Cargando mapa Cesium…</p>}><Globe {...props}/></Suspense></MapBoundary></div>;
}
