# Plan de refactorización visual del frontend

Fecha: 7 de noviembre de 2026. Estado: **etapas A–E implementadas; validación con personas de la etapa F pendiente**. Consulta la [entrega, comprobaciones y capturas](Refactor%20frontend%20-%20entrega.md). Acompaña a la [guía de conceptos](Guia%20para%20entender%20el%20atlas.md). Las secciones siguientes conservan el diseño propuesto como referencia; la ficha de entrega registra su alcance final.

## 1. Resultado que queremos conseguir

Al abrir el atlas, una persona debe reconocer qué parte de Marte se compara con qué parte de la Tierra, en qué se parecen, en qué difieren y qué falta medir. Debe poder cambiar una candidata o una condición y ver inmediatamente el efecto.

La pantalla inicial será una **mesa de comparación visual**. Jezero permanece a la izquierda; la candidata terrestre, a la derecha. Debajo aparecen dos comparaciones pequeñas con unidades: pendientes y relieve. El método y la procedencia se consultan bajo demanda. La primera tarea del usuario será mirar el terreno y comparar; no interpretar un catálogo de términos.

Objetivo propuesto para la validación: en 10 segundos reconocer el par y las dos variables; en 30 segundos explicar una semejanza y una diferencia sin ayuda técnica. Estos tiempos son criterios de diseño, todavía no resultados medidos.

## 2. Diagnóstico basado en el código y las capturas existentes

| Problema observado | Dónde aparece | Cambio propuesto |
|---|---|---|
| Cabecera e introducción grandes antes del resultado | `App.tsx`, `.intro` en `style.css`; captura de fase 5 | Cabecera compacta con pregunta activa; resultado en el primer viewport de escritorio |
| Navegación sigue la historia de implementación | «Primer caso», «Ampliar búsqueda», «Reconocimiento» | Acciones del usuario: «Comparar lugares», «Explorar zonas», «Ver qué cambia» |
| Los dos paneles visuales quedan después de tablas y explicaciones | `App.tsx`: tabla → distribución → sensibilidad → `.worlds` | Llevar el par de vistas al comienzo y vincularlo a las métricas |
| Globos ocultos y separados de la lectura principal | `ContextGlobe.tsx`, desplegables en App y RegionalSearch | Ubicación accesible junto al par; contexto visible compacto, detalle analítico como vista principal |
| Texturas globales pueden parecer evidencia de detalle | Globo con SingleTileImageryProvider; sin proveedor de alturas del análisis | Rótulo «Ubicación»; separar claramente del modo «Terreno medido» |
| Colores ajustados por panel impiden una comparación inmediata | `SitePanel` y figuras PNG precalculadas | Nuevas capas visuales con leyenda común, unidades, huella y celda visibles |
| Muchos valores y términos requieren lectura previa | Wasserstein, p95−p5, deltas y bases de pendiente | Etiqueta corriente + representación visual + nombre técnico en detalle |
| La búsqueda se presenta como tabla paginada sin panorama espacial | `RegionalSearch.tsx` | Mapa con todas las huellas de la consulta y lista sincronizada |
| Fuente y escala se explican mediante varias tablas | `Expansion.tsx` | Separar dos preguntas visuales: cambiar producto a escala fija; cambiar escala con producto fijo |
| Selección y controles viven en cada vista | Estados locales de los tres componentes principales | Contexto de análisis explícito y restaurable; transición consciente entre experimentos |
| Hay tipos, formateo, peticiones y estilos repetidos | Tipos en tres TSX; `style.css` con reglas acumuladas | Adaptadores de datos, componentes compartidos, estilos con alcance y tokens |

Es un problema de jerarquía y de interacción, además de vocabulario. Acortar párrafos sin cambiar la composición no cumple el objetivo.

## 3. Qué verá la persona

### A. Comparar lugares: pantalla inicial

