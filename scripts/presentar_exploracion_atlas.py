#!/usr/bin/env python3
"""Render figures and readable observed tables from the offline exploration."""
from collections import defaultdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
import sys

os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'analogos-matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Rectangle, Patch
from matplotlib.colors import ListedColormap, BoundaryNorm
import geopandas as gpd
import numpy as np
import rasterio

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.explorar_fuentes_atlas import OUT, CENTERS, native_crop, read_crop

LABELS={'desierto':'Utah','montana':'Montaña','costa':'Costa','tropico':'Trópico','polar':'Antártida',
        'atacama-materiales':'Atacama · materiales'}


def load(name): return json.loads((OUT/name).read_text())
def number(x, digits=2): return '—' if x is None else f'{x:.{digits}f}'
def percent(x): return '—' if x is None else f'{100*x:.1f} %'


def scene_date(r):
    s=r['scene']
    return datetime.strptime(s.split('.')[3][:7],'%Y%j') if r['source']=='hls' else datetime.strptime(s.split('_')[3],'%Y%m%d')


def save(fig,name):
    fig.savefig(OUT/f'{name}.png',dpi=170,facecolor='white')
    svg=OUT/f'{name}.svg'
    fig.savefig(svg,facecolor='white',metadata={'Date':None})
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    plt.close(fig)


def figures(inv,temporal):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'axes.titleweight':'bold', 'svg.hashsalt':'atlas-exploracion-v1'})
    land=gpd.read_file(f'zip://{ROOT}/data/raw/atlas30/land/ne_10m_land.zip')
    # Simplification is for the world-map background only, never a scientific mask.
    land.geometry=land.geometry.simplify(.05,preserve_topology=True)
    fig,ax=plt.subplots(figsize=(14,7))
    land.plot(ax=ax,color='#e5e9ed',edgecolor='#b2bdc6',linewidth=.2)
    tiles=[]
    for r in inv:
        if r['family']=='glo30' and r['status']=='header_read':
            w,s,e,n=r['bounds']; tiles.append(Rectangle((w,s),e-w,n-s))
    ax.add_collection(PatchCollection(tiles,facecolor='#188b98',edgecolor='none',alpha=.8))
    offsets={'desierto':(10,10),'montana':(10,10),'costa':(-95,-10),'tropico':(10,10),
             'polar':(10,10),'atacama-materiales':(15,-28)}
    for k,(lon,lat) in CENTERS.items():
        ax.scatter(lon,lat,s=28,color='#c44b32',zorder=4)
        ax.annotate(LABELS[k],(lon,lat),xytext=offsets[k],textcoords='offset points',fontsize=9,
                    color='#922f1c',arrowprops={'arrowstyle':'-','color':'#922f1c','lw':.6})
    ax.set(xlim=(-180,180),ylim=(-90,90),xlabel='Longitud',ylabel='Latitud',
           title=f'Disponibilidad local: {len(tiles):,} teselas GLO-30 y seis ventanas de exploración'.replace(',', '.'))
    ax.set_aspect('auto');ax.grid(alpha=.15)
    ax.legend(handles=[Patch(color='#188b98',label='Extensión de teselas locales; validez interior sin evaluar aquí')],loc='lower left',fontsize=9)
    fig.text(.08,.025,'Instantánea local · 10 nov 2026. No representa la cobertura mundial del proveedor ni sitios análogos validados.',fontsize=10,color='#495560')
    fig.subplots_adjust(bottom=.13,top=.9);save(fig,'disponibilidad-local')

    fig,axes=plt.subplots(1,2,figsize=(16,9),gridspec_kw={'width_ratios':[1.15,1]})
    for ax,fam in zip(axes,['hls','landsat']):
        rows=sorted([r for r in temporal if r['source']==fam and r['status']=='profiled'],
                    key=lambda r:(list(LABELS).index(r['site']),scene_date(r)))
        values=[]; labels=[]
        for r in rows:
            stat=r['policies']['legacy']['ndvi' if fam=='hls' else 'temperature_k']
            values.append(stat['valid_fraction']*100)
            sensor=r['scene'].split('.')[1] if fam=='hls' else r['scene'][:4]
            labels.append(f'{LABELS[r["site"]]} · {sensor} · {scene_date(r):%d/%m}')
        y=np.arange(len(rows));bars=ax.barh(y,values,color=['#bd513b' if v<50 else '#188b98' for v in values],height=.65)
        for b,v in zip(bars,values):ax.text(min(v+1,102),b.get_y()+b.get_height()/2,f'{v:.1f} %',va='center',fontsize=9)
        ax.set_yticks(y,labels);ax.invert_yaxis();ax.set_xlim(0,118);ax.set_xticks([0,25,50,75,100])
        ax.set_xlabel('Centros válidos / centros de la huella (%)')
        ax.set_title('HLS · NDVI por escena' if fam=='hls' else 'Landsat · temperatura por escena')
        ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('La disponibilidad de escenas no garantiza observaciones útiles',fontsize=18,fontweight='bold',y=.98)
    fig.text(.06,.025,'Ventanas de 3 km · escenas seleccionadas de 2024 · política heredada de QA, explicitada en el informe.\nSin ponderación por área; los centros térmicos a 30 m no son observaciones independientes. Antártida: sin escenas seleccionadas.',fontsize=10)
    fig.tight_layout(rect=(.01,.08,.99,.95),w_pad=3);save(fig,'soporte-por-escena')

    spatial=load('perfiles-espaciales.json'); geoms=load('huellas.json')['earth']
    codes=[10,20,30,40,50,60,70,80,90,95,100]
    names=['Árboles','Matorral','Herbazal','Cultivos','Construido','Desnudo / escaso','Nieve / hielo','Agua','Humedal','Manglar','Musgo / liquen']
    colors=['#246331','#b1a65e','#8dc66a','#dfb64b','#d45b51','#c6b9a0','#d6eef4','#3b83b9','#6e9b9e','#386b69','#c7cc99']
    cmap=ListedColormap(colors);norm=BoundaryNorm(np.arange(-.5,11.5),11)
    fig,axes=plt.subplots(1,4,figsize=(16,5.5))
    for ax,site in zip(axes,['desierto','montana','costa','tropico']):
        rec=next(r for r in spatial if r['site']==site and r['source']=='worldcover')
        with rasterio.open(ROOT/rec['path']) as d:
            win,inside=native_crop(d,geoms[site]);a=read_crop(d,1,win)
            indexed=np.full(a.shape,np.nan)
            for i,code in enumerate(codes):indexed[(a==code)&inside]=i
            ax.imshow(indexed,cmap=cmap,norm=norm,interpolation='nearest',aspect='equal')
        ax.set_title(LABELS[site]);ax.set_xticks([]);ax.set_yticks([])
    fig.suptitle('Qué contienen realmente las ventanas piloto',fontsize=18,fontweight='bold')
    fig.legend(handles=[Patch(color=c,label=n) for c,n in zip(colors,names)],loc='lower center',ncol=6,frameon=False,bbox_to_anchor=(.5,.06),fontsize=9)
    fig.text(.05,.025,'WorldCover 2021 · centros nativos dentro de cada huella de 3 km. Cada panel conserva su propia rejilla; no es una escala común.',fontsize=10)
    fig.tight_layout(rect=(0,.19,1,.95));save(fig,'cobertura-pilotos')


