# Fase 5 — expansión condicionada

**Estado:** implementada y verificada para un segundo escenario, el 7 de noviembre de 2026.  
**Resultado:** escenario de reconocimiento topográfico para examinar sensibilidad a fuente y escala en diez ventanas de fase 4: siete evaluadas y tres pendientes. Se conserva la línea base interpretable. No se certifican análogos ni movilidad.

## 1. Decisión sustentada en fase 4

La [fase 4](Fase%204%20-%20busqueda%20regional%20terrestre.md) produjo 970 ventanas y tres controles. Los tres controles quedaron fuera del perfil base a ambas escalas y solo una ventana nueva tenía detalle evaluado. El cambio de métricas entre GMTED a 300/600 m y SRTM a 60/120 m mezclaba cambios de producto y escala; no permitía atribuirlos por separado.

La expansión responde a una pregunta concreta: **¿se conservan las decisiones regionales al cambiar GMTED por SRTM a la misma escala, y cómo cambian los descriptores al examinar 60/120 m?** Sirve para preparar una revisión de reconocimiento topográfico antes de extender la evaluación local. No selecciona lugares seguros ni define aptitud de una misión.

La pregunta, fuentes, presupuesto, escalas y selección quedan en [estabilidad-topografica-v1.json](../../../specs/scenarios/estabilidad-topografica-v1.json). Los productos y condiciones documentales son los ya verificados en fases 2 y 4; no se introducen fuentes externas ni descargas adicionales.

## 2. Selección reproducible y sesgo de disponibilidad

Se conservan los tres controles y `utah-010-007`, el ancla con detalle de fase 4. Se añade una ventana generada aceptada y otra excluida por área según el perfil base a 300 m. Para cada estrato se prefieren ventanas cubiertas por una sola tesela SRTM local de identidad revisada; los empates se ordenan por SHA-256 de `fase5-v1:id`. La selección se realiza antes de calcular las nuevas métricas SRTM. El presupuesto de esta configuración es diez ventanas y el programa impone un techo de veinte.

| Área y decisión regional | Ventanas del estrato | Con tesela local revisada | Ventana seleccionada |
|---|---:|---:|---|
| Utah · aceptada | 99 | 40 | `utah-006-006` |
| Utah · excluida | 173 | 40 | `utah-007-005` |
| Mojave · aceptada | 128 | 0 | `mojave-010-013` |
| Mojave · excluida | 150 | 0 | `mojave-011-002` |
| Atacama · aceptada | 136 | 29 | `atacama-018-014` |
| Atacama · excluida | 284 | 71 | `atacama-013-011` |

Las siete ventanas de Utah y Atacama tienen evaluación exploratoria. Las dos ventanas generadas de Mojave y `control-mojave` conservan `pending_detail`, métricas locales y contrastes `null`, y las teselas pendientes explícitas. La fase 5 usa únicamente `N38W111.tif` y `S24W068.tif`, cuyas identidades constan en la configuración revisada de fase 2. Una tesela distinta presente en disco no se adopta automáticamente.

**Esta es una muestra de conveniencia estratificada**, favorecida por los datos locales y limitada a dos áreas con detalle. No es una muestra aleatoria del catálogo. No estima tasas de acierto, falsos positivos, falsos negativos ni sesgo global. Los controles contextuales tampoco son etiquetas verdaderas de analogía.

## 3. Método y comparabilidad