```text
ATLAS       Comparar lugares | Explorar zonas | Ver qué cambia
Jezero ↔ Utah                  Ventana 1,8 km · celda 60 m

Candidatas: [Utah] [Atacama]       Capa: [Pendiente] [Altura relativa]

┌───────────────────────┐      ┌───────────────────────┐
│ JEZERO · MARTE         │      │ UTAH · TIERRA          │
│ terreno medido         │      │ terreno medido         │
│ escala / norte / celda  │      │ escala / norte / celda  │
└───────────────────────┘      └───────────────────────┘
                Leyenda común de la capa activa

Pendientes   [distribuciones comparadas]  Diferencia: 1,46°
Relieve      [dos barras en metros]      54,6 m ↔ 27,4 m

Utah: pendientes más cercanas entre estas dos candidatas;
relieve aproximadamente a la mitad.                  [Ver por qué]

Celda: 60 ━━━━━● 120 m          Ubicación | Fuentes y método
Medido: pendiente, relieve. Pendiente: materiales, térmica, rocas…
```

La maqueta adjunta a la conversación usa valores y cuadrículas reales de fase 2. Prueba candidata, capa y celda; representa la dirección propuesta y no es una aplicación conectada al backend.

- Inicio ya resuelto: Jezero, Utah y 60 m; omitir selectores de una sola opción.
- Cambiar candidata actualiza la vista terrestre, métricas y frase breve en una sola operación.
- Pendiente se muestra con colores comunes de grados. Altura relativa usa elevación menos mediana de cada ventana y una escala común en metros; el relieve p95−p5 sigue siendo una métrica distinta.
- Gráfico de pendientes: curva acumulada de los intervalos disponibles, con una etiqueta que explique qué fracción queda por debajo de cada valor. No usar anchos desiguales de histograma como si fuesen bins equivalentes.
- Relieve: barras con origen cero, eje en metros y valores directos. La diferencia firmada queda al lado.
- La vista conserva distribución y relieve aunque se dé énfasis a una de ellas.
- Frases derivadas de reglas explícitas: «más cercana entre estas dos», «menor relieve», etc. Evitar «bueno», «seguro» o categorías de calidad no calibradas.

### B. Explorar zonas: mapa y resultados coordinados

Mapa terrestre con huellas reales de ventanas de 3 km; lista compacta al lado. Seleccionar una huella selecciona su ficha y viceversa. Los espacios entre ventanas permanecen visiblemente sin estudiar; no colorear una región entera por sus muestras.

Controles: área, celda regional 300/600 m, perfil y «Mostrar fuera del filtro». Por defecto, Utah, 300 m y perfil base. Un control de tres posiciones permite pasar de estricto a amplio y muestra las dos condiciones numéricas activas. Es un filtro sobre resultados guardados.

Estados que se representan por separado:

| Eje | Estados | Codificación |
|---|---|---|
| Filtro | Cumple / fuera / evidencia insuficiente | Forma y etiqueta; color complementario |
| Evaluación local | Disponible / pendiente / cobertura insuficiente | Insignia de texto en lista y ficha |
| Selección | Activa / no activa | Contorno o foco, sin cambiar el significado del filtro |

Conteos con denominador: «99 de 272 ventanas cumplen este perfil» para Utah/base/300 m. Mantener visibles los tres controles contextuales aunque queden fuera; distinguirlos de las 970 ventanas nuevas.

Al seleccionar una ventana: ficha con nombre comprensible («Utah · zona 010/007»), ID secundario, ubicación, medidas regionales y estado local. Si solo existe medida regional, mostrar su huella y los gráficos numéricos disponibles. No simular una imagen de detalle que el backend no sirve.

### C. Ver qué cambia: dos comparaciones controladas

1. **Cambiar los datos:** misma ventana, celda regional fija y referencia fija. Comparar GMTED ↔ SRTM, mostrar las métricas de cada producto y «Cumple → Cumple» u otra transición real. El resumen de la muestra indica «0 de 7 decisiones cambiaron · 3 ventanas pendientes» con perfil y escala explícitos.
2. **Cambiar el tamaño de celda:** mantener SRTM y ventana de 3 km. Mostrar dos gráficos alineados para 60/120/300/600 m: distancia de pendientes y diferencia de relieve. No interpolar resultados científicos entre esos cuatro puntos.

