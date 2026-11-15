# Documentación del Atlas de Análogos Planetarios

> **Etapa actual del proyecto (al 12 de noviembre de 2026):** **Etapa 3 — Armonización científica y contrato común multi-instrumento** (`contrato-comun-superficie-v1` y `consulta-bajo-demanda-v1`), construida sobre el Atlas de 30 m tras la revisión metodológica.

---

## Cómo navegar esta carpeta

La documentación está organizada por **vigencia y etapa** para distinguir rápidamente qué es válido hoy, qué corresponde a entregas anteriores ya completadas y qué quedó obsoleto:

| Directorio | Qué contiene | Cuándo consultarlo |
|---|---|---|
| [`01-vigentes/`](01-vigentes/) | **Documentos válidos actuales**: visión AS-IS/TO-BE, catálogo de datos, revisión metodológica, guías operativas y entregas de la **Etapa 3 (actual)**. | Siempre que trabajes en el estado actual del proyecto, operación del atlas o metodología científica vigente. |
| [`02-versiones-anteriores/`](02-versiones-anteriores/) | **Etapas 1 y 2 completadas** (6–8 nov 2026): MVP por escenarios (Fases 1–5), refactor frontend, extensión multidimensional y minerales EMIT. | Para trazabilidad técnica, contexto de cómo se construyó el MVP o reproducir entregas anteriores. |
| [`03-obsoletos-e-historico/`](03-obsoletos-e-historico/) | **Propuestas iniciales e instrucciones puntuales superadas** (4–5 nov 2026): visión inicial, prototipo pre-escenarios, arquitecturas preliminares y auditoría inicial. | Solo como archivo histórico; **no usar como referencia operativa ni arquitectónica**. |
| `evidencia-*`, `exploracion-*`, `investigacion-*` | Artefactos, manifiestos, métricas JSON y figuras generadas por los análisis reproducibles. | Se conservan en la raíz de `docs/` para mantener intactas las rutas usadas por `scripts/`, `specs/` y `tests/`. |

---

## 1. Documentos vigentes (`01-vigentes/`)

### 1.1 Arquitectura, visión y diccionario de datos (`01-vigentes/arquitectura-y-vision/`)

| Documento | Fecha / Estado | Rol |
|---|---|---|
| [Atlas_de_Analogos_Planetarios_AS_IS_TO_BE.md](01-vigentes/arquitectura-y-vision/Atlas_de_Analogos_Planetarios_AS_IS_TO_BE.md) | 9 nov 2026 · **Vigente** (propuesta v1.0) | Documento marco AS-IS / TO-BE y estrategia de búsqueda global. |
| [Atlas - catalogo y diccionario de datos.md](01-vigentes/arquitectura-y-vision/Atlas%20-%20catalogo%20y%20diccionario%20de%20datos.md) | 9 nov 2026 · **Vigente** | Inventario oficial de productos, escalas, CRS, máscaras y variables. |
| [revision-metodologica-atlas-30-m.md](01-vigentes/arquitectura-y-vision/revision-metodologica-atlas-30-m.md) | **Vigente** | Revisión crítica del Atlas de 30 m que define los controles de comparabilidad (origen de la Etapa 3). |

### 1.2 Operación y adquisición de datos (`01-vigentes/operacion-y-datos/`)

| Documento | Estado | Rol |
|---|---|---|
| [Atlas de 30 m - operacion.md](01-vigentes/operacion-y-datos/Atlas%20de%2030%20m%20-%20operacion.md) | **Vigente** | Operación de `/?view=world`, publicación `mundial-30m-r1` (3.782 ventanas) y reanudación. |
| [Barrido mundial - robustez cobertura costo y publicacion.md](01-vigentes/operacion-y-datos/Barrido%20mundial%20-%20robustez%20cobertura%20costo%20y%20publicacion.md) | **Vigente** · 14 nov 2026 | Fallos con causa, reanudación por identidad, relleno de cobertura, benchmark ([`evidencia-barrido/`](evidencia-barrido/)) y publicación del ETL al mapa. |
| [Atlas de 30 m - preparacion multidimensional.md](01-vigentes/operacion-y-datos/Atlas%20de%2030%20m%20-%20preparacion%20multidimensional.md) | **Vigente** | Preparación reproducible de WorldCover, JRC, HLS y Landsat. |
| [Guia de recoleccion.md](01-vigentes/operacion-y-datos/Guia%20de%20recoleccion.md) | **Vigente** | Uso actual de `scripts/recolectar_datos.py` y recuperación de descargas. |
| [Adquisicion CRISM de Marte.md](01-vigentes/operacion-y-datos/Adquisicion%20CRISM%20de%20Marte.md) | **Vigente** | Uso de `scripts/adquirir_marte.py` y adquisición CRISM `FRT000047A3`. |
| [Plan - busqueda de analogos por referencia en tiempo real.md](01-vigentes/operacion-y-datos/Plan%20-%20busqueda%20de%20analogos%20por%20referencia%20en%20tiempo%20real.md) | **Propuesta** · 15 nov 2026 | Plan por fases: motor residente, espejo de datos, catálogo de referencias lunares y marcianas, API y frontend. |

