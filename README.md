# Atlas de análogos planetarios

La interfaz abre una comparación visual Jezero–Tierra con cuadrículas reales y colores comunes. Permite cambiar candidata, capa y tamaño de celda, explorar ventanas sobre un mapa y revisar por separado qué cambia con la fuente y la escala. Las fuentes, tablas y método se consultan bajo demanda. Consulta la [guía de conceptos](docs/Guia%20para%20entender%20el%20atlas.md) y la [entrega del refactor visual](docs/Refactor%20frontend%20-%20entrega.md).

Aplicación local para revisar candidatas terrestres según una pregunta de exploración. El recorrido de fase 3 compara un sector del abanico de Jezero con Utah y Atacama a partir del DTM HiRISE y SRTM analizados en fase 2: ventanas de 1,8 × 1,8 km, celdas de 60 o 120 m y métricas separadas de pendiente y relieve. Muestra fuentes, cobertura, sensibilidad a escala y datos pendientes. Los resultados son exploratorios y no evalúan movilidad. Los globos son contexto regional; los paneles del análisis muestran el detalle disponible.

La **fase 4** añade «Ampliar búsqueda»: 970 ventanas nuevas de 3 × 3 km en Utah, Mojave y Atacama, generadas con GMTED2010 a 300/600 m. Permite consultar perfiles de filtro, ventanas excluidas, controles, cobertura de muestreo y exportación GeoJSON. La evaluación local de detalle se mantiene separada; se incluye una ventana nueva de Utah calculada con el SRTM disponible. Consulta [la entrega de fase 4](docs/Fase%204%20-%20busqueda%20regional%20terrestre.md).

La **fase 5** añade «Reconocimiento · fuente y escala»: un segundo escenario que examina diez ventanas de fase 4, con siete evaluadas y tres pendientes. Contrasta GMTED y SRTM a 300/600 m y muestra SRTM frente a Jezero a 60/120/300/600 m. Expone la selección y sus sesgos; conserva los filtros solo en las escalas regionales. Se reproduce sin descargas con `./.pixi/envs/default/bin/python scripts/evaluar_expansion.py`. Consulta [la entrega de fase 5](docs/Fase%205%20-%20expansion%20condicionada.md).

La vista **Nicaragua** (`/?view=nicaragua`) busca análogos de Marte y la Luna dentro del país, con foco en sus 13 volcanes holocenos. Muestra los análogos ya publicados (Cerro Negro, Momotombo, Telica y San Jacinto) y propone lugares nuevos con el motor de similitud, sobre ventanas densificadas cada 2 km cerca de los volcanes. Consulta [método, límites y comandos](docs/Analogos%20en%20Nicaragua.md).

## Inicio

El recorrido **Superficie 3D** (`/?view=surface`) añade un visor CesiumJS para pasar de órbita a relieve regional y abrir mallas locales de Jezero, Utah y Atacama. Incluye teselas MOLA de NASA PDS, Blue Marble de NASA y PNG de alturas que JavaScript convierte en geometría. Permite ajustar la exageración, alternar textura y conectar servicios de terreno o 3D Tiles. Se ejecuta sin backend ni token; el relieve mundial terrestre requiere conexión a Esri. Ver [uso, arquitectura y límites del visor](docs/Superficie%203D%20-%20Cesium.md).

El recorrido **Más dimensiones** añade rugosidad sin inclinación, posición topográfica y curvatura discreta a 60/120 m, mapas con escala común y un panel de inercia térmica de Jezero. Conserva estados explícitos para propiedades todavía sin datos comparables. Incluye adquisición acotada de THEMIS, 3DEP, HiRISE y EMIT. Ver [extensión multidimensional y comandos](docs/Extension%20multidimensional.md); el cálculo se reproduce con `./.pixi/envs/default/bin/python scripts/analizar_dimensiones.py` y la vista se abre en `/?view=dimensions`.