El eje de celda conserva proporciones o se presenta como selector categórico explícito; no dibujar cuatro puntos equidistantes en un eje numérico engañoso. Los filtros se aplican solo a 300/600 m. A 60/120 m se muestran medidas sin indicador de aprobado.

La muestra es de diez ventanas. Una ventana pendiente abre un estado útil: ubicación y datos regionales disponibles, más «Falta evaluación con SRTM». No una tabla llena de ceros.

## 4. Recuperar controles con significado

### Primera entrega: interacción compatible con el método actual

| Control | Acción real | Restricción visible |
|---|---|---|
| Candidata | Cambia la ventana terrestre activa | Conserva referencia y experimento |
| Capa | Cambia la variable espacial mostrada | Misma leyenda para ambos sitios |
| Celda | Selecciona uno de los análisis existentes | 60/120 en primer caso; 300/600 regional; cuatro escalas en sensibilidad |
| Perfil de tolerancia | Cambia estricto/base/amplio con dos umbrales visibles | Tres posiciones discretas; sin valores intermedios inventados |
| «Ordenar por pendientes / relieve» | Ordena por distancia de pendientes o por valor absoluto de la diferencia de relieve | No mezcla unidades ni cambia los datos |
| «Dar énfasis a…» | Cambia el gráfico y la explicación destacados | Es presentación; no altera la puntuación ni el filtro |

La ordenación por relieve se hará sobre **todo el conjunto filtrado**, no sobre doce filas de la página. Para el primer caso puede ser local; para búsqueda regional requiere una ampliación pequeña del endpoint o cargar el conjunto completo dentro del límite actual medido.

### Pesos de importancia: segunda entrega opcional, con método nuevo explícito

Si se recupera un slider continuo «Me importa más pendiente ↔ relieve», debe cambiar un orden de preferencia real y explicar su cálculo. No conectar la UI nueva a `/api/search`: ese catálogo, ventanas y métricas son distintos.

Una posible regla de preferencia, pendiente de revisión, sería ordenar de menor a mayor una suma ponderada de distancia de pendientes y diferencia absoluta de relieve **divididas por escalas de normalización declaradas**. Esas escalas y la política para datos faltantes deben quedar versionadas. Los pesos, aportaciones y cambios de orden se muestran; el resultado se llama preferencia, sin porcentaje de analogía.

La primera entrega prioriza comparación y controles ya sustentados. El ranking ponderado exige definir y evaluar un método adicional; se puede añadir después sin retrasar la recuperación visual. La preferencia nunca rellena dimensiones ausentes, nunca oculta su desglose y no cambia los datos medidos.

## 5. Cesium y las capas visuales

**Decisión propuesta:** conservar Cesium para ubicación y exploración regional. La comparación inicial usa las cuadrículas medidas en dos vistas 2D coordinadas. El usuario podrá abrir el contexto Marte–Tierra junto a ellas. Dos globos cargados por defecto no aportarían detalle local con las texturas actuales.

El terreno medido tendrá zoom y encuadre vinculados por extensión física, orientación y escala relativa al centro de cada ventana. No compartir coordenadas absolutas entre planetas. Activar cámara independiente cuando se necesite inspección libre. La comparación de colores exige igual unidad y límites; el sombreado se identifica como contexto.

Para el primer incremento, usar los GeoTIFF existentes de fase 2 para generar **derivados visuales nuevos**: solo área medida, rango común, máscara visible y metadatos. No sobrescribir PNG, JSON, manifiestos ni rásteres de la evidencia original. No recalcular métricas para recolorear un mapa.

La producción puede publicar imágenes ligeras con extensión, leyenda y referencia de procedencia; no necesita mandar GeoTIFF completos al navegador. No usar mapas de altura relativa para sugerir alturas absolutas equivalentes entre cuerpos. El modo 3D de detalle queda para un incremento posterior que disponga de mallas y referencias geodésicas verificadas.

