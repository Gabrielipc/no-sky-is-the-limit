"""Bounded scientific reads -> calibrated browser PNGs. Originals stay in ignored data/raw.
Visual grids never replace or recompute the published similarity descriptors.
Run from repository root with .venv/bin/python frontend/scripts/prepare-unified-terrain.py.
"""
import json, math, shutil, hashlib
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds, reproject, Resampling
from rasterio.transform import from_origin
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'frontend/public/surface/unified'; OUT.mkdir(parents=True,exist_ok=True)
RAW=ROOT/'data/raw/regolith'
LOLA='https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF'
manifest={'version':1,'description':'Visual derivatives only; rankings remain unchanged. Local 1.8 km is a subset of the 3 km analysis window.', 'sites':{},'missing':{},'moon':{'radius_m':1737400,'tile_size':65,'max_level':3,'native_spacing_m':7581,'source_url':'https://svs.gsfc.nasa.gov/4720/','datum':'1737400 m sphere; original float TIFF kilometres converted to metres','color_note':'NASA LROC display mosaic; polar albedo fill, not analytical photometry'}}
def save_grid(z, ident, name, body, lon,lat,cell,source,url,datum,native,kind):
 valid=np.isfinite(z); vals=z[valid]
 if len(vals)==0: raise ValueError('No valid DEM samples')
 lo,hi=float(vals.min()),float(vals.max()); scale=max((hi-lo)/254,0.0001)
 q=np.full(z.shape,255,dtype='uint8');q[valid]=np.clip(np.rint((vals-lo)/scale),0,254).astype('uint8')
 file=f'{ident}-{kind}.png';Image.fromarray(q).save(OUT/file)
 return dict(id=ident,name=name,body=body,longitude=lon,latitude=lat,width=z.shape[1],height=z.shape[0],cell_m=cell,window_m=(z.shape[1]-1)*cell,offset_m=lo,scale_m=scale,nodata=255,center_m=float(np.median(vals)),min_m=lo,max_m=hi,coverage=float(valid.mean()),heightmap='unified/'+file,texture='unified/'+file,source=source,source_url=url,datum=datum,native_resolution_m=native,quantization_error_m=scale/2,sha256=hashlib.sha256((OUT/file).read_bytes()).hexdigest(),grid_crs=f'Local azimuthal equidistant at {lat}, {lon}; raster north-up')
def sample(src,lon,lat,body,cell,n):
 radius='+R=1737400' if body=='Moon' else '+R=3396000' if body=='Mars' else '+datum=WGS84'
 crs=f'+proj=aeqd +lat_0={lat} +lon_0={lon} {radius} +units=m'
 half=(n-1)*cell/2
 dst_transform=from_origin(-half-cell/2,half+cell/2,cell,cell)
 bounds=transform_bounds(crs,src.crs,-half-2*cell,-half-2*cell,half+2*cell,half+2*cell,densify_pts=41)
 win=from_bounds(*bounds,transform=src.transform).round_offsets().round_lengths()
 arr=src.read(1,window=win,boundless=False).astype('float32')
 if src.nodata is not None:arr[arr==src.nodata]=np.nan
 dst=np.full((n,n),np.nan,dtype='float32')
 reproject(arr,dst,src_transform=src.window_transform(win),src_crs=src.crs,src_nodata=np.nan,dst_transform=dst_transform,dst_crs=crs,dst_nodata=np.nan,resampling=Resampling.bilinear)
 return dst
# Global LOLA float km grid, equirectangular -180..180, north-up (NASA CGI Moon Kit).
with rasterio.open(RAW/'moon-global.tif') as src:g=src.read(1)*1000
for level in range(4):
 ny=2**level;nx=ny*2
 for y in range(ny):
  for x in range(nx):
   xs=np.linspace(x/nx,(x+1)/nx,65)*g.shape[1]-.5;ys=np.linspace(y/ny,(y+1)/ny,65)*g.shape[0]-.5
   xx,yy=np.meshgrid(xs,ys);x0=np.floor(xx).astype(int); y0=np.floor(yy).astype(int);fx=xx-x0;fy=yy-y0
   a=g[np.clip(y0,0,g.shape[0]-1),x0%g.shape[1]];b=g[np.clip(y0,0,g.shape[0]-1),(x0+1)%g.shape[1]];c=g[np.clip(y0+1,0,g.shape[0]-1),x0%g.shape[1]];d=g[np.clip(y0+1,0,g.shape[0]-1),(x0+1)%g.shape[1]]
   h=np.clip(np.rint((a*(1-fx)+b*fx)*(1-fy)+(c*(1-fx)+d*fx)*fy)+32768,0,65535).astype('uint16')
   rgb=np.zeros((65,65,3),dtype='uint8');rgb[:,:,0]=h//256;rgb[:,:,1]=h%256
   path=OUT/f'moon/{level}/{x}';path.mkdir(parents=True,exist_ok=True);Image.fromarray(rgb).save(path/f'{y}.png')
