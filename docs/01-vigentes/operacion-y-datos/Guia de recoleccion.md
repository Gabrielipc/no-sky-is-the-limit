# Recolección de originales

`scripts/recolectar_datos.py` utiliza la biblioteca estándar de Python; ejecutar desde la raíz con el Python de Pixi ya instalado:

```sh
.pixi/envs/default/bin/python scripts/recolectar_datos.py doctor
.pixi/envs/default/bin/python scripts/recolectar_datos.py discover
.pixi/envs/default/bin/python scripts/recolectar_datos.py fetch --max-gb 50
.pixi/envs/default/bin/python scripts/recolectar_datos.py verify
```

`discover` consulta índices y cabeceras remotas y guarda `data/manifests/plan.json`. Muestra el tamaño conocido y el número de tamaños desconocidos; termina con error si una fuente falla, está incompleta o no proporciona tamaños. No descarga imágenes. Puede elegirse una o más fuentes con `--sources mola mola_polar lola gmted`. Una fuente incompleta no se descarga. `fetch --sources lola` limita el lote. El manifiesto cambia durante la descarga y queda excluido de Git; no lo edites con URLs ni credenciales sensibles.

El límite `--max-gb` usa GB decimales y cuenta todos los archivos dentro de `data/raw`, incluidos los existentes y parciales; se reserva además 1 GiB de espacio libre. El máximo admitido es 100 GB. El límite no incluye el espacio requerido para descomprimir ZIP ni derivados fuera de `data/raw`: compruébalo antes de extraer. El script no descomprime ni procesa datos. Los archivos se guardan en carpetas separadas y no se sobrescriben. Los parciales y sus metadatos se conservan tras fallos. El script reintenta automáticamente hasta cinco veces y, si hay un validador HTTP y el servidor admite rangos, reanuda desde el último byte. Los parciales anteriores sin metadatos se comparan con el proveedor antes de reutilizarse; esta comprobación transfiere de nuevo el prefijo, pero lo conserva. Si el proveedor no confirma el rango o cambió la versión, se detiene sin borrar el parcial. Los hashes SHA-256 son locales, no prueba independiente de autenticidad. `verify` exige que todos los archivos del plan existan y coincidan con su hash registrado.

La selección inicial comprende MOLA MEG128 (32 imágenes de topografía y recuentos con etiquetas), MOLA polar 128 (cuatro imágenes con etiquetas), LOLA LDEM 64 float con etiquetas y GMTED media a 7,5 y 30 segundos. La selección de media GMTED es provisional; conservar sus límites científicos. El inventario incluye candidatos polares ArcticDEM y REMA, pero todavía no se ha comprobado su cobertura efectiva; tampoco incluye capas contextuales, documentación adicional MOLA/LOLA ni un producto de soporte LOLA. Es necesario seleccionarlos y verificar cobertura antes de considerar completa la recolección global. El script tampoco reutiliza automáticamente los archivos existentes ni valida puntos de control o formatos científicos.

Los índices PDS consultados son públicos y los enlaces GMTED se publican en el catálogo USGS, pero una respuesta 401 o 403 puede reflejar autenticación, permisos o restricciones del proveedor. No proporciones contraseñas por chat. El script actual no admite credenciales: si un recurso las exige, se debe añadir el método oficial para ese proveedor. Si hay problemas de conectividad, ejecutar `doctor` en una conexión disponible. Los archivos sin `Content-Length` no se descargan hasta disponer de una estimación verificable.

## Recursos polares y recuperación de una descarga interrumpida

Se añadieron ArcticDEM 4.1 y REMA 2.0 a 500 m, disponibles como archivos públicos del [Polar Geospatial Center](https://www.pgc.umn.edu/data/arcticdem/) y [REMA](https://www.pgc.umn.edu/data/rema/). Sus datos originales son modelos de superficie y usan alturas relativas al elipsoide WGS84; no combinarlos automáticamente con GMTED. Atribuir las fuentes conforme a la política del proveedor y comprobar cobertura, vacíos y datos de soporte. Son candidatos, no una garantía de cobertura completa.

Para retomar GMTED sin borrar el parcial:

```sh
.pixi/envs/default/bin/python scripts/recolectar_datos.py fetch --sources gmted --max-gb 50
```

Para planificar los polos en un manifiesto separado y descargarlos:

```sh
.pixi/envs/default/bin/python scripts/recolectar_datos.py discover --sources arcticdem rema --out data/manifests/polos.json
.pixi/envs/default/bin/python scripts/recolectar_datos.py fetch --plan data/manifests/polos.json --max-gb 50
.pixi/envs/default/bin/python scripts/recolectar_datos.py verify --plan data/manifests/polos.json
```

Si ya existe `polos.json` con hashes, conserva ese plan y omite `discover`. Ninguno de estos dos archivos públicos exige credenciales. Los tamaños comprimidos son aproximadamente 660 MiB y 285 MiB según los índices PGC; el espacio extraído no se conoce aún y no está incluido en el presupuesto. Los SHA-256 locales detectan cambios posteriores pero no validan el contenido frente a un hash oficial.