### 1.3 Etapa actual: Armonización y contrato común (`01-vigentes/etapa-actual-armonizacion/`)

| Documento | Fecha / Estado | Evidencia asociada |
|---|---|---|
| [Primera entrega - exploracion de fuentes y preguntas cientificas.md](01-vigentes/etapa-actual-armonizacion/Primera%20entrega%20-%20exploracion%20de%20fuentes%20y%20preguntas%20cientificas.md) | 10 nov 2026 · **Vigente** | [`exploracion-fuentes-v1/`](exploracion-fuentes-v1/) |
| [Plan y experimento de armonizacion topografica en Utah.md](01-vigentes/etapa-actual-armonizacion/Plan%20y%20experimento%20de%20armonizacion%20topografica%20en%20Utah.md) | 11 nov 2026 · **Vigente** | [`evidencia-armonizacion-utah/`](evidencia-armonizacion-utah/) |
| [Validacion de armonizacion topografica en desierto bosque y costa.md](01-vigentes/etapa-actual-armonizacion/Validacion%20de%20armonizacion%20topografica%20en%20desierto%20bosque%20y%20costa.md) | 11 nov 2026 · **Vigente** | [`evidencia-validacion-topografica/`](evidencia-validacion-topografica/) |
| [Plan de armonizacion de las dimensiones de superficie.md](01-vigentes/etapa-actual-armonizacion/Plan%20de%20armonizacion%20de%20las%20dimensiones%20de%20superficie.md) | 11 nov 2026 · **Vigente** | [`evidencia-armonizacion-superficie/`](evidencia-armonizacion-superficie/) |
| [Tercera entrega - muestreo estratificado y puentes entre cuerpos.md](01-vigentes/etapa-actual-armonizacion/Tercera%20entrega%20-%20muestreo%20estratificado%20y%20puentes%20entre%20cuerpos.md) | **Vigente (última entrega)** | [`evidencia-entrega-3/`](evidencia-entrega-3/) |
| [Contraste de fuentes del challenge 2026](01-vigentes/etapa-actual-armonizacion/Contraste%20de%20fuentes%20del%20challenge%202026.md) | 12 nov 2026 · Investigación | Fuentes oficiales, encaje con el ETL y propuesta de piloto lunar-terrestre. |
| [Elección de fuentes y costo de cobertura mundial](01-vigentes/etapa-actual-armonizacion/Eleccion%20de%20fuentes%20y%20costo%20de%20cobertura%20mundial.md) | 13 nov 2026 · Evaluación | Validez de GLO‑30 y las características, enriquecimientos y presupuesto de procesamiento. |
| [Auditoría de armonización y features frente a fuentes del challenge](01-vigentes/etapa-actual-armonizacion/Auditoria%20de%20armonizacion%20y%20features%20frente%20a%20fuentes%20del%20challenge.md) | 14 nov 2026 · Auditoría | Vacíos de método, features propuestas y prioridades; compuerta por escenario implementada. |
| [Descriptores de forma y redundancia del vector topográfico](01-vigentes/etapa-actual-armonizacion/Descriptores%20de%20forma%20y%20redundancia%20del%20vector%20topografico.md) | 14 nov 2026 · **Vigente** | [`evidencia-descriptores-forma/`](evidencia-descriptores-forma/) |
| [Puente espectral con un solo operador en tres cuerpos](01-vigentes/etapa-actual-armonizacion/Puente%20espectral%20con%20un%20solo%20operador%20en%20tres%20cuerpos.md) | 14 nov 2026 · **Vigente** | [`evidencia-puente-espectral/`](evidencia-puente-espectral/) |
| [Puentes láser y radar polarimétrico](01-vigentes/etapa-actual-armonizacion/Puentes%20laser%20y%20radar%20polarimetrico.md) | 14 nov 2026 · **Vigente** | [`evidencia-puentes-laser-radar/`](evidencia-puentes-laser-radar/) |

