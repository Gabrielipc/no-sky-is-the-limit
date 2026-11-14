# Evidencias de la primera exploración

Entrada principal: [informe de investigación](../01-vigentes/etapa-actual-armonizacion/Primera%20entrega%20-%20exploracion%20de%20fuentes%20y%20preguntas%20cientificas.md).

Esta carpeta contiene salidas nuevas de lectura de originales. No sustituye las publicaciones anteriores ni configura la función de similitud. Instantánea del 10 de noviembre de 2026, America/Managua.

| Archivo | Contenido |
|---|---|
| `inventario.json` | Un registro por archivo local: tamaño, modificación, estado de lectura, cabeceras, bandas, atributos; también miembros de archivos comprimidos |
| `resumen.json` | Recuentos por familia, versiones del entorno y alcance de la exploración |
| `diccionario-observado.md` | Campos observados, sin deducir unidades ausentes de la cabecera |
| `huellas.json` | Seis polígonos terrestres y uno marciano, con definición explícita del cuerpo y CRS en Marte |
| `perfiles-espaciales.json` | Conteos y cuantiles nativos por activo y huella para elevación, WorldCover y JRC |
| `perfiles-temporales.json` | Bandas, máscaras, índices diagnósticos, temperatura e incertidumbre por escena; políticas alternativas |
| `perfiles-emit.json` | Soporte GLT, muestras originales únicas, clases por grupo, ajuste almacenado y ×2, profundidad e incertidumbre |
| `perfiles-marte.json` | HiRISE, THEMIS y todas las bandas SR de CRISM en la nueva ventana de 3 km |
| `muestras-diagnosticas.json` | Cinco parches nativos de 32 × 32 por archivo seleccionado; los parches polares y JP2 están en el inventario |
| `tablas-resultados.md` | Tablas legibles generadas de los perfiles |
| `identidades-entradas.json` | Hashes SHA-256 de 180 entradas interpretadas o muestreadas |
| `manifest.json` | Hashes de los resultados de exploración, su programa y dependencias de configuración/lectura |
| `manifest-presentacion.json` | Hashes del generador de figuras, tablas y gráficos |
| Tres pares PNG/SVG | Disponibilidad local, soporte por escena y clases en ventanas piloto |

## Reglas de interpretación

1. **Inventario ≠ cobertura válida.** Los archivos y sus extensiones no certifican observaciones útiles. Los archivos `.part`, `.lock` y `.etag` se excluyen del análisis científico.
2. **Original del proyecto ≠ dato instrumental sin procesar.** Se respeta el nivel de producto entregado por cada proveedor.
3. **Perfiles por centros, no por área.** Las fracciones usan la huella completa, sin máscara terrestre ni ponderación por intersección. El soporte de una variable y una fecha no se transfiere a otra.
4. **Muestras diagnósticas, no estimación mundial.** La selección de parches es determinista por orden de archivos. Ni tamaños de muestra ni promedios de estas muestras representan la superficie global.
5. **Rejilla ≠ información independiente.** No usar centros térmicos o repeticiones GLT como grados de libertad independientes. Los cuantiles EMIT están ponderados por repeticiones GLT en esta exploración; se deberá evaluar también la distribución sobre muestras únicas.
6. **Codificaciones categóricas.** En máscaras, códigos de clase y banderas, consultar conteos/decodificación. Los cuantiles genéricos de códigos almacenados son diagnósticos técnicos y no magnitudes científicas.
7. **Datos ausentes.** `null` en una estadística sin observaciones no representa cero. `no_scene_selected` no implica que el proveedor carezca de cobertura. Una combinación sitio–fuente sin perfil no tiene un activo local con intersección en esta selección.
8. **EMIT.** Se conserva ajuste almacenado y ajuste ×2 documentado por NASA. Los filtros son experimentales, sin máscaras L2A complementarias locales. Ningún conteo certifica abundancia o probabilidad mineralógica.
9. **Metadatos planetarios.** LOLA necesita distinguir altura de radio y km de m. Los valores de parches MOLA/LOLA están en unidades almacenadas; una máscara del lector puede necesitar reinterpretación a partir de la etiqueta.
10. **Identidad.** El inventario mundial guarda tamaño y modificación; solo el conjunto de 180 entradas tiene hash completo recalculado. Los seis archivos EMIT se contrastaron además con los hashes fijados anteriormente. Cambios futuros en las descargas cambian la instantánea.

## Reproducir

Ejecutar desde la raíz del repositorio con los originales locales y el entorno de minerales existentes:

```sh
bash scripts/ejecutar_minerales.sh scripts/explorar_fuentes_atlas.py
bash scripts/ejecutar_minerales.sh scripts/presentar_exploracion_atlas.py
bash scripts/ejecutar_minerales.sh -m unittest discover -s tests -p test_explorar_fuentes_atlas.py -v
```

Los paquetes polares se copian temporalmente, miembro a miembro, a una carpeta temporal para leerlos. No se extraen sobre `data/raw/`. El trabajo no necesita red para reproducir los cálculos. La interpretación documental y los hallazgos se conservan en el informe principal; su redacción no se regenera automáticamente.

El JSON de huellas contiene coordenadas marcianas con su CRS explícito: **no importar esa geometría como coordenadas terrestres WGS84**. Los SHA-256 verifican identidad de archivos, no exactitud científica.