La sección **Minerales** muestra los indicadores CRISM de Jezero junto a las identificaciones EMIT de Utah o Atacama. Cada mapa conserva su cuadrícula y escala. Jezero incluye cinco indicadores espectrales, el residuo atmosférico y la cobertura VNIR/IR. La Tierra conserva los grupos espectrales, el ajuste, la incertidumbre y el filtro de inclinación. [Procesamiento y cobertura de Jezero](docs/Adquisicion%20CRISM%20de%20Marte.md#integración-en-el-atlas).

La [adquisición CRISM de Marte](docs/Adquisicion%20CRISM%20de%20Marte.md) descarga y verifica el paquete de indicadores y calidad de Jezero (189 MB) sin token. Incluye presupuesto, reanudación e identidades registradas; el espectro completo es una opción separada. Comienza con `.pixi/envs/default/bin/python scripts/adquirir_marte.py discover` y luego `fetch --max-new-gb 0.25` usando el mismo script.

En macOS o Linux, desde la raíz del proyecto, ejecuta:

```sh
./scripts/inicializar.sh
```

Necesitas Bash, `curl`, conexión a internet y varios GB de espacio libre. La primera instalación descarga paquetes grandes, incluido `proj-data` (aproximadamente 800 MB comprimidos), y puede tardar varios minutos. El script instala [Pixi](https://pixi.prefix.dev/latest/installation/) dentro de `.tools/`, sin modificar la configuración de tu terminal; Pixi instala Python, Node.js y las bibliotecas geoespaciales indicadas en `pixi.toml`. También instala los paquetes del frontend, comprueba los CRS planetarios, ejecuta las pruebas y compila el frontend. Puedes volver a ejecutarlo; `npm ci` reemplaza `frontend/node_modules` según el lock. No descarga datos científicos ni credenciales.

Después, desde la raíz, inicia cada servicio en una terminal distinta:

```sh
make backend
```

```sh
make frontend
```

Abre [la aplicación](http://localhost:5173). La documentación de la API está en [FastAPI](http://127.0.0.1:8000/docs). `make check` repite las comprobaciones de entorno, API y compilación.

## Datos y método

La vista **Búsqueda mundial** (`/?view=world`) consulta el Atlas de 30 m. El muestreo activo puede ser parcial. Los comandos de adquisición, procesamiento, reanudación y publicación están en la [guía de operación](docs/Atlas%20de%2030%20m%20-%20operacion.md).

El recorrido principal lee `specs/analysis/primer-caso-fase2.json` y la evidencia revisada de `docs/evidencia-fase-2/`. Verifica tamaño y SHA-256 de los registros utilizados contra su manifiesto local. No necesita originales, descargas ni procesamiento de rásteres en cada consulta. Conserva estos archivos junto con el código; un archivo ausente o modificado genera un error explícito. Los rásteres originales en `data/raw/` están excluidos de Git.

Las pendientes se comparan mediante distancia de Wasserstein en grados; el relieve relativo se describe como p95−p5 y su diferencia candidata−Jezero en metros. No hay puntuación combinada en la interfaz nueva. La cobertura se informa por variable y no equivale a observaciones directas. Más dimensiones incorpora por separado minerales terrestres e inercia térmica de Jezero; sus comparaciones entre planetas, rocas/obstáculos, polvo y agua/hielo siguen pendientes. La [ficha de fase 3](docs/Fase%203%20-%20recorrido%20minimo%20en%20la%20aplicacion.md) explica el recorrido inicial y la API.

Las rutas históricas `/api/regions` y `/api/search` conservan el catálogo MOLA/SRTM de 10 km en `data/regions.json` para compatibilidad. `/api/search` está marcada como obsoleta en OpenAPI: sus porcentajes y pesos son ilustrativos y no se usan en la interfaz nueva. Su preparación se documenta en [la guía del prototipo](data/README-datos-reales.md). Las imágenes CTX/HLS, ML y el soporte lunar no están integrados.

La búsqueda nueva sirve los resultados y el manifiesto de `docs/evidencia-fase-4/` bajo `/api/regional-search`. No ejecuta un barrido ni descarga datos al consultar la API. Para reproducirla con los originales locales:

```sh
./.pixi/envs/default/bin/python scripts/buscar_candidatas.py audit
./.pixi/envs/default/bin/python scripts/buscar_candidatas.py search
./.pixi/envs/default/bin/python scripts/buscar_candidatas.py detail utah-010-007
```

La auditoría recorre ambos ZIP completos para comprobar CRC y SHA-256 y reconcilia únicamente sus entradas del manifiesto de adquisición. El barrido tiene un presupuesto de 1500 ventanas y no extrae el ráster global. `detail` adquiere archivos ausentes solo con `--download`, limitado a cuatro teselas SRTM y 50 MB por archivo. Los límites de adquisición y los umbrales se explican en la ficha de fase 4; no son criterios de idoneidad ni de precisión científica.

## Entorno y estructura de trabajo

El análisis reproducible de fase 2 sigue separado del catálogo histórico. Sus resultados, fuentes, límites y comandos están en [Primer análisis reproducible — Jezero y candidatas terrestres](docs/Primer%20analisis%20reproducible%20-%20Jezero%20y%20candidatas%20terrestres.md). `make analysis` lo repite con las entradas locales verificadas; `make test-analysis` ejecuta sus controles científicos mínimos. La aplicación ahora consume esos resultados revisados. Si cambia el método, la configuración o el entorno y se generan archivos distintos, revisa los resultados antes de emitir un nuevo manifiesto; la API no los adopta silenciosamente.

`pixi.toml` describe el entorno y `pixi.lock` fija las versiones resueltas para las plataformas compatibles. Comparte ambos archivos junto con `frontend/package-lock.json`; el script utiliza el lock de Pixi cuando está presente. Si aún no existe, la primera instalación lo crea y debe compartirse para reproducir esa resolución. Las plataformas previstas son macOS Intel y Apple Silicon y Linux x86-64; en Windows se necesita WSL.

Se han reservado `specs/`, `packages/analogos_core/`, `pipelines/`, `ml/` y `releases/` para la arquitectura propuesta. Los derivados locales pertenecen a `data/normalized/`, `data/features/` y `data/visual/`; estas carpetas, los datos crudos y los releases generados están excluidos de Git. Los datos y archivos del prototipo siguen en sus ubicaciones actuales. Los contratos científicos y el pipeline siguen pendientes de revisión e implementación.

## Despliegue en Azure

La [guía de CI/CD con Docker para una VM de Azure](docs/guia-ci-cd-azure-docker.md) describe la validación en pull requests y el despliegue automático a producción únicamente desde `main`, sin Nginx.
