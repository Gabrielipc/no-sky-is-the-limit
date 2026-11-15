import {tr} from '../../i18n/lang';
import { Cartesian2, Cartesian3, Color, CustomDataSource, LabelStyle, Matrix4 } from 'cesium';
import type { SurfaceSite } from './terrain';

/** Georeferenced rulers and a measured cross-section, in the mesh's ENU frame. */
export function localGuides(site:SurfaceSite, heights:Float32Array, exaggeration:number, matrix:Matrix4) {
  const data=new CustomDataSource('Referencias de la malla');
  const point=(x:number,y:number,z:number)=>Matrix4.multiplyByPoint(matrix,new Cartesian3(x,y,z),new Cartesian3());
  const label=(x:number,y:number,z:number,text:string,color=Color.WHITE)=>data.entities.add({position:point(x,y,z),label:{text,font:'13px sans-serif',fillColor:color,outlineColor:Color.fromCssColorString('#1C1511'),outlineWidth:4,style:LabelStyle.FILL_AND_OUTLINE,disableDepthTestDistance:Infinity,pixelOffset:new Cartesian2(0,-12)}});
  const line=(coords:number[][],color=Color.fromCssColorString('#85705A'),width=1.5)=>data.entities.add({polyline:{positions:coords.map(p=>point(p[0],p[1],p[2])),width,material:color,arcType:0}});
  const half=site.window_m/2, bottom=(site.min_m-site.center_m)*exaggeration-35;
  line([[-half,-half,bottom],[half,-half,bottom],[half,half,bottom],[-half,half,bottom],[-half,-half,bottom]]);
  label(0,-half-100,bottom,`${site.window_m.toLocaleString('es')} m · este ↔ oeste`);
  label(-half-190,0,bottom,`${site.window_m.toLocaleString('es')} m`);
  line([[-half-150,half-350,bottom],[-half-150,half+80,bottom]],Color.fromCssColorString('#F6EDE0'),3);
  label(-half-150,half+130,bottom,'N ↑',Color.fromCssColorString('#F6EDE0'));
  // Keep missing samples as gaps in the cross section.
  const row=Math.floor(site.height/2), gold=Color.fromCssColorString('#F2A64E');let segment:number[][]=[];
  for(let x=0;x<site.width;x++){
    const h=heights[row*site.width+x];
    if(!Number.isFinite(h)){if(segment.length>1)line(segment,gold,3);segment=[];continue;}
    segment.push([-half+x*site.cell_m,0,(h-site.center_m)*exaggeration+3]);
  }
  if(segment.length>1)line(segment,gold,3);
  for(const [x,name] of [[0,'A'],[site.width-1,'B']] as const){const h=heights[row*site.width+x];if(Number.isFinite(h))label(-half+x*site.cell_m,0,(h-site.center_m)*exaggeration+20,name,gold);}
  let low=-1,high=-1;
  heights.forEach((h,i)=>{if(Number.isFinite(h)){if(low<0||h<heights[low])low=i;if(high<0||h>heights[high])high=i;}});
  for(const [i,name] of [[low,tr('Mín.','Min.')],[high,tr('Máx.','Max.')]] as const){
    if(i<0)continue;
    const x=(i%site.width)*site.cell_m-half,y=half-Math.floor(i/site.width)*site.cell_m,z=(heights[i]-site.center_m)*exaggeration;
    data.entities.add({position:point(x,y,z+3),point:{pixelSize:7,color:Color.WHITE,outlineColor:Color.BLACK,outlineWidth:2,disableDepthTestDistance:Infinity}});
    label(x,y,z+10,`${name} ${heights[i].toFixed(0)} m`);
  }
  return data;
}