---

## 2. Versiones anteriores completadas (`02-versiones-anteriores/`)

Documentos de iteraciones previas ya implementadas y verificadas. Conservan valor como registro técnico, pero el análisis y los contratos actuales están en `01-vigentes/`.

### 2.1 Etapa 1: MVP orientado a escenarios — Fases 1–5 y frontend (`02-versiones-anteriores/etapa-1-mvp-escenarios/`)

| Documento | Fecha / Estado | Evidencia asociada |
|---|---|---|
| [Plan de implementacion orientado a escenarios.md](02-versiones-anteriores/etapa-1-mvp-escenarios/Plan%20de%20implementacion%20orientado%20a%20escenarios.md) | 6 nov 2026 · Completado (plan de Etapa 1) | — |
| [Ficha de viabilidad - primer caso.md](02-versiones-anteriores/etapa-1-mvp-escenarios/Ficha%20de%20viabilidad%20-%20primer%20caso.md) | 6 nov 2026 · Fase 1 completada | [`evidencia-fase-1/`](evidencia-fase-1/) |
| [Primer analisis reproducible - Jezero y candidatas terrestres.md](02-versiones-anteriores/etapa-1-mvp-escenarios/Primer%20analisis%20reproducible%20-%20Jezero%20y%20candidatas%20terrestres.md) | Fase 2 completada | [`evidencia-fase-2/`](evidencia-fase-2/) |
| [Fase 3 - recorrido minimo en la aplicacion.md](02-versiones-anteriores/etapa-1-mvp-escenarios/Fase%203%20-%20recorrido%20minimo%20en%20la%20aplicacion.md) | 7 nov 2026 · Fase 3 completada | [`evidencia-fase-3/`](evidencia-fase-3/) |
| [Fase 4 - busqueda regional terrestre.md](02-versiones-anteriores/etapa-1-mvp-escenarios/Fase%204%20-%20busqueda%20regional%20terrestre.md) | 7 nov 2026 · Fase 4 completada | [`evidencia-fase-4/`](evidencia-fase-4/) |
| [Fase 5 - expansion condicionada.md](02-versiones-anteriores/etapa-1-mvp-escenarios/Fase%205%20-%20expansion%20condicionada.md) | 7 nov 2026 · Fase 5 completada | [`evidencia-fase-5/`](evidencia-fase-5/) |
| [Plan de refactorizacion visual del frontend.md](02-versiones-anteriores/etapa-1-mvp-escenarios/Plan%20de%20refactorizacion%20visual%20del%20frontend.md) | 7 nov 2026 · Etapas A–E hechas (F pendiente) | — |
| [Refactor frontend - entrega.md](02-versiones-anteriores/etapa-1-mvp-escenarios/Refactor%20frontend%20-%20entrega.md) | 7 nov 2026 · Entregado | [`evidencia-refactor-frontend/`](evidencia-refactor-frontend/) |
| [Guia para entender el atlas.md](02-versiones-anteriores/etapa-1-mvp-escenarios/Guia%20para%20entender%20el%20atlas.md) | 7 nov 2026 · Guía de las fases 1–5 | — |

### 2.2 Etapa 2: Extensión multidimensional y minerales EMIT (`02-versiones-anteriores/etapa-2-multidimensional-emit/`)

| Documento | Fecha / Estado | Evidencia asociada |
|---|---|---|
| [Fuentes para ampliar las dimensiones del atlas.md](02-versiones-anteriores/etapa-2-multidimensional-emit/Fuentes%20para%20ampliar%20las%20dimensiones%20del%20atlas.md) | 7 nov 2026 · Investigación previa | [`investigacion-dimensiones/`](investigacion-dimensiones/) |
| [Extension multidimensional.md](02-versiones-anteriores/etapa-2-multidimensional-emit/Extension%20multidimensional.md) | Completada (`/?view=dimensions`) | [`evidencia-dimensiones/`](evidencia-dimensiones/) |
| [Minerales EMIT - entrega.md](02-versiones-anteriores/etapa-2-multidimensional-emit/Minerales%20EMIT%20-%20entrega.md) | 8 nov 2026 · Entregado | [`evidencia-minerales/`](evidencia-minerales/), [`investigacion-marte/`](investigacion-marte/), [`evidencia-crism/`](evidencia-crism/) |