shutil.copyfile(RAW/'moon-color.jpg',OUT/'moon-color.jpg')
# Resample existing HiRISE visual crop to the same 30 m display grid as Moon/Earth.
m=json.loads((ROOT/'frontend/public/surface/manifest.json').read_text())
s=next(s for s in m['sites'] if s['id']=='mars-jezero-fan')
q=np.asarray(Image.open(ROOT/'frontend/public/surface'/s['heightmap']).convert('L'));h=np.where(q==255,np.nan,s['offset_m']+q*s['scale_m']).astype('float32')
z=np.full((61,61),np.nan,dtype='float32');crs='+proj=aeqd +lat_0=18.49 +lon_0=77.41 +R=3396000 +units=m'
reproject(h,z,src_transform=from_origin(-900-9.375,900+9.375,18.75,18.75),src_crs=crs,src_nodata=np.nan,dst_transform=from_origin(-915,915,30,30),dst_crs=crs,dst_nodata=np.nan,resampling=Resampling.bilinear)
manifest['sites']['jezero']={'local':save_grid(z,'jezero','Jezero','Mars',77.41,18.49,30,s['source'],s['source_url'],'Mars 2000 equipotential',18.75,'local')}
manifest['sites']['jezero']['local']['upstream_quantization_error_m']=s['scale_m']/2
manifest['sites']['jezero']['local']['quantization_error_m']+=s['scale_m']/2
from rasterio.io import MemoryFile
file=ROOT/'data/raw/frontend-surface/mola128-rows3072-3455.bin'
assert hashlib.sha256(file.read_bytes()).hexdigest()=='430ae7fb3b811bbe48697856d9ed21a412a1d14b4b29181cf7df474628bc762f'
fine=np.fromfile(file,dtype='>i2').reshape(384,11520).astype('float32')
with MemoryFile() as mem:
 with mem.open(driver='GTiff',height=384,width=11520,count=1,dtype='float32',crs='+proj=longlat +R=3396000',transform=from_origin(0,20,1/128,1/128)) as src:
  src.write(fine,1);z=sample(src,77.41,18.49,'Mars',150,161)
url='https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/megr44n000hb.img'
manifest['sites']['jezero']['regional']=save_grid(z,'jezero','Jezero','Mars',77.41,18.49,150,'NASA MGS / MOLA 128 ppd',url,'3396000 m sphere · radius grid, not areoid elevation',463.0625,'regional')

env=dict(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.TIF,.tif',GDAL_HTTP_TIMEOUT='20',GDAL_HTTP_MAX_RETRY='0',CPL_VSIL_CURL_CACHE_SIZE=32000000)
with rasterio.Env(**env):
 for ident,name,lon,lat in [('haworth-fondo','Haworth',-5,-87.45),('de-gerlache-cresta','De Gerlache',-68.7,-88.71)]:
  try:
   with rasterio.open('/vsicurl/'+LOLA) as src:
    manifest['sites'][ident]={kind:save_grid(sample(src,lon,lat,'Moon',cell,n),ident,name,'Moon',lon,lat,cell,'NASA LRO / LOLA 2009–2022',LOLA,'1737400 m sphere · MOON_ME_DE421',20,kind) for kind,cell,n in [('local',30,61),('regional',150,161)]}
   print(ident,'LOLA OK',flush=True)
  except Exception as e:manifest['missing'][ident]=str(e);print(ident,str(e),flush=True)
 # Public Copernicus COGs. Derivatives keyed to exact candidate ID and centre, not ranking position.
 candidates={}
 for ref in ['jezero','haworth-fondo']:
  for row in json.loads((ROOT/f'frontend/public/simulation/{ref}.json').read_text())['results']:candidates[row['region_id']]=row
 for ident,r in candidates.items():
  lon,lat=r['longitude'],r['latitude'];sn='N' if lat>=0 else 'S';ew='E' if lon>=0 else 'W'
  tile=f'Copernicus_DSM_COG_10_{sn}{abs(math.floor(lat)):02}_00_{ew}{abs(math.floor(lon)):03}_00_DEM'
  url=f'https://copernicus-dem-30m.s3.amazonaws.com/{tile}/{tile}.tif'
  try:
   with rasterio.open('/vsicurl/'+url) as src:
    manifest['sites'][ident]={kind:save_grid(sample(src,lon,lat,'Earth',cell,n),ident,f'Candidata {r["rank"]}','Earth',lon,lat,cell,'Copernicus DEM GLO-30',url,'EGM2008 · DSM, incluye objetos superficiales','1 arcsec (~30 m; varía con latitud)',kind) for kind,cell,n in [('local',30,61),('regional',150,161)]}
   print(ident,'GLO-30 OK',flush=True)
  except Exception as e:manifest['missing'][ident]='Sin derivado DEM válido: '+str(e);print(ident,str(e),flush=True)
manifest['inputs']={file:hashlib.sha256((RAW/file).read_bytes()).hexdigest() for file in ['moon-global.tif','moon-color.jpg']}
(OUT/'catalog.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print('SAVED',len(manifest['sites']),len(manifest['missing']),flush=True)