- Misma ventana de **3000 × 3000 m** y mismo centro que fase 4. La referencia HiRISE de Jezero se calcula de nuevo a cada escala; su cobertura es completa en las cuatro.
- SRTM se agrega a **60, 120, 300 y 600 m**, con margen de 600 m y bases de pendiente de 120, 240, 600 y 1200 m. Se reutilizan promedio espacial, máscara independiente de soporte completo, diferencias centrales, Wasserstein en grados y relieve p95−p5. No se comparan elevaciones absolutas entre cuerpos.
- A **300/600 m** se compara GMTED con SRTM usando la misma referencia. Se publica Wasserstein entre las pendientes terrestres de ambos productos y los cambios SRTM−GMTED en la distancia a Jezero y la diferencia de relieve. Estos cambios no son errores de medición ni incertidumbres calibradas.
- Los perfiles estricto/base/amplio de fase 4 se aplican solo a **300/600 m**. Se guardan motivos por producto y si cambia la decisión. A 60/120 m se muestran descriptores y diferencias sin extrapolar los filtros.
- Se requiere al menos **95 %** de cobertura por variable y referencia. Un contraste insuficiente produce valores comparativos y cambio de decisión `null`; no cuenta como cambio ni como mala semejanza. Se conservan conteos y descriptores para inspección.
- Se comprueba la identidad de la configuración de fuentes de fase 2, del catálogo y configuración de fase 4 y de los originales utilizados. La lectura directa del ArcGrid reproduce las métricas GMTED publicadas con tolerancia absoluta de 10⁻⁷, sin regenerar ni modificar fase 4.

GMTED y SRTM pueden compartir observaciones de origen. La comparación no constituye validación independiente ni aísla un sesgo de sensor: describe diferencias entre productos y procesamiento a escala común. Persisten límites de resolución efectiva, superficie radar, rellenos, referencias verticales heterogéneas y precisión local no cuantificada.

### Conservación de la cuadrícula nativa

En la verificación se observó que crear un mosaico SRTM con límites geográficos arbitrarios puede desplazar el origen de su cuadrícula e introducir pérdida de soporte en los bordes. Esta implementación lee ventanas de píxeles directamente de la tesela original y añade el margen necesario para 600 m. Una prueba con cuadrícula sintética comprueba origen, cero válido y cobertura completa de pendiente en las cuatro escalas.

El detalle publicado en fase 4 usaba `merge(bounds=...)` y se preserva íntegro. Por esta diferencia de procesamiento, las nuevas métricas finas del ancla no deben copiarse sobre aquella entrega ni confundirse con una repetición idéntica de su procedimiento. Para `utah-010-007`, fase 5 obtiene 1,024760° y −3,816283 m a 60 m, y 0,752652° y −4,181361 m a 120 m. El registro de fase 4 conserva sus valores anteriores y su trazabilidad.

## 4. Hallazgos de la muestra

En los **siete pares** con cobertura completa, se conservan las decisiones GMTED→SRTM para los tres perfiles a 300 y 600 m: **0 cambios de 7 pares** en cada una de las seis combinaciones. Las métricas sí cambian. La ausencia de cambios en esta muestra pequeña no calibra ni valida los umbrales.

| Ventana | Distancia SRTM a Jezero · 60 m | 120 m | 300 m | 600 m |
|---|---:|---:|---:|---:|
| `utah-010-007` | 1,025° | 0,753° | 0,388° | 0,389° |
| `utah-007-005` · excluida | 4,769° | 3,834° | 2,399° | 1,445° |
| `control-utah` | 2,916° | 2,533° | 1,809° | 1,668° |
| `atacama-018-014` · aceptada | 0,935° | 1,109° | 1,581° | 1,483° |

Para el ancla, el cambio de producto a 300 m modifica la distancia a Jezero en +0,060° y la diferencia de relieve en +3,324 m. A 600 m los cambios son −0,022° y +0,177 m. La sensibilidad de escala no tiene un sentido universal: algunas ventanas se acercan a la referencia al agregar y otras se alejan. La interfaz conserva las dos dimensiones por separado.

Los valores completos, coberturas, identidades, decisiones y estratos están en [resultados.json](../../evidencia-fase-5/resultados.json). El orden de ventanas es por identificador, sin clasificación conjunta de idoneidad.

## 5. Aplicación y API

