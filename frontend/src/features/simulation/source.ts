import {adaptSearch,type LoadedSearch,type ReferenceId} from './model';
import {tr} from '../../i18n/lang';
const demoFiles:Partial<Record<ReferenceId,string>>={'jezero':'jezero.json','haworth-fondo':'haworth-fondo.json'};

export async function loadSearch(reference:ReferenceId,version:string,source:'auto'|'demo',base:string,signal:AbortSignal):Promise<LoadedSearch> {
  let notice=tr('Demostración seleccionada: resultados precalculados del repositorio.','Demo selected: precomputed results from the repository.');
  if(source==='auto') {
    let response:Response|undefined;
    const query=version?`?version=${encodeURIComponent(version)}`:'';
    try {
      response=await fetch(`/api/atlas/similarity/${encodeURIComponent(reference)}${query}`,{signal});
    } catch(error) {
      if(signal.aborted)throw error;
      notice=tr('No hay conexión con el servicio de similitud. Se muestra la demostración del repositorio.','No connection to the similarity service. Showing the repository demo.');
    }
    if(response) {
      // Parse/identity failures remain errors. Only transport/unavailability allows the explicit demo.
      if(response.ok) {
        const data=adaptSearch(await response.json());
        if(data.reference.id!==reference)throw new Error(tr('La respuesta pertenece a otra referencia.','The response belongs to another reference.'));
        if(version&&data.version!==version)throw new Error(tr('La respuesta no confirma la publicación solicitada.','The response does not confirm the requested release.'));
        return {data,source:'published',notice:tr('Resultados publicados por la API del atlas.','Results published by the atlas API.'),version:data.version||version||undefined};
      }
      if(response.status!==404 && response.status<500)throw new Error(tr(`El servicio respondió con estado ${response.status}.`,`The service responded with status ${response.status}.`));
      notice=response.status===404?tr('El servicio no ofrece resultados para esta referencia. Se muestra la demostración del repositorio.','The service has no results for this reference. Showing the repository demo.'):tr('El servicio de similitud no está disponible. Se muestra la demostración del repositorio.','The similarity service is unavailable. Showing the repository demo.');
    }
  }
  const file=demoFiles[reference];
  if(!file)throw new Error(tr('Esta referencia todavía no tiene un ranking publicado ni un ejemplo de demostración. Elige Jezero o Haworth.','This reference has no published ranking or demo example yet. Choose Jezero or Haworth.'));
  const response=await fetch(`${base}simulation/${file}`,{signal});
  if(!response.ok)throw new Error(tr('No se pudo cargar la demostración. Reintenta la consulta.','The demo could not be loaded. Try the query again.'));
  const data=adaptSearch(await response.json());
  if(data.reference.id!==reference)throw new Error(tr('El ejemplo no coincide con la referencia seleccionada.','The example does not match the selected reference.'));
  return {data,source:'demo',notice:`${notice} ${tr('No está vinculado a la release del atlas; no recalcula el ranking.','It is not tied to the atlas release and does not recalculate the ranking.')}`};
}