Cargar Cesium bajo demanda, liberar viewers al salir, manejar falta de WebGL y mantener comparación numérica y figuras utilizables como alternativa. Revisar además el tamaño de ventana: `ContextGlobe` cae por defecto en 1800 m cuando no recibe `side_m`; algunas llamadas regionales simplifican el objeto. La nueva interfaz debe recibir `window_m=3000` explícito en esos recorridos.

## 6. Arquitectura técnica de la refactorización

Mantener React, TypeScript, Vite, FastAPI y los cálculos actuales. Estructura propuesta:

```text
frontend/src/
  app/AtlasShell.tsx                  navegación y contexto activo
  domain/analysis.ts                  tipos, unidades, estados y compatibilidad
  data/api.ts                        peticiones, cancelación y errores
  data/adapters.ts                    fase 2 / fase 4 / fase 5 → modelos de vista
  features/compare/CompareWorkspace.tsx
  features/explore/ExploreWorkspace.tsx
  features/sensitivity/SensitivityWorkspace.tsx
  components/ComparisonStage.tsx      dos vistas con leyenda compartida
  components/TerrainLayer.tsx
  components/LocationContext.tsx      adaptación de ContextGlobe
  components/SlopeComparison.tsx
  components/ReliefComparison.tsx
  components/EvidenceStatus.tsx
  components/AnalysisControls.tsx
  components/MethodDrawer.tsx
  styles/tokens.css
  styles/layout.css
  styles/components.css
```

Modelo de contexto mínimo: `experimentId`, `scenarioId`, `referenceId`, `candidateId`, `windowM`, `cellM`, `sourceId`, `layer`, `profile`, `sort`. Un experimento mantiene sus escalas y fuentes permitidas. URL con esos parámetros para compartir/restaurar una vista; parámetros incompatibles se corrigen de forma visible.

Estados de datos explícitos: carga, listo, vacío, error, pendiente e insuficiente. El estado del filtro es independiente del estado de evaluación. Formatear `null` como ausencia y conservar cero como valor. Datos de consultas anteriores no deben aparecer bajo un nuevo rótulo mientras carga. Cancelar peticiones y validar su clave al recibirlas, conservando el aislamiento que ya implementan las vistas actuales.

Al pasar del primer caso a búsqueda regional, indicar «Ahora comparas ventanas de 3 km». La candidata histórica `earth-utah`, el control `control-utah` y una ventana como `utah-010-007` no son intercambiables. Al abrir sensibilidad desde una ventana que no pertenece a las diez, mostrar «No incluida en esta muestra»; permitir escoger una evaluada, sin sustituirla silenciosamente.

## 7. Datos y API: lo reutilizable y lo que falta

| Necesidad de UI | Recurso existente | Trabajo adicional |
|---|---|---|
| Comparación inicial, distribuciones y relieve | `/api/scenarios/relieve-regional/comparison` | Adaptador y gráficos; conservar valores completos para cálculos y redondear solo presentación |
| Capas iniciales con leyenda común | GeoTIFF de `docs/evidencia-fase-2/` | Generador de visuales y endpoint de lista cerrada o assets estáticos con metadatos nuevos |
| Todas las huellas del área y filtros | `/api/regional-search/export` | Consumir su FeatureCollection GeoJSON; no montar un mapa con solo la página actual |
| Lista, conteos y ficha regional | `/api/regional-search/candidates` y `/{id}` | Añadir `sort=slope_distance|abs_relief_difference` antes de paginar; conservar orden estable por ID y política de nulos |
| Mapa y lista consistentes | Exportación y lista comparten área, celda, perfil e inclusiones | Clave de consulta común; verificar mismo conjunto y conteos; no usar como orden de lista el orden del GeoJSON |
| Sensibilidad, muestra y pendientes | `/api/expansion` | Adaptador de métricas regionales/locales y selección sincronizada |
| Acceso a procedencia | Endpoints cerrados de evidencia existentes | Panel de detalle con enlaces a fuentes y registros |
| Imagen local de las 970 ventanas | No disponible de forma general | Estado «Sin capa local»; ampliar generación de visuales solo donde haya datos revisados |

