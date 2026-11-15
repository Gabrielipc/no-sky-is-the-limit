# Regolith · Explorar y comparar

Entrega y verificación: 15 de noviembre de 2026. Frontend React/TypeScript/Cesium.
La pantalla inicial reúne referencia, candidatas, mapa, escalas y explicación del
parecido. Los análisis existentes permanecen en «Otros análisis».

## Disponibilidad verificada

| Referencia | Órbita | Relieve regional | Superficie local | Comparaciones |
|---|---|---|---|---|
| Jezero, 18,49° N / 77,41° E | MOLA global 4 ppd | MOLA 128 ppd (~463 m) + recorte CTX (~81 m/píxel visual) | HiRISE, nativo 18,75 m, rejilla visual 30 m | 10 candidatas del ejemplo del repositorio |
| Fondo de Haworth, 87,45° S / 5° O | LOLA global 4 ppd | LOLA polar, nativo 20 m, rejilla visual 150 m | LOLA, rejilla visual 30 m | 10 candidatas de su propio ejemplo |
| Cresta de De Gerlache, 88,71° S / 68,7° O | LOLA global 4 ppd | Su propio recorte LOLA polar | Su propio recorte LOLA a 30 m | Sin comparaciones publicadas; el terreno sigue navegable |

Las 20 candidatas terrestres de las dos demostraciones tienen derivados GLO-30
regionales y locales vinculados a su identificador y centro exactos. Se conserva
el área sin soporte en bordes de tesela; tener un DEM no cambia la elegibilidad.
La referencia de De Gerlache procede de un punto publicado con precisión de dos
decimales (~300 m), y Haworth usa un centro aproximado del fondo.

La API local devuelve `/api/atlas/versions = []` y `/api/atlas = 503`: no hay una
release activa con resultados adicionales. No existe el servicio de recálculo de
pesos. Jezero y Haworth se identifican como **demostraciones precalculadas** y
mantienen la etiqueta experimental y todos los avisos originales. De Gerlache no
recibe el ranking de ninguna otra referencia.

## Lectura científica del visor

- El control de escala conserva referencia, candidata, método y release en la URL.
  El zoom libre y la ampliación de grupos cambian la cámara, no la pareja.
- Región: recortes de 24 km y encuadres iniciales equivalentes, con norte,
  barra de distancia medida, huellas de 3 km y 1,8 km y resolución nativa visible.
  Las imágenes y los DEM conservan su georreferencia; las regiones polares se
  colocan sobre el cuerpo curvo mediante distancias geodésicas.
- Local: 61 × 61 vértices, 30 m de separación, 1,8 km entre extremos. Altura
  relativa a la mediana para no restar datums planetarios diferentes. Rampa y
  rango compartidos por las dos mallas válidas; los perfiles recorren 1.800 m.
- La pendiente visual usa diferencias centrales sobre 60 m. La pendiente del
  ranking conserva su base original de 240 m y la rugosidad su radio de 360 m.
  No se genera una capa de rugosidad sin soporte comparable.
- La exageración parte de 1× y no cambia métricas, perfiles ni distancias
  horizontales. Cambiar capa no recalcula el ranking.
- «Datos y método» reúne procedencia, datums, cuantización, cobertura del DEM,
  valores originales, diferencias, contribuciones, dimensiones y pesos desactivados.
  La cobertura del ranking es una fracción de peso evaluado; no es cobertura del DEM.
- Cesium transmite teselas MOLA/LOLA y terreno terrestre por nivel de detalle.
  Un cuerpo de contexto sin elevación evita un lienzo vacío mientras se preparan
  las teselas; el visor lo identifica como relieve global pendiente. Los recortes
  regionales y locales se cargan bajo demanda y las peticiones obsoletas se cancelan.

Los originales científicos permanecen en `data/raw/`, fuera de Git. El catálogo
`frontend/public/surface/unified/catalog.json` registra fuentes, centros, datums,
escalas de gris, nodata, resolución, cobertura y hashes. Su README documenta las
atribuciones, incluidas NASA y Copernicus. El logotipo es un recorte fiel del
manual aportado; las superficies sintéticas del manual no son evidencia.

## Ejecutar

```sh
cd frontend
npm ci
npm run dev
```

Abrir `http://127.0.0.1:5173/`. Para consultar el servicio existente, iniciarlo desde
la raíz en otro terminal:

```sh
.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Para verificar producción:

```sh
cd frontend
npm run build
npm exec vite preview -- --host 127.0.0.1 --port 4174
```

Los activos se empaquetan en `/analysis/surface`, `/analysis/simulation` y
`/analysis/brand`; DM Sans se emite en `/assets`. Funcionan con los mounts actuales
del backend, sin añadir rutas. Se verificaron por HTTP el índice, logo, fuente,
Cesium, catálogo, DEM lunares y ejemplo de Haworth en una instancia de la API.

La regeneración offline usa `frontend/scripts/prepare-unified-terrain.py`, numpy,
rasterio y Pillow. Requiere los originales NASA del CGI Moon Kit y los rangos
MOLA ya auditados en el proyecto; hace lecturas HTTP acotadas de LOLA y GLO-30.
No es necesario regenerarlos para ejecutar el frontend.

## Comprobaciones realizadas

`npm test`: **38 pruebas correctas**. `npm run build`: correcto. Incluyen
persistencia de la pareja, identidad y centro de DEM, orientación y huecos de
malla, pendientes, rangos compartidos, geodesia lunar, hashes, grupos con selección
separada, cancelación y rechazo de HTML o imágenes corruptas como si fueran DEM.

Safari, escritorio y modo adaptable de **390 × 844**, con selección desde el mapa:

1. Jezero → candidata 4 (`utm-ups-v1-10000-32631-323-71`) en escritorio.
   Órbita → regional → local conserva la pareja, distancia 0,000207 y sus medidas.
2. Jezero móvil: ampliar un grupo de cuatro puntos y elegir la candidata 2
   (`utm-ups-v1-10000-32616-533-28`) desde su marcador. Revisar las tres escalas;
   se conserva su exclusión por vegetación densa, sin modificar el ranking.
3. Haworth → candidata 4 (`utm-ups-v1-10000-32645-356-55`) desde el mapa,
   tanto en escritorio como en móvil. Se conservan la distancia 0,000081, las
   coordenadas y la referencia en las tres escalas; las mallas y perfiles son propios.
4. De Gerlache en local, regional y órbita: perfil LOLA propio y «Sin comparaciones
   publicadas», sin candidatas ni métricas heredadas de Haworth.
5. DEM ausente: retirar temporalmente solo un PNG del build de prueba de la
   candidata terrestre de Haworth. El visor muestra «Sin malla local disponible»
   y «La fuente no devolvió una imagen DEM válida», conserva la malla y el perfil
   lunar y mantiene distancia y métricas del motor. Se restauró el PNG original.
6. Servicio sin publicación: las consultas automáticas abren los ejemplos
   identificados. Enlaces con una candidata inexistente no seleccionan otra de
   forma silenciosa y permiten elegir un marcador o usar la lista de teclado.

No se necesita un token de Cesium ion para los recorridos incluidos. La imagen
regional terrestre y el terreno global de Esri dependen de su servicio externo;
los DEM preparados y el contexto NASA están empaquetados. La validación móvil se
hizo en el modo adaptable de Safari; no equivale a una prueba en hardware iOS.
