import {defineConfig,type Plugin} from 'vite';
import react from '@vitejs/plugin-react';
import cesium from 'vite-plugin-cesium';
import {cpSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
// The existing API already serves /analysis. Keep new static evidence under that
// namespace in production without requiring new backend mounts.
function browserEvidence():Plugin {
  let root='';let out='';let building=false;
  return {name:'browser-evidence',configResolved(config){building=config.command==='build';root=config.root;out=resolve(root,config.build.outDir);},
    configureServer(server){server.middlewares.use((req,_res,next)=>{for(const folder of ['surface','simulation','brand'])if(req.url?.startsWith(`/analysis/${folder}/`))req.url=req.url.replace(`/analysis/${folder}/`,`/${folder}/`);next();});},
    closeBundle(){if(!building)return;mkdirSync(resolve(out,'analysis'),{recursive:true});for(const folder of ['surface','simulation','brand'])cpSync(resolve(root,'public',folder),resolve(out,'analysis',folder),{recursive:true});},
  };
}
const cesiumAssets=cesium();
export default defineConfig({
  plugins:[react(),{...cesiumAssets,transformIndexHtml:()=>[]},browserEvidence()],
  server:{proxy:{'/api':'http://127.0.0.1:8000'}},
  preview:{proxy:{'/api':'http://127.0.0.1:8000'}},
});