La API actual lee evidencia precalculada. Mover controles no debe iniciar adquisiciones ni nuevos cálculos científicos. Si se incorpora una ordenación nueva, sus pruebas se añaden al servicio; si se agrega ranking ponderado, requiere un contrato y evaluación propios.

## 8. Lenguaje e información por niveles

| Hoy | Primera lectura | Detalle consultable |
|---|---|---|
| Distancia Wasserstein | Diferencia entre pendientes · menor = más cercanas | Métrica de Wasserstein en grados, calculada con las muestras válidas |
| Relieve p95−p5 | Variación de altura | Diferencia entre percentiles 95 y 5 de elevación |
| Reconocimiento · fuente y escala | Ver qué cambia | Producto, celda, base de pendiente y selección de muestra |
| Locally evaluated exploratory | Con evaluación local | Cobertura, productos, método y límites |
| Pendiente | Inclinación, cuando se trata de terreno | Usar «Falta evaluar» para el estado y evitar la ambigüedad |
| Fuente de datos | Datos utilizados | Producto, fecha, hash y referencia vertical |

Primer nivel: par de lugares, imágenes, dos gráficos, una frase y datos faltantes. Segundo: explicación por variable y sensibilidad. Tercero: fuentes, tablas completas, método y registros. Siempre queda visible una línea breve «Comparación exploratoria de terreno; movilidad sin evaluar» y el estado de datos faltantes. No convertir cada límite en un bloque de texto permanente.

## 9. Secuencia de implementación y criterios de salida

Cada etapa entrega algo revisable. Las estimaciones son orientativas para una persona familiarizada con el proyecto; incluyen integración y comprobaciones, y se ajustan tras la primera etapa.

| Etapa | Alcance y dependencias | Entrega | Criterio de salida |
|---|---|---|---|
| A · Contrato visual y datos, 0,5–1 día | Inventariar respuestas y congelar casos de referencia; definir estados y escalas | Matriz de compatibilidad, modelos de vista y boceto con datos reales | Todos los números del boceto tienen origen identificado; faltantes y cero diferenciados |
| B · Comparación inicial, 1–2 días | Depende de A; generar capas comunes y montar mesa visual | Jezero ↔ Utah/Atacama; capa, celda, pendientes y relieve | Resultado aparece sin scroll a 1440×900; candidata y escala actualizan todo; valores coinciden con fase 2 |
| C · Exploración regional, 1–2 días | Depende de A y componentes de B | Mapa, lista y ficha coordinados; perfiles discretos; ordenación global | Utah/base/300 m muestra 99/272; mapa y lista coinciden; controles y ventanas excluidas se pueden examinar |
| D · Sensibilidad, 1 día | Depende de A y B | Dos comparaciones controladas, pendientes claros | 10 seleccionadas, 7 evaluadas, 3 pendientes; filtros solo regionales; 0/7 cambios correctamente acotados |
| E · Integración y accesibilidad, 0,5–1 día | B–D | URL restaurable, móvil, teclado, carga/error y Cesium diferido | Ninguna vista mezcla experimentos o muestra datos obsoletos; alternativa sin WebGL funciona |
| F · Comprensión y ajuste, 0,5–1 día | Depende de E | Sesiones con cinco personas sin contexto, resultados y correcciones | Al menos 4/5 completan las tareas de comprensión y distinguen pendiente de evaluación y mala coincidencia |

Orden de prioridad: **B es el primer incremento de producto**, seguido de C y D; A prepara su base. La estimación total orientativa es 4,5–8 días. Pesos continuos y terreno 3D son incrementos posteriores, con requisitos propios, fuera de esa estimación.

