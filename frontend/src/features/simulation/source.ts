import {adaptSearch,type LoadedSearch,type ReferenceId} from './model';
const demoFiles:Partial<Record<ReferenceId,string>>={'jezero':'jezero.json','haworth-fondo':'haworth-fondo.json'};

export async function loadSearch(reference:ReferenceId,version:string,source:'auto'|'demo',base:string,signal:AbortSignal):Promise<LoadedSearch> {
  let notice='Demostración seleccionada: resultados precalculados del repositorio.';
  if(source==='auto') {
    try {
      const query=version?`?version=${encodeURIComponent(version)}`:'';
      const response=await fetch(`/api/atlas/similarity/${encodeURIComponent(reference)}${query}`,{signal});
      if(response.ok) {
        const data=adaptSearch(await response.json());
        if(data.reference.id!==reference)throw new Error('La respuesta pertenece a otra referencia.');
        if(version&&data.version!==version)throw new Error('La respuesta no confirma la publicación solicitada.');
        return {data,source:'published',notice:'Resultados publicados por la API del atlas.',version:data.version||version||undefined};
      }
      if(![404,503].includes(response.status))throw new Error(`El servicio respondió con estado ${response.status}.`);
      notice=response.status===404?'El servicio no ofrece resultados para esta referencia. Se muestra la demostración del repositorio.':'El servicio de similitud no está disponible. Se muestra la demostración del repositorio.';
    } catch(error) {
      if(signal.aborted)throw error;
      // Invalid scientific responses must remain errors instead of silently substituting demo data.
      if(error instanceof Error && !(error instanceof TypeError))throw error;
      notice='No hay conexión con el servicio de similitud. Se muestra la demostración del repositorio.';
    }
  }
  const file=demoFiles[reference];
  if(!file)throw new Error('Esta referencia todavía no tiene un ranking publicado ni un ejemplo de demostración. Elige Jezero o Haworth.');
  const response=await fetch(`${base}simulation/${file}`,{signal});
  if(!response.ok)throw new Error('No se pudo cargar la demostración. Reintenta la consulta.');
  const data=adaptSearch(await response.json());
  if(data.reference.id!==reference)throw new Error('El ejemplo no coincide con la referencia seleccionada.');
  return {data,source:'demo',notice:`${notice} No está vinculado a la release del atlas; no recalcula el ranking.`};
}
