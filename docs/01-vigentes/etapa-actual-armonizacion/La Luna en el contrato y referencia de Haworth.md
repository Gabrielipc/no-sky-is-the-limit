# La Luna en el contrato y referencia de Haworth

Implementación del 14 de noviembre de 2026 para la sección 2.1 de la [auditoría de armonización](Auditoria%20de%20armonizacion%20y%20features%20frente%20a%20fuentes%20del%20challenge.md). El reto pide sitios para una base lunar permanente y Marte, pero el contrato solo conocía la Tierra y Marte.

**Resultado.** La Luna ya es un cuerpo del contrato, con su marco planetario, su partición y una tabla de dimensiones propias. La primera referencia, el fondo de Haworth, se midió con LOLA usando la misma huella y los mismos descriptores que en Tierra. Da relieve 147 m, pendiente P50 3,4° y P90 5,7°, y queda 100 % en sombra permanente, así que la compuerta lunar la clasifica como objetivo de volátiles. Después se añadió un sitio iluminado, la cresta de de Gerlache (punto C de Bussey et al., 2010). Con la huella de 3 km resulta mucho más escarpado (P90 22,4°), y la compuerta provisional de 15° lo excluye por pendiente (ver [sitio iluminado](#sitio-iluminado-cresta-de-de-gerlache)). De las cinco dimensiones lunares, la fracción PSR está medida. Iluminación, Diviner (temperaturas y regolito) y Mini‑RF tienen el contrato y el extractor listos, pero esperan un archivo verificado.

## Qué cambió en el contrato

| Elemento | Antes | Ahora |
|---|---|---|
| `body` | `Earth`, `Mars` | `Earth`, `Mars`, `Moon` |
| Procedencia (`source_manifests`) | Sin CRS ni marco | `crs_wkt` (CRS nativo del activo) y `planetary_frame` (`EARTH_WGS84`, `IAU_MARS`, `MOON_ME_DE421`). Los manifiestos terrestres sin marco se completan como EPSG:4326 al escribir. |
| Partición de `base_windows` | Bandas UTM/UPS | Además `MOON_SPS` y `MOON_NPS`, estereográficas polares por hemisferio, que son las proyecciones de los productos polares LOLA. Solo se admiten sitios con \|lat\| ≥ 60°. |
| Elegibilidad | `mars_reference_surface` | Además `moon_reference_surface` con perfil `moon_reference`. Las fracciones de cobertura terrestre quedan nulas y `cover_status = not_requested`. |
| Tabla nueva | — | `enrichment_lunar`, con la iluminación, la fracción PSR, las temperaturas de Diviner, la abundancia de rocas y el parámetro H, y el CPR de Mini‑RF. Cada dimensión guarda su fracción válida y su estado, más el estado de la compuerta lunar. |
| `features_unified` | Estados espectrales y HLS `unobserved_by_product` solo en Marte | Igual en la Luna. Las columnas lunares quedan `unobserved_by_product` en la Tierra y en Marte. |

Código: [`pipelines/etl_lunar_schema.py`](../../../pipelines/etl_lunar_schema.py) (esquema, sin dependencias para evitar ciclos), [`pipelines/etl_lunar.py`](../../../pipelines/etl_lunar.py) (geometría, lectura y extracción), [`scripts/etl_luna.py`](../../../scripts/etl_luna.py) (CLI) y [`specs/sources/luna-polar-sur-v1.json`](../../../specs/sources/luna-polar-sur-v1.json) (fuentes, capas, compuerta y sitios).

## Cómo se mide una ventana lunar

- **Misma huella:** núcleo de 3 km, halo de 720 m, celda de 30 m, base de pendiente de 240 m y radio de rugosidad de 360 m. Usa la misma función que en Tierra (`compute_topography_features`), incluidos los descriptores de forma.
- **Rejilla:** azimutal equidistante local sobre la esfera IAU de 1737,4 km, centrada en el sitio, como la referencia de Jezero. Así las distancias son reales en la huella. La estereográfica polar solo sirve para particionar. A 87,45° S su factor de escala es 0,9995, y a 80° S sería 0,992.
- **Soporte:** cada celda de 30 m exige soporte nativo completo, como en Jezero. Si el ráster no está en la esfera lunar (radio distinto de 1 737 400 m), se rechaza.
- **Lectura:** los GeoTIFF COG de PGDA se leen solo en la ventana (HTTP 206). Una ventana con halo son 246 × 246 píxeles de 20 m y se lee en unos 13 s. Una copia local verificada tiene prioridad si existe.

## Dimensiones lunares y su estado

| Dimensión | Producto | Estado de la fuente | Nivel de comparabilidad |
|---|---|---|---|
| Topografía y forma | LOLA `LDEM_80S_20MPP_ADJ` (Barker et al., 2023), 20 m, metros, estereográfica polar sur, R = 1 737 400 m | **Confirmada** | `direct_metric` con GLO‑30 en la misma huella |
| Fracción PSR | LOLA `LPSR_80S_20MPP_ADJ`, máscara 0/1 a 20 m | **Confirmada** | `planet_specific_constraint` (compuerta) |
| Iluminación promedio | PGDA *Lunar Polar Illumination* (producto 69) | Pendiente: la página no mostró el archivo | `planet_specific_constraint` (compuerta) |
| Tmax, Tmin y amplitud | Diviner PRP sur (`dlre_prp_south.tab`, 605 MB) | Pendiente de adaptador: es una tabla ASCII de 15 columnas cuya estructura (`DLRE_PRP.FMT`) falta leer | `functional_contract_bridge` con climatología MODIS LST, por percentil |
| Abundancia de rocas y parámetro H | Productos derivados de Diviner | Pendiente: no figuran por nombre en PDS Geosciences | `functional_contract_bridge` con la ATI de MODIS, por percentil |
| CPR y S1 | Mosaicos polares Mini‑RF (CDR‑MOSAIC) | Pendiente: falta fijar archivo, bandas y CRS | `functional_contract_bridge` con RCM compacto, por percentil |

Una dimensión cuyas fuentes no están confirmadas queda `on_demand_fetchable`, sin adivinar valores. Para activarla basta con cambiar la fuente a `confirmed` en la especificación, con URL o ruta, escala y rango válido. La amplitud térmica es la mediana por celda de Tmax − Tmin, no la diferencia de medianas, y todas las columnas de una dimensión comparten denominador.

### Compuerta del sitio lunar (`lunar_polar_base_v1`)

1. Fracción PSR ≥ 0,5 → `volatile_target_psr`.
2. Sin pendiente → `pending_topography`; pendiente P90 > 15° → `excluded_steep`.
3. Sin iluminación → `pending_illumination`; iluminación media < 0,3 → `excluded_low_illumination`.
4. Si pasa todo lo anterior → `base_candidate_illuminated`.

Los umbrales son decisiones iniciales. Hay que validarlos con las regiones candidatas de Artemis III antes de usarlos para ordenar sitios.

## Referencia: fondo de Haworth

Haworth es una región candidata de Artemis III y una trampa fría. El sitio está en el centro aproximado del fondo (87,45° S, 5,0° O); LOLA confirma que la ventana está a unos −3,3 km de altura y 100 % en el mapa PSR.

| Feature | Haworth (LOLA, 30 m) | Jezero (HiRISE, 30 m) |
|---|---:|---:|
| Relieve P95−P5 | 146,9 m | 120,3 m |
| Pendiente P50 (base 240 m) | 3,43° | 3,07° |
| Pendiente P90 | 5,69° | 9,24° |
| Rugosidad 360 m P50 | 3,46 m | — |
| Integral hipsométrica | 0,443 | ver [descriptores de forma](Descriptores%20de%20forma%20y%20redundancia%20del%20vector%20topografico.md) |
| Concentración de orientación | 0,668 | |
| Asimetría de elevación | 0,262 | |
| Fracción PSR | 1,00 | — |
| Compuerta lunar | `volatile_target_psr` | — |

La asimetría positiva corresponde a un fondo plano con bordes más altos, lo que encaja con el fondo de un cráter. El halo de 720 m alcanza el inicio de las paredes.

### Contraparte terrestre

`scripts/etl_luna.py rank --site haworth-fondo` ordena las ventanas terrestres con la misma distancia que se usa para Jezero, con `polar_cold_v1` por defecto:

- **Con la compuerta polar**, solo hay 12 ventanas elegibles, porque 1 461 704 ventanas del almacén siguen pendientes de cobertura. Las 12 vienen del refinamiento de Jezero y se parecen más a él (P90 ≈ 9°). La mejor tiene una distancia de 0,77.
- **Sin la compuerta**, las más cercanas tienen una distancia ≈ 0,01. Están en la meseta de Putorana y el norte de Siberia (61–70° N, 89–95° E) y en los Adirondack (44,5° N), con relieve de 145–148 m, P50 de 3,3–3,5° y P90 de 5,6–5,8°. Aún no se ha comprobado su cobertura.

La lista útil para el escenario polar depende del relleno de cobertura WorldCover/JRC, que se está trabajando por separado. La evidencia completa, con identidades y los dos rankings, está en [`docs/evidencia-luna-polar/resultados.json`](../../evidencia-luna-polar/resultados.json).

## Sitio iluminado: cresta de de Gerlache

El escenario de base necesita un sitio con luz casi continua, como contraste del fondo en sombra de Haworth. Se tomó el punto C de la tabla de Bussey et al. (2010, *Icarus* 208, 558–564): 88,71° S, 68,7° O, con 85 % de iluminación anual en el punto y un mínimo de 64 % por día lunar. Es el punto con más iluminación de esa tabla. Las coordenadas se leyeron en la tabla que reproduce Wikipedia (*Peak of eternal light*); el artículo original no pudo abrirse.

**Comprobación independiente con LOLA.** `check_site_position` (en `pipelines/etl_lunar.py`) se ejecuta ahora en cada sitio y se guarda en la evidencia. No mueve el sitio.

| Punto de Bussey (2010) | Percentil de elevación del centro en su huella | Distancia al máximo local (±300 m) | PSR en el centro | PSR en la huella |
|---|---:|---:|---:|---:|
| A, cresta de Shackleton | 0,74 | 345 m | 0 | 1,8 % |
| B, pico cerca de Shackleton | 0,53 | 304 m | 0 | 1,9 % |
| **C, cresta de de Gerlache** | **0,87** | **340 m** | **0** | **0,3 %** |
| D, pico cerca de Shackleton | 0,86 | 403 m | 0 | 0,4 % |
| M1, monte Malapert | 0,53 | 295 m | 0 | 4,9 % |

Los cinco puntos están fuera de la sombra permanente, lo que es coherente con su iluminación. Ninguno cae justo sobre una cima del DEM de 2023: el máximo local está a 300–400 m, en el borde de la caja de búsqueda. Encaja con coordenadas de 2010 dadas con dos decimales (0,01° de latitud ≈ 300 m) sobre una topografía anterior. Se eligió C porque combina la mayor iluminación publicada con el centro más alto de su huella y la menor fracción de PSR.

| Feature (30 m, base 240 m) | Cresta de de Gerlache | Fondo de Haworth |
|---|---:|---:|
| Relieve P95−P5 | 465,6 m | 146,9 m |
| Pendiente P50 | 13,08° | 3,43° |
| Pendiente P90 | 22,40° | 5,69° |
| Fracción > 15° / > 25° | 0,364 / 0,006 | 0 / 0 |
| Rugosidad 360 m P50 | 6,27 m | 3,46 m |
| Integral hipsométrica | 0,588 | 0,443 |
| Asimetría de elevación | −0,265 | 0,262 |
| Concentración de orientación | 0,381 | 0,668 |
| Fracción PSR | 0,003 | 1,00 |
| Compuerta lunar | `excluded_steep` | `volatile_target_psr` |

La integral alta y la asimetría negativa describen un alto convexo, el opuesto del fondo del cráter, y una orientación poco concentrada encaja con una cresta que cae hacia varios lados. **Un 36 % de la huella supera 15°.** Con la compuerta provisional (P90 ≤ 15°), el sitio más iluminado de la tabla queda excluido. Eso no indica que el sitio sea inútil. Muestra que la compuerta mide la escabrosidad de la huella de 3 km, mientras que una zona de aterrizaje en una cresta es un rellano de cientos de metros. Para el escenario de base, la pendiente debería evaluarse en una huella menor o como superficie transitable alrededor del punto, no como P90 de 3 km. El umbral no se cambió para que el sitio pase. Sin el producto de iluminación, `illumination_mean_fraction` queda pendiente: el 85 % publicado es de un punto, no la media de la huella.

**Contraparte terrestre.** Las 12 ventanas elegibles en `polar_cold_v1` quedan lejos (distancia ≥ 0,98). Sin la compuerta, las más cercanas tienen una distancia de 0,005 a 0,01, con relieve de 464–471 m, P50 de 12,9–13,1° y P90 de 22–23°. Están en los Andes patagónicos (42,3° S, 71,8° O), en Drakensberg (29,4° S, 29,6° E), en Montana (46,0° N, 112,8° O) y en la Columbia Británica (51,4° N, 122,1° O). Son relieves montañosos sin revisión de cobertura, no análogos polares todavía.

## Límites

- Hay un sitio en sombra y uno iluminado, y el iluminado no pasa la compuerta de pendiente con la huella de 3 km. Las coordenadas del sitio iluminado vienen de una fuente secundaria y se comprobaron solo de forma indirecta con LOLA.
- El DEM de 20 m interpola entre trazas LOLA. La comparación con GLO‑30 es directa en el operador, pero no en la resolución efectiva.
- La procedencia remota se identifica por ETag o por tamaño y fecha, no por SHA‑256, igual que las lecturas por rangos de GLO‑30.
- No se tocó el ranking: Haworth es una referencia alternativa a Jezero y no entra en la distancia de las ventanas terrestres como término adicional.

## Uso

```bash
.pixi/envs/default/bin/python scripts/etl_luna.py referencia
```

```bash
.pixi/envs/default/bin/python scripts/etl_luna.py rank --site haworth-fondo --profile polar_cold_v1 --limit 15
```
