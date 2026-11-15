# Simulador geoespacial: uso y estado de integración

La interfaz organiza el atlas en **Explorar → Simular similitud → Comparar → Revisar sensibilidad**. La referencia, `regionId`, publicación, método, pesos del atlas, destino local, modo de superficie y exageración se conservan en enlaces y en el historial del navegador.

## Ejecutar y probar

Desde la raíz del repositorio:

```sh
npm --prefix frontend ci
npm --prefix frontend run dev
```

Para los recorridos que consumen evidencia revisada, inicia la API existente en otra terminal:

```sh
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

La alternativa gestionada por el proyecto es `make backend` con el entorno Pixi instalado. El visor y las demostraciones estáticas funcionan sin procesamiento científico nuevo.

1. Abre `http://127.0.0.1:5173/`. Jezero es la referencia inicial. Explora **Relieve regional** y **Superficie local**. En la malla, comprueba norte, lados de 1.800 m, mínimos/máximos, leyenda y el corte central A–B. La altura empieza en 1×; el factor se conserva al navegar y se restablece al cambiar de destino.
2. Pulsa **Simular similitud**. Cuando la API no tiene resultados publicados, aparece **Demostración precalculada / Motor experimental**. Los archivos son copias exactas de la evidencia del repositorio, con hashes en `/analysis/simulation/provenance.json`.
3. Selecciona la **candidata 4 de Jezero** en la lista (29,181°, 5,160°; `utm-ups-v1-10000-32631-323-71`). A diferencia de otras filas del ejemplo, figura como elegible para el perfil árido. El ranking conserva también las candidatas excluidas y sus motivos, tal como las entrega la búsqueda original.
4. Pulsa **Comparar con la referencia**. Se conservan referencia, ID y procedencia. La tabla alinea unidades, muestra valores originales, diferencias y contribuciones con signo. El mapa muestra contexto satelital de la candidata; el ejemplo no incluye un DEM local suyo.
5. Pulsa **Revisar sensibilidad**. Verás pesos solicitados/efectivos y los motivos de dimensiones deshabilitadas. La consulta personalizada todavía no existe: no se inventan cambios de puesto o distancia.
6. Abre **Controles locales · 1,8 km**, compara Jezero–Utah o Jezero–Atacama a 60/120 m y pasa a sensibilidad: la misma candidata conserva su selección y permite revisar los cambios medidos. Desde allí se puede abrir la muestra ampliada GMTED/SRTM de 3 km; se identifica como otro experimento.
7. Prueba Haworth desde el selector de referencia. Tiene otro ejemplo. De Gerlache muestra explícitamente la ausencia de ranking y de DEM para el navegador.
8. En **Simular similitud → Atlas a 30 m** se conservan las rutas y el método topográfico existentes. Sin release local activa aparece el mensaje de la API. Con release, `region_id` conecta resultados, ficha, comparación y expediente de sensibilidad; las columnas ambientales ausentes conservan estados explícitos.

Ejemplo de enlace reproducible del motor:

```text
/?view=compare&method=engine&reference=jezero&regionId=utm-ups-v1-10000-32631-323-71&engineSource=demo
```

Los enlaces históricos `?view=compare` siguen abriendo la evidencia local. En los nuevos enlaces se serializa `method=engine` para evitar confundir ambos métodos. `view=world`, `view=dimensions`, `view=explore` y `view=sensitivity` siguen disponibles con sus herramientas existentes.

## Qué existe realmente

Inspección de `backend/app/routers/*`, `/openapi.json` y disco local:

| Fuente | Estado verificado | Uso en la interfaz |
|---|---|---|
| `/api/scenarios/relieve-regional/comparison`, `/api/multidimensional`, `/api/minerals`, `/api/expansion`, `/api/regional-search` | Implementadas; evidencia revisada local disponible | Comparación, dimensiones, muestreo y sensibilidad de controles |
| `/api/atlas`, `/versions`, `/coverage`, `/search`, `/candidates/{region_id}` y `terrain.png` | Implementadas; no hay `releases/atlas30/` activo en este entorno | Integración del atlas y estados de publicación ausente |
| `/api/atlas/similarity/{reference}` | No implementada actualmente | Se comprueba y se usa si devuelve una respuesta válida; 404/5xx o falta de conexión permiten la demostración explícita |
| `POST /api/similarity/search` | Propuesta en la guía; ausente del backend | Pesos y escenario ajustado deshabilitados con explicación |
| `docs/evidencia-motor-similitud/busqueda-jezero.json` y `busqueda-haworth.json` | Disponibles; diez resultados cada una | Demostraciones, sin vincularlas a una release del atlas |
| Capas ambientales `*_cmg` | Contrato estable; su presencia depende de la publicación | Valor solo si el estado es `measured`; pendientes, fuera de cobertura y nulos se explican |

