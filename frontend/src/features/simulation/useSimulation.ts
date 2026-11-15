import {useEffect,useState} from 'react';
import type {AtlasState} from '../../app/useAtlasState';
import {loadSearch} from './source';
import type {LoadedSearch} from './model';
export function useSimulation(state:AtlasState) {
  const key=`${state.reference}/${state.release}/${state.engineSource}`;
  const enabled=state.method==='engine' && ['simulation','compare','sensitivity','surface'].includes(state.view);
  const [attempt,setAttempt]=useState(0);
  const [result,setResult]=useState<{key:string;attempt:number;value?:LoadedSearch;error?:string}>();
  useEffect(()=>{
    if(!enabled)return;
    const controller=new AbortController();
    loadSearch(state.reference,state.release,state.engineSource,`${import.meta.env.BASE_URL}analysis/`,controller.signal)
      .then(value=>{if(!controller.signal.aborted)setResult({key,attempt,value});})
      .catch(e=>{if(!controller.signal.aborted)setResult({key,attempt,error:e.message});});
    return ()=>controller.abort();
  },[key,attempt,enabled]);
  const current=result?.key===key&&result.attempt===attempt?result:undefined;
  return {loaded:current?.value,error:current?.error,loading:enabled&&!current,retry:()=>setAttempt(n=>n+1)};
}
export type SimulationResource=ReturnType<typeof useSimulation>;