---

## 3. Documentos obsoletos e histórico inicial (`03-obsoletos-e-historico/`)

Documentos de arranque (4–5 nov 2026) reemplazados por el enfoque orientado a escenarios, el Atlas AS-IS/TO-BE o las guías operativas actuales:

| Documento | Fecha | Por qué está obsoleto / qué lo reemplaza |
|---|---|---|
| [Documento Visión.md](03-obsoletos-e-historico/Documento%20Visi%C3%B3n.md) | Inicial | Visión preliminar ("Nombre del proyecto: Por definir"), reemplazada por [AS-IS / TO-BE](01-vigentes/arquitectura-y-vision/Atlas_de_Analogos_Planetarios_AS_IS_TO_BE.md). |
| [Arquitectura y estrategia de implementacion.md](03-obsoletos-e-historico/Arquitectura%20y%20estrategia%20de%20implementacion.md) | Inicial | Propuesta técnica inicial pre-prototipo, superada por las iteraciones posteriores. |
| [Investigacion de fuentes de datos y cruces.md](03-obsoletos-e-historico/Investigacion%20de%20fuentes%20de%20datos%20y%20cruces.md) | 4 nov 2026 | Inventario preliminar, reemplazado por [Atlas - catálogo y diccionario de datos](01-vigentes/arquitectura-y-vision/Atlas%20-%20catalogo%20y%20diccionario%20de%20datos.md). |
| [Plan Prototipo.md](03-obsoletos-e-historico/Plan%20Prototipo.md) | Inicial | Plan de prueba de concepto inicial (CesiumJS/FastAPI), superado tras el diagnóstico. |
| [Diagnostico y arquitectura despues del prototipo.md](03-obsoletos-e-historico/Diagnostico%20y%20arquitectura%20despues%20del%20prototipo.md) | 5 nov 2026 | Diagnóstico de la prueba de concepto inicial. |
| [Arquitectura objetivo y plataforma de datos.md](03-obsoletos-e-historico/Arquitectura%20objetivo%20y%20plataforma%20de%20datos.md) | 5 nov 2026 | Propuesta teórica a largo plazo, reemplazada por [AS-IS / TO-BE](01-vigentes/arquitectura-y-vision/Atlas_de_Analogos_Planetarios_AS_IS_TO_BE.md). |
| [Arquitectura para el hackathon.md](03-obsoletos-e-historico/Arquitectura%20para%20el%20hackathon.md) | 5 nov 2026 | Propuesta de escala reducida previa al plan por escenarios. |
| [Plan de arranque desde cero.md](03-obsoletos-e-historico/Plan%20de%20arranque%20desde%20cero.md) | 5 nov 2026 | Reemplazado explícitamente por [Plan de implementacion orientado a escenarios.md](02-versiones-anteriores/etapa-1-mvp-escenarios/Plan%20de%20implementacion%20orientado%20a%20escenarios.md). |
| [Siguiente accion - auditoria de datos.md](03-obsoletos-e-historico/Siguiente%20accion%20-%20auditoria%20de%20datos.md) | 5 nov 2026 | Instrucción puntual ya ejecutada para auditar `data/raw/`. |
| [Auditoria de datos locales.md](03-obsoletos-e-historico/Auditoria%20de%20datos%20locales.md) | 5 nov 2026 | Foto histórica de `mola/` y `srtm/` al 5 nov; reemplazada por el catálogo del 9 nov. |
| [Plan de recoleccion de datos.md](03-obsoletos-e-historico/Plan%20de%20recoleccion%20de%20datos.md) | 5 nov 2026 | Plan preliminar de descarga, reemplazado por [Guia de recoleccion.md](01-vigentes/operacion-y-datos/Guia%20de%20recoleccion.md) y [preparación multidimensional](01-vigentes/operacion-y-datos/Atlas%20de%2030%20m%20-%20preparacion%20multidimensional.md). |
