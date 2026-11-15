# Superficie 3D con CesiumJS

Abre `http://127.0.0.1:5173/?view=surface`. El destino inicial es Jezero; `&surfaceSite=earth-utah` o `&surfaceSite=earth-atacama` abre una candidata terrestre. Los recorridos científicos existentes se conservan.

## Ejecutar

```sh
npm --prefix frontend ci
npm --prefix frontend run dev
```

Esta vista utiliza archivos estáticos y no requiere la API de Python ni Cesium ion. Cesium ya pertenece a las dependencias del proyecto. El servidor usa `127.0.0.1:5173`; para los demás recorridos, inicia también el backend según el README.

## Recorrido

1. **Órbita:** planeta completo con textura global y navegación libre.
2. **Relieve regional:** vuelo al destino y terreno solicitado por teselas.
3. **Superficie local:** ventana de 1,8 × 1,8 km reconstruida desde un PNG en grises. La malla se puede girar, acercar y exagerar de 1× a 5×, con textura de relieve o alturas.

El botón de encuadre restaura la cámara. La sección de método ofrece el PNG, la fuente y el manifiesto de calibración. Cambiar destino retira las capas externas y vuelve a órbita.

## Datos y límites

Marte usa el producto de radios MOLA MEGR90N000CB descargado de NASA PDS, referido a una esfera de 3.396.000 m. Su resolución original es 0,25° (unos 14,8 km en el ecuador). La pirámide local tiene niveles 0–4; acercarse no produce nuevo detalle. La textura global existente muestra elevación en falso color.

La Tierra utiliza Blue Marble Next Generation de NASA, obtenida mediante GIBS cuando el servidor de imágenes Visible Earth no respondió. El terreno global se solicita al servicio público Esri World Elevation. Este servicio requiere red y puede variar su disponibilidad; si falla al iniciar, el visor informa que muestra un elipsoide sin elevación.

Las ventanas locales proceden de los recortes HiRISE/SRTM verificados del proyecto. El PNG conserva una escala y un offset en metros, un valor reservado para ausencia de datos y un error de cuantización documentado. JavaScript desplaza una cuadrícula en coordenadas este/norte/arriba, calcula normales y aplica una textura. Las caras que tocan datos ausentes se omiten. Se oculta el globo en esta vista porque la altura se centra en la mediana del DEM, sin afirmar una equivalencia entre datums verticales.

Las texturas locales son relieve sombreado derivado del DEM, no fotografías de superficie. El salto de terreno global a ventana local es explícito. Los resultados científicos del atlas no se recalculan con estas imágenes de visualización.

Consulta [formatos, fuentes, hashes y reproducción de los recursos](../frontend/public/surface/README.md). Los originales descargados permanecen en `data/raw/frontend-surface/`, excluidos de Git.

## Servicios externos

En un destino terrestre, abre **Conectar terreno o 3D Tiles**. Introduce una raíz de terreno con `layer.json` (quantized-mesh), o un `tileset.json` georreferenciado en WGS84. El servidor debe permitir CORS. En una página HTTPS, la fuente también debe usar HTTPS. Las URLs con credenciales embebidas se rechazan; no se persisten tokens ni URLs de servicios.

Cesium carga los 3D Tiles por demanda y vuela a su volumen. La capa se oculta durante la inspección del DEM local. **Quitar capa** retira los 3D Tiles o restaura el proveedor terrestre predeterminado. Las teselas fallidas generan un aviso. La interfaz no transforma automáticamente tilesets terrestres a coordenadas marcianas.

## Implementación y comprobación

- `frontend/src/features/surface/SurfaceWorkspace.tsx`: controles, catálogo y formulario de servicios.
- `SurfaceScene.tsx`: ciclo de vida de Cesium, proveedores, cámara, malla y 3D Tiles. Libera recursos y aborta lecturas al cambiar de destino.
- `terrain.ts`: decodificación, geometría y validación de URL, independientes de WebGL.
- `assets.ts`: lectura de PNG como muestras, con conversión de color desactivada.
- `scripts/preparar_superficie_frontend.py`: preparación reproducible con numpy y rasterio.

Cesium se carga de forma diferida. Vite conserva sus workers y recursos en producción. Se limita la densidad de renderizado a 1,5 píxeles por píxel CSS y se solicita renderizado cuando la escena cambia.

```sh
npm --prefix frontend test
npm --prefix frontend run build
.venv/bin/python -m unittest tests.test_frontend_surface_assets
```

Los controles verifican rutas, unidades, orientación, caras, ausencia de datos, URLs, hashes y continuidad de todas las teselas MOLA, incluida la costura de longitud. Para revisar el bundle final: `cd frontend && npx vite preview --host 127.0.0.1`.

Validación de esta entrega: compilación de producción, 17 pruebas del frontend y 3 de recursos aprobadas. En Safari se revisaron el globo marciano, el relieve terrestre conectado, las mallas locales de los tres destinos, la exageración y el cambio de textura. El bundle de producción también cargó y dibujó el ejemplo público `TilesetWithDiscreteLOD` de CesiumGS mediante el formulario de 3D Tiles. Ese ejemplo se usó solo para comprobar el cargador; no forma parte del catálogo científico ni de los recursos incluidos. El conector de terreno quantized-mesh admite la API nativa de Cesium, pero no se verificó con un servicio externo de ese formato en esta sesión.
