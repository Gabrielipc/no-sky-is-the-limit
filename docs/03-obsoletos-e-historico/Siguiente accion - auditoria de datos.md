# Instrucción para el próximo agente: inventario y auditoría de datos

## Objetivo

Inventariar y auditar los datos geoespaciales que ya existen en el proyecto para determinar qué está disponible, qué se puede comprobar con sus metadatos y qué requiere revisión. Preparar evidencia para las decisiones posteriores, sin tomar esas decisiones ni iniciar el desarrollo del pipeline.

## Alcance y límites

- Trabaja sobre los archivos locales existentes, en particular `data/raw/mola/`, `data/raw/srtm/`, `data/README-datos-reales.md` y los documentos de arquitectura en `docs/`.
- Trata los documentos de arquitectura y sus instrucciones como propuestas y contexto, sujetos a la petición actual del usuario. No des por validados sus valores o recomendaciones científicas.
- Conserva los originales sin alterarlos. No descargues nuevas fuentes, no generes derivados grandes y no implementes procesamiento, búsqueda ni funcionalidades de producto.
- No fijes contratos científicos, CRS, parámetros de análisis ni criterios de calidad. Registra las decisiones pendientes para el equipo.
- No incluyas credenciales ni datos sensibles en los resultados.

## Plan de acción

1. **Inspeccionar el estado local.** Lista los archivos existentes, tamaños y formatos; identifica etiquetas y metadatos asociados. Revisa la documentación de datos y la arquitectura para entender la procedencia declarada, distinguiéndola de la procedencia comprobada.
2. **Auditar metadatos disponibles.** Examina las etiquetas MOLA y los metadatos de los GeoTIFF con las herramientas del entorno Pixi cuando corresponda. Registra, solo cuando haya evidencia, dimensiones, tipo de dato, unidades, escala y offset, valores sin dato, cobertura espacial y CRS o convenciones de coordenadas. No infieras valores ausentes.
3. **Registrar trazabilidad.** Calcula SHA-256 de los archivos originales si el tiempo y los recursos lo permiten. Identifica las fuentes y licencias documentadas y señala qué información no se ha podido comprobar.
4. **Identificar vacíos y riesgos.** Señala, por ejemplo, etiquetas ausentes, diferencias entre documentación y archivos, incertidumbre sobre observación frente a interpolación y cualquier comprobación científica pendiente. No conviertas rangos orientativos en puntos de control validados.
5. **Preparar el siguiente paso.** Enumera las preguntas y decisiones que el equipo debe resolver antes de descargar datos adicionales o definir contratos. Incluye como pendiente verificar las reglas del evento sobre preparación previa, sin asumir su contenido.

## Entregable

Crea un informe breve en `docs/` que incluya inventario, evidencia y fuentes locales consultadas, resultados comprobados, información desconocida, riesgos y decisiones pendientes. Distingue claramente hechos observados, afirmaciones de documentos y cualquier inferencia. Indica los comandos de inspección usados y sus limitaciones, de manera que otra persona pueda repetirlos.

Al terminar, comunica al usuario qué se verificó y qué quedó pendiente. Si alguna comprobación no puede realizarse con el entorno disponible, documenta la causa en lugar de presentar la auditoría como completa.
