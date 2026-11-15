/** Copy only existing browser-ready evidence; preserve original scientific responses byte for byte. */
import {readFileSync,writeFileSync,mkdirSync,copyFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const frontend=resolve(dirname(fileURLToPath(import.meta.url)),'..'), root=resolve(frontend,'..');
const read=p=>JSON.parse(readFileSync(resolve(root,p),'utf8'));
const hash=p=>createHash('sha256').update(readFileSync(resolve(root,p))).digest('hex');
const write=(p,value)=>writeFileSync(resolve(frontend,'public',p),JSON.stringify(value,null,2)+'\n');
mkdirSync(resolve(frontend,'public/simulation'),{recursive:true});
const files=[];
for(const [file,reference] of [['busqueda-jezero.json','jezero'],['busqueda-haworth.json','haworth-fondo']]) {
  const source=`docs/evidencia-motor-similitud/${file}`;
  copyFileSync(resolve(root,source),resolve(frontend,'public/simulation',`${reference}.json`));
  files.push({reference,file:`${reference}.json`,source,sha256:hash(source)});
}
write('simulation/provenance.json',{kind:'reviewable_repository_examples',release:null,window_m:3000,cell_m:30,slope_baseline_m:240,roughness_radius_m:360,files});
const source='docs/evidencia-fase-2/procesamiento.json', processing=read(source), config=read('specs/analysis/primer-caso-fase2.json'),sites={};
for(const site of config.sites) {
  const input=processing.inputs.find(i=>i.input===site.input);
  if(!input)throw new Error(`Sin metadatos de ${site.id}`);
  sites[site.id]=Object.fromEntries(['product_id','version','vertical_reference','observation_dates','url','limitations'].map(key=>[key,site[key]]));
  sites[site.id].native_step_at_center_m=input.native_step_at_center_m;
}
write('surface/source-context.json',{source,source_sha256:hash(source),sites});
console.log('Synchronized 2 unchanged engine examples and 3 source metadata records.');