def tables(inv,temporal):
    lines=['# Tablas de la exploración nativa','',
           'Generadas desde los JSON de esta carpeta. Fracciones por centros nativos; denominador = huella completa, sin máscara de tierra. No son fracciones exactas por área.','',
           '## Inventario físico','', '| Familia | Archivos | GB decimales | Estados |','|---|---:|---:|---|']
    for k,v in load('resumen.json')['families'].items():
        lines.append(f'| {k} | {v["files"]} | {v["bytes"]/1e9:.3f} | {v["statuses"]} |')
    lines+=['','## HLS por observación','',
            'La política `legacy` excluye nubes, adyacencia, sombra y agua; conserva nieve y todos los niveles de aerosol. Los índices se muestran como diagnóstico, aún sin filtrar reflectancias negativas.','',
            '| Ventana | Fecha | Sensor | NDVI p50 | NDMI p50 | NDSI p50 | Soporte NDVI | NDVI fuera de [−1,1] |',
            '|---|---|---|---:|---:|---:|---:|---:|']
    for r in temporal:
        if r['source']!='hls' or r['status']!='profiled':continue
        p=r['policies']['legacy']
        lines.append(f'| {r["site"]} | {scene_date(r):%Y-%m-%d} | {r["scene"].split(".")[1]} | '+
                     ' | '.join(number(p[k]['p50'],4) for k in ['ndvi','ndmi','ndsi'])+
                     f' | {percent(p["ndvi"]["valid_fraction"])} | {p["ndvi"]["outside_minus1_plus1"]} |')
    lines+=['','## Landsat por observación','',
            'QA heredada excluye relleno, nubes, cirros, dilatación, sombra y nieve. ST_QA se convierte a K; los umbrales son experimentales.','',
            '| Ventana | Fecha | T p05 / p50 / p95 (K) | Soporte | ST_QA p50 (K) | Soporte con ST_QA ≤ 2 K | Soporte con ST_QA ≤ 3 K |',
            '|---|---|---:|---:|---:|---:|---:|']
    for r in temporal:
        if r['source']!='landsat' or r['status']!='profiled':continue
        p=r['policies']['legacy'];t=p['temperature_k']
        lines.append(f'| {r["site"]} | {scene_date(r):%Y-%m-%d} | '+
                     ' / '.join(number(t[k]) for k in ['p05','p50','p95'])+
                     f' | {percent(t["valid_fraction"])} | {number(p["uncertainty_k"]["p50"])} | '+
                     ' | '.join(percent(r['uncertainty_sensitivity'][k]['valid_fraction']) for k in ['2','3'])+' |')
    lines+=['','## EMIT, nuevas huellas de 3 km','',
            'Fit × 2 sigue la interpretación documentada por NASA; conservar el dato almacenado. Celdas GLT y muestras originales únicas no son equivalentes. Los filtros no certifican minerales.','',
            '| Sitio / fecha | Centros GLT / muestras únicas | Grupo | Clasificados / huella | Sin coincidencia | Fit almacenado p50 | Fit × 2 p50 | Fit × 2 ≥ 0,8 y profundidad > 2σ |',
            '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in load('perfiles-emit.json'):
        for key,g in r['groups'].items():
            lines.append(f'| {r["site"]} · {r["date"][:10]} | {r["glt_cells"]} / {r["unique_raw_samples"]} | {key} | '+
                f'{g["matched_cells"]} / {r["footprint_cells"]} | {g["no_match_cells"]} | {number(g["fit_stored"]["p50"],4)} | '+
                f'{number(g["fit_times_two"]["p50"],4)} | {g["exploratory_quality_counts"]["0.8"]} |')
    lines+=['','## Variables CRISM observadas en Jezero, 3 km','',
            'Indicadores SR después de máscara IN = 0. No se interpretan automáticamente como clases, abundancias o detecciones minerales.','',
            '| Banda | Indicador | Centros válidos | p05 | p50 | p95 |','|---:|---|---:|---:|---:|---:|']
    for i,v in enumerate(load('perfiles-marte.json')[0]['variables'],1):
        lines.append(f'| {i} | `{v["name"]}` | {v["n"]} | '+ ' | '.join(number(v[k],6) for k in ['p05','p50','p95'])+' |')
    (OUT/'tablas-resultados.md').write_text('\n'.join(lines)+'\n')
    lines=['# Diccionario observado de archivos','',
           'Lectura de cabeceras y variables. Los valores `None` indican metadatos no declarados, no ausencia de magnitud física. Las reglas científicas complementarias están en el informe.','']
    groups=defaultdict(list)
    for r in inv:
        if r.get('variables'):groups[r['family']].append(r)
    for fam,rs in groups.items():
        lines += [f'## {fam}','','| Variable / banda | Tipo | Unidad en archivo | Relleno | Escala / offset de cabecera |','|---|---|---|---|---|']
        seen=set()
        for r in rs:
            for v in r['variables']:
                name=v['name']
                if fam=='hls':name=Path(r['path']).name.split('.')[-2]+' · '+name
                if fam=='landsat':name=next(b for b in ['ST_B10','ST_QA','QA_PIXEL'] if b in r['path'])
                attrs=v.get('attributes',{})
                data=[name,v.get('dtype'),v.get('unit_header',attrs.get('units')),
                      v.get('nodata',attrs.get('_FillValue')),
                      [v.get('scale_header',attrs.get('scale_factor')),v.get('offset_header',attrs.get('add_offset'))]]
                key=json.dumps(data)
                if key not in seen:lines.append('| '+' | '.join(str(x).replace('|','/') for x in data)+' |');seen.add(key)
        lines+=['']
    lines+=['## Capas dentro de archivos comprimidos','','| Archivo | Miembro | Bandas | Paso nativo |','|---|---|---:|---|']
    for r in inv:
        for member in r.get('members',[]):
            if 'bands' in member:lines.append(f'| {r["family"]} | {member["name"]} | {member["bands"]} | {member["step"]} |')
    lines+=['','La máscara Natural Earth incluye `featurecla`, `scalerank`, `min_zoom` y geometría; no es una capa de condiciones de operación. Los archivos GMTED se leen como rejillas dentro de ZIP; metadatos completos en `inventario.json`.','']
    (OUT/'diccionario-observado.md').write_text('\n'.join(lines))


def main():
    inv=load('inventario.json'); temporal=load('perfiles-temporales.json')
    figures(inv,temporal);tables(inv,temporal)
    paths=[Path(__file__)]+sorted(OUT.glob('*.png'))+sorted(OUT.glob('*.svg'))+[OUT/'tablas-resultados.md',OUT/'diccionario-observado.md']
    (OUT/'manifest-presentacion.json').write_text(json.dumps({'files':[{'path':str(p.relative_to(ROOT)),
        'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in paths]},indent=2)+'\n')


if __name__=='__main__':main()