La adaptación del formato antiguo añade `coverage_fraction` solo cuando puede calcularse a partir del número de candidatas con vista y la población informada. Conserva el orden, los scores, los avisos, las ausencias y la elegibilidad. Una respuesta válida tiene que confirmar la referencia y la versión solicitadas; una respuesta científica inválida no se sustituye silenciosamente.

Una distancia menor significa mayor parecido en `motor-busqueda-v1`. El intervalo refleja dimensiones ausentes, no un intervalo de confianza estadístico. La cobertura es del peso efectivo, no de todas las dimensiones solicitadas. Las contribuciones pueden ser negativas o superar 100 % por correlación. El motor continúa pendiente de validación a ciegas.

## Escala y relieve

El problema regional tenía tres componentes: la textura global ampliada no aportaba detalle local, el MOLA global tenía separación de muestras de ~14,8 km y las teselas CTX en vivo podían fallar. El sistema de coordenadas de las mallas se mantiene en este/norte/arriba, en metros. Los PNG usan su calibración declarada y conservan huecos.

- Jezero regional utiliza un recorte CTX georreferenciado de nueve teselas nivel 8, preparado para el navegador. Su extensión exacta es `[76.640625, 17.578125, 78.75, 19.6875]` grados. Tiene 1.536 × 1.536 píxeles, ~81,4 m/píxel en el ecuador; es un derivado remuestreado de un mosaico no controlado, sin precisión posicional local afirmada. Fuera de ese recorte se mantiene la textura global gruesa.
- El terreno regional MOLA existente utiliza radios sobre la esfera de 3.396.000 m y muestras de ~463 m en la zona de Jezero, con interpolaciones. La textura y la malla no adquieren la misma resolución por mostrarse juntas.
- La Tierra usa imagen y elevación públicas de Esri, de resolución variable. Los fallos de conexión son visibles. El mapa de candidatas del motor presenta imagen de contexto y no afirma tener un DEM local de cada resultado.
- Los controles locales usan ventanas de 1,8 km. Espaciado visual: 18,75 m en Jezero, 30 m en Utah/Atacama. El panel de fuentes conserva el espaciado nativo, versión, periodo y datum de la evidencia original.
- El corte A–B y la malla leen el mismo PNG, la misma fila central y el mismo espaciado. El perfil mantiene las alturas originales y avisa de sus ejes de distinta escala. La malla resta la mediana como origen de visualización; su exageración no modifica las mediciones.
- Las imágenes de color de altura y los relieves sombreados son derivados del DEM. Cesium, sus workers y los mapas se cargan de forma diferida.

Preparación repetible de los recursos nuevos, desde la raíz:

```sh
node frontend/scripts/sync-evidence.mjs
.venv/bin/python frontend/scripts/prepare-regional-preview.py
```

El primer comando copia evidencia existente y genera sus metadatos. El segundo descarga solo nueve teselas CTX de contexto, no originales científicos. Sus URLs y hashes quedan en `/analysis/surface/regional-preview.json`.

## Verificación

```sh
npm --prefix frontend test
npm --prefix frontend run build
cd frontend
./node_modules/.bin/vite preview --host 127.0.0.1 --port 4174
```

Las pruebas cubren enlaces y compatibilidad histórica, identidad de referencia/release, adaptación del motor, fallos/ausencia de servicio, valores nulos, distancias pequeñas, orientación y huecos de la malla, perfil central y huella geográfica del recorte CTX. La revisión manual en Safari incluye el flujo Jezero → candidata 4 → comparación → sensibilidad, cambio a Haworth, referencia sin ejemplo, terreno regional y perfil local, y comparación apilada a 390 × 844 px. La demostración explícita permite repetir el recorrido aunque no haya servicio de similitud.

Limitaciones pendientes: publicar una release local del atlas, servir similitud precalculada desde el backend, incorporar el endpoint de pesos personalizados y publicar DEMs/imágenes/otras resoluciones para las candidatas del motor y las referencias lunares. No se cambió el backend ni se ejecutaron nuevos análisis científicos para cubrir esas ausencias.

El build copia los recursos nuevos al namespace `/analysis/surface` y `/analysis/simulation`, que el backend existente ya sirve. Vite resuelve ese mismo namespace en desarrollo. Así el bundle también puede abrirse desde `http://127.0.0.1:8000/` sin añadir rutas al backend.

Resultado final de esta entrega: **29 pruebas del frontend aprobadas**, `tsc -b` y build de Vite correctos. Se verificó en navegador el bundle desde Vite Preview y desde FastAPI en un proceso de comprobación en `127.0.0.1:8001`, además del servidor de desarrollo en `5173`. Los recursos de demostración y CTX respondieron HTTP 200 bajo `/analysis/`. El atlas sin publicación devolvió su estado explícito de ausencia de release.
