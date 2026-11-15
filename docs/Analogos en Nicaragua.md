# Análogos planetarios en Nicaragua

La vista **Nicaragua** (`/?view=nicaragua`, botón «Nicaragua» en la cabecera) muestra qué lugares del país se parecen a los sitios de referencia de Marte y la Luna, con foco en las zonas volcánicas. Reúne dos tipos de lugar:

- **Análogos conocidos**: Cerro Negro, Momotombo, Telica y los Hervideros de San Jacinto, estudiados como análogos de la alteración ácido-sulfática de Marte temprano (Hynek et al. 2013, [doi:10.1002/jgre.20140](https://doi.org/10.1002/jgre.20140); Marcucci et al. 2013, [doi:10.1002/jgre.20159](https://doi.org/10.1002/jgre.20159)). Lo son por su química y sus procesos, según la literatura citada en `data/nicaragua/sitios-conocidos.json`.
- **Lugares por descubrir**: las ventanas de 3 km que el motor de similitud clasifica como más parecidas a la referencia elegida y que no coinciden con un análogo publicado. Son hipótesis para revisar, no análogos confirmados.

La vista no necesita backend: lee el precálculo `frontend/public/analysis/nicaragua/analogos-nicaragua-v1.json`.

## Referencias

- **Marte y Luna**: Jezero, Haworth y De Gerlache, las referencias del motor.
- **Análogos conocidos como referencia terrestre**: «Relieve parecido a Cerro Negro» (y a los otros tres sitios) busca ventanas con una forma del relieve parecida a la de ese análogo. Se omiten las ventanas a menos de 5 km del propio sitio.

## Método

1. **Recorte**: contorno de Nicaragua de Natural Earth 1:10 m, simplificado a 0,005° (`data/nicaragua/frontera-ne10m.geojson`). No es un límite oficial, e incluye los lagos dentro del polígono.
2. **Zonas volcánicas**: centro de ventana a 10 km o menos de uno de los 13 volcanes holocenos del Global Volcanism Program (`data/nicaragua/volcanes-gvp.json`).
3. **Densificación**: el atlas global solo tiene una ventana de 3 km cada 10 km, y ninguna caía sobre los análogos conocidos. En las zonas volcánicas se añadieron 903 ventanas cada 2 km, una en cada cumbre y una en cada sitio conocido. Las calcula el mismo extractor del atlas (`pipelines/etl_extractors.extract_base_window`: Copernicus GLO-30 a 30 m, WorldCover y JRC). Quedan fuera del almacén y del ajuste del motor.
4. **Distancias**: el motor `motor-similitud-ml-v1` con sus pesos por defecto y sin el filtro de superficie árida, porque casi todo Nicaragua tiene bosque, cultivos o agua. La cobertura se muestra aparte. Las ventanas con al menos un 50 % de agua permanente no se clasifican.
5. **Puesto mundial**: posición que tendría la distancia de la ventana entre las 188 003 ventanas terrestres clasificables del atlas.

## Límites

- El motor compara la **forma del relieve** (escabrosidad, forma hipsométrica, organización de las pendientes y régimen morfológico). Las vistas espectral y térmica no están ajustadas para la Tierra, así que la mineralogía, que es lo que hace análogos a los sitios conocidos, no entra en la distancia.
- Con más de un 5 % de árboles el atlas no mide la rugosidad, así que esa feature queda ausente en casi todas las ventanas.
- Fuera de las zonas volcánicas solo hay una ventana cada 10 km.
- Las referencias de Marte y la Luna no son volcánicas. Un análogo volcánico marciano (conos de Hydraotes Colles o Home Plate, por ejemplo) necesitaría sus descriptores calculados desde un DTM.

## Reproducir

```sh
# Una vez: contorno y volcanes (descarga externa al scratchpad; las salidas se versionan)
./.pixi/envs/default/bin/python scripts/analogos_nicaragua.py boundary --shp ne_10m_admin_0_countries.shp
./.pixi/envs/default/bin/python scripts/analogos_nicaragua.py volcanoes --gvp gvp-nicaragua.json

# Ventanas densas (lee DEM y coberturas por HTTP; requiere `scripts/atlas30.py inventory`)
./.pixi/envs/default/bin/python scripts/analogos_nicaragua.py densify

# Precálculo con el motor (requiere data/feature_store_v1 y el modelo del motor)
./.pixi/envs/default/bin/python scripts/analogos_nicaragua.py compute
```

El GeoJSON de volcanes procede del servicio WFS del GVP (`GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes`, filtro `Country='Nicaragua'`). `densify` reanuda desde `data/normalized/nicaragua/ventanas-densas-v1.json` si los parámetros coinciden.

Pruebas: `tests/test_analogos_nicaragua.py` y `frontend/tests/nicaragua.test.cjs`.