En [la aplicación local](http://localhost:5173), abrir **«Reconocimiento · fuente y escala»**. Se puede elegir cualquiera de las diez ventanas, cambiar perfil, revisar los contrastes a escala común, las cuatro escalas SRTM, las fuentes, los estratos y las decisiones de expansión. Los pendientes se muestran sin tablas de valores inventados. Se mantienen los recorridos anteriores.

| Ruta | Contenido |
|---|---|
| `GET /api/scenarios` | Dos escenarios implementados, escalas y ruta del nuevo recorrido. |
| `GET /api/expansion` | Evidencia completa del nuevo escenario, recursos y enlaces a registros. |
| `GET /api/scenarios/estabilidad-topografica/comparison` | Mismo registro, con `reference_id=mars-jezero-fan` y `cell_m=60/120/300/600` validados; `cell_m` señala la escala solicitada y el registro conserva todas para inspección. |
| `GET /api/expansion/evidence/{filename}` | Lista cerrada: resultados, procesamiento y manifiesto. |

La API verifica identidades de resultados, procesamiento y configuraciones y su vínculo con el catálogo vigente de fase 4. Una evidencia ausente o distinta genera 503. No procesa rásteres, descarga ni sirve originales. Los hashes son identidad local; no autenticidad externa. La publicación sigue siendo atómica por archivo, sin transacción conjunta de la entrega.

## 6. Reproducción y verificación

Desde la raíz, con originales locales y entorno ya instalado:

```sh
./.pixi/envs/default/bin/python scripts/evaluar_expansion.py
./.pixi/envs/default/bin/python -m unittest discover -s tests -p test_evaluar_expansion.py -v
make check
./.pixi/envs/default/bin/python -m unittest discover -s tests -v
```

El programa no ofrece descargas. Los recortes regenerables se guardan en `data/normalized/fase5/`; los resultados publicados, en `docs/evidencia-fase-5/`. Requiere el catálogo y manifiestos previos revisados y las identidades de las entradas documentadas. Se conservan también `Makefile` y `pixi.toml`, incluidos en el manifiesto de fase 2; la expansión usa el entorno existente sin alterar esa identidad.

Se aprobaron **51 pruebas**: 23 de API y 28 de análisis/adquisición, incluidas doce nuevas de fase 5. Se verificaron TypeScript/Vite, selección determinista, controles y exclusiones, ceros válidos, soporte, límites de presupuesto, pendientes, ausencia de filtros finos, parámetros inválidos, archivos permitidos y rechazo de evidencia/configuración alteradas.

Dos ejecuciones completas consecutivas, con llamadas de red bloqueadas, produjeron el mismo SHA-256 de `resultados.json`: **`eb4d5e338787a93de422c03e504a9bd923f07f65bf9701f32adb1ec791b418fd`**. Se preservaron los **58 archivos** existentes de las carpetas de evidencia de fases 2 y 4. Véase [repetición e identidades previas](../../evidencia-fase-5/repeticion.json). El tiempo de procesamiento es variable y queda separado del resultado determinista.

El lote tarda unos segundos localmente y genera aproximadamente 0,21 MB de recortes SRTM para siete ventanas. No se extrapola a un barrido global ni se presenta como benchmark de memoria. La verificación de interfaz y los recursos medidos de la entrega están en [evidencia de fase 5](../../evidencia-fase-5/README.md).

## 7. Decisiones condicionadas y salida

Se incorpora **un escenario adicional** porque tiene pregunta explícita, fuentes utilizables, método de evaluación y ejecución reproducible. No se necesita añadir una dimensión física o un cuerpo para cumplir la expansión condicionada.

- **ML: pospuesto.** No hay etiquetas independientes, separación geográfica de evaluación ni evidencia de mejora sobre la línea base. Antes de entrenar se requiere un protocolo que evalúe sesgos de producto, escala y geografía; esta muestra no satisface esas condiciones.
- **Luna y regiones polares: pospuestas.** La descarga de LOLA o archivos polares no establece por sí sola una pregunta, cobertura local y comparabilidad utilizables.
- **Infraestructura distribuida: pospuesta.** Los aproximadamente 9,3 s medidos en fase 4 para 970 ventanas y el coste acotado de esta evaluación no demuestran esa necesidad. No se añade infraestructura sin un cuello de botella medido.

El criterio de salida de esta entrega es un segundo escenario seleccionable, reproducible y trazable, con contraste a escala común, sesgo de disponibilidad visible, pendientes explícitos y decisiones de expansión justificadas. Se cumple en este dominio; la validación física independiente y la extensión a otras fuentes o cuerpos permanecen abiertas.