Conservar las rutas y contratos actuales durante la migración. Sustituir cada recorrido cuando cumpla sus criterios, en commits pequeños. Las evidencias científicas previas permanecen intactas; nuevos assets visuales tienen directorio y manifiesto propios.

## 10. Cómo comprobar que mejora

### Comprensión, que es el objetivo principal

Sin tutorial, pedir a cinco personas que:

1. Identifiquen los dos lugares y expliquen qué representa cada vista.
2. Indiquen cuál de las dos candidatas iniciales se aproxima más en pendientes y qué diferencia presenta en relieve.
3. Cambien de 60 a 120 m y describan qué modificaron.
4. Busquen una ventana que cumpla el perfil regional y distingan su estado de evaluación local.
5. Expliquen por qué una ventana pendiente no recibe un cero ni una mala nota.

Registrar tiempo hasta la respuesta, aciertos, confusiones y necesidad de ayuda. Comprobar los objetivos de 10/30 segundos en las tareas pertinentes. Si fallan, revisar jerarquía, leyendas y controles antes de añadir funciones. No considerar que una captura bonita o un build correcto prueban comprensión.

### Corrección técnica y visual

- Adaptadores: comparar números y estados con JSON existentes; verificar signo, unidad, cero y `null`. No copiar números redondeados para cálculos.
- E2E esenciales: cambio de candidata/celda, peticiones fuera de orden, error y reintento, filtros/lista/mapa, URL, muestra pendiente y selección incompatible al cambiar recorrido.
- API si se modifica ordenación: ordenar el conjunto completo antes de paginar; desempates estables; nulos al final; exportación con mismos filtros.
- Capas: misma variable y escala cromática; máscara visible; orientación, ventana y borde coinciden; no confundir recorte con margen y área medida.
- Vistas a 1440×900, 1024×768, 390×844 y 320 px; controles táctiles, tabulación, foco visible, nombres accesibles y contraste. En móvil, paneles consecutivos con mismo encuadre y contexto compartido; sin obligar a arrastrar tablas para entender lo principal.
- Gráficos con unidades y equivalentes textuales; significado además del color; `aria-live` para cambios relevantes y respeto a reducción de movimiento.
- Medir carga y fluidez en el equipo de referencia; Cesium bajo demanda, sin viewers huérfanos ni bloqueos al cambiar candidata. Fijar presupuesto de assets después de medir el primer incremento, sin añadir infraestructura de antemano.
- Ejecutar build TypeScript/Vite y tests existentes cuando se implemente; sumar pruebas de integración para los comportamientos nuevos. Revisar manifiestos antes/después para detectar modificaciones accidentales de evidencia.

## 11. Riesgos y decisiones que quedan explícitas

| Riesgo | Respuesta de diseño |
|---|---|
| Colores iguales parecen significar lo mismo, pero las escalas difieren | Leyenda común por capa, límites declarados y unidades visibles |
| Una ventana regional parece directamente comparable al caso de 1,8 km | Contexto persistente con ventana, fuente y celda; cambio de experimento explícito |
| «No cambió el filtro» se interpreta como validación | Mostrar alcance «7 pares de esta muestra» y acceso al contraste numérico |
| Mapa aparenta cobertura continua | Huellas reales y espacios sin evaluar; porcentaje de muestreo consultable |
| Sliders aparentan cálculo continuo o nueva precisión | Posiciones discretas sustentadas y valores activos visibles |
| El énfasis visual oculta una dimensión desfavorable | Mantener ambas métricas visibles; solo variar el foco |
| Nueva estética borra procedencia | Fuentes y método accesibles desde la comparación activa |
| Recolorear altera una entrega científica revisada | Derivados nuevos vinculados a originales; conservar hashes previos |

El primer trabajo implementable es extraer el modelo de comparación y montar el par visual con los datos de fase 2, leyendas compartidas y cambio de candidata/celda. Eso permite comprobar la comprensión antes de extender el patrón a las 970 ventanas.
