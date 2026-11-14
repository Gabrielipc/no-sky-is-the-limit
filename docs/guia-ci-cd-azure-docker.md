# CI/CD del Atlas en una VM de Azure con Docker

Esta guía describe el flujo automatizado definido en
[`../.github/workflows/ci-cd.yml`](../.github/workflows/ci-cd.yml). Las pull
requests hacia `main` ejecutan comprobaciones; solo un `push` aceptado en `main`
publica la imagen en GitHub Container Registry (GHCR) e intenta desplegarla en la
VM. No se usa Nginx.

## Arquitectura desplegada

- La etapa Node del [`../Dockerfile`](../Dockerfile) instala las dependencias
  bloqueadas con `npm ci` y compila el frontend.
- La etapa Python instala las dependencias bloqueadas con `uv.lock`, incorpora
  el backend y las evidencias revisadas, y copia el frontend compilado.
- FastAPI sirve el frontend en `/` y conserva los endpoints `/api/...`. Así el
  navegador usa el mismo origen y no se requieren cambios a las URLs ni a los
  formatos de respuesta existentes.
- El contenedor corre con un usuario sin privilegios y publica el puerto 8000.
- [`../deploy/docker-compose.yml`](../deploy/docker-compose.yml) monta el directorio
  de publicaciones del Atlas 30 m desde la VM. El montaje es escribible porque
  `/api/atlas/search` guarda las consultas reproducibles en `searches.sqlite`.

El Atlas 30 m se publica aparte de Git: `releases/` está excluido del repositorio.
Si el directorio de publicaciones está vacío o no tiene una versión activa, la
app y el resto de la API pueden arrancar, pero los endpoints de Atlas devolverán
el error explícito de índice no disponible hasta que se instale una publicación.

## Variables de Docker Compose

[`../deploy/.env.example`](../deploy/.env.example) es la plantilla sin secretos
para ejecutar Compose manualmente. Cópiala como `deploy/.env` (ese archivo está
ignorado por Git) y ajusta la ruta de datos antes de iniciar el servicio:

```bash
cp deploy/.env.example deploy/.env
docker compose --env-file deploy/.env -f deploy/docker-compose.yml config
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d
```

La plantilla define `IMAGE` (imagen a descargar de GHCR), `APP_PORT` (puerto
expuesto en la VM, por defecto `8000`) y `ATLAS_RELEASES_PATH` (ruta persistente
del Atlas). La VM debe poder iniciar sesión en GHCR antes de descargar una imagen
privada. En el despliegue automatizado, Actions genera su propio `.env` usando la
etiqueta SHA del commit; no se copia la plantilla de ejemplo.

## Flujo automático

1. Abrir una pull request hacia `main` ejecuta pruebas del backend, pruebas y
   compilación del frontend, y una construcción Docker de prueba.
2. Al hacer merge, el `push` a `main` repite las comprobaciones.
3. Si pasan, GitHub Actions construye y publica `latest` y una etiqueta inmutable
   `sha-<commit>` en GHCR.
4. El job de despliegue se conecta por SSH a Azure, actualiza el Compose y su
   archivo `.env`, descarga la imagen de ese commit y verifica que el volumen del
   Atlas sea escribible por el UID 10001 antes de iniciar el servicio.
5. Compose espera el health check de `/openapi.json` antes de marcar el
   despliegue como listo.

El flujo no modifica reglas de ramas ni habilita pushes directos. Configura la
protección de `main` en GitHub para requerir los jobs `Backend tests`,
`Frontend tests and build` y `Docker image smoke test`.

## Preparar la VM de Azure

Se asume una VM Linux (por ejemplo, Ubuntu 22.04/24.04), con Docker Engine y el
plugin `docker compose` instalados desde la documentación oficial de Docker.
No instales ni configures Nginx para este despliegue.

1. Crea un usuario de despliegue dedicado. Dale acceso al daemon de Docker
   siguiendo la política de tu organización. Pertenecer al grupo `docker`
   equivale prácticamente a tener privilegios de root; limita el acceso a esa
   cuenta.
2. Crea los directorios persistentes. Ajusta el dueño del directorio de la app
   al usuario SSH de despliegue y el de publicaciones al UID/GID `10001`, que es
   el usuario del proceso dentro del contenedor:

   ```bash
   sudo mkdir -p /opt/analogos
   sudo mkdir -p /srv/analogos/releases/atlas30
   sudo chown deploy:deploy /opt/analogos
   sudo chown 10001:10001 /srv/analogos/releases/atlas30
   ```

   Sustituye `deploy:deploy` por el usuario y grupo reales.
3. Instala la clave pública SSH de despliegue en `~deploy/.ssh/authorized_keys`.
   Protege la clave privada y guarda su contenido únicamente como secreto de
   GitHub; no la pongas en el repositorio ni en esta guía.
4. En la Network Security Group (NSG) de Azure permite:
   - TCP `8000` desde los rangos que realmente deban acceder a la aplicación.
   - SSH (normalmente TCP `22`) solo desde las IP de administración o del runner
     autorizado. Los runners hospedados por GitHub no tienen una IP de salida
     fija sencilla de mantener en una allowlist; para restringir más el acceso,
     usa un runner self-hosted dentro de la red de Azure, VPN o un bastion.

La app se sirve por HTTP directo en `http://<IP-o-DNS-de-la-VM>:8000`. Sin un
proxy TLS, la conexión pública **no está cifrada**. Es una limitación importante
para una VM accesible desde Internet; restringe el tráfico a una red de
confianza hasta que decidas cómo añadir HTTPS.

### Publicación persistente del Atlas

Si quieres habilitar la vista mundial, copia una publicación aprobada de
`releases/atlas30` a `/srv/analogos/releases/atlas30` en la VM, incluyendo el
puntero `current` y los directorios/manifiestos de versión que este referencia.
No copies `data/raw/` ni credenciales. Mantén permisos que permitan al UID 10001
leer las publicaciones y escribir `searches.sqlite`. Haz respaldo de esta
carpeta antes de actualizar datos. El código y la imagen se despliegan desde Git;
las publicaciones permanecen en el volumen de la VM.

## Configurar GitHub Actions

En **Settings → Secrets and variables → Actions**, crea los siguientes valores.

### Secrets

| Nombre | Valor |
|---|---|
| `AZURE_VM_HOST` | IP pública o nombre DNS de la VM, sin esquema ni puerto. |
| `AZURE_VM_USER` | Usuario SSH dedicado para despliegues. |
| `AZURE_VM_SSH_KEY` | Clave privada que corresponde a la clave pública instalada en la VM. No compartirla por chat. |
| `AZURE_VM_KNOWN_HOSTS` | Línea de `known_hosts` para esa VM; valida su huella por un canal confiable antes de guardarla. |
| `GHCR_USERNAME` | Cuenta GitHub que puede descargar el paquete del contenedor. |
| `GHCR_PULL_TOKEN` | PAT clásico de alcance mínimo con `read:packages` y acceso al paquete privado de GHCR. No compartirlo por chat. |

El workflow usa `GITHUB_TOKEN` automáticamente para publicar la imagen; no crees
un token de publicación adicional. GHCR suele crear el paquete como privado.
Conserva el token de descarga solo en GitHub Secrets y en el almacén Docker de la
cuenta de despliegue de la VM.

### Variables

| Nombre | Ejemplo | Uso |
|---|---|---|
| `AZURE_VM_SSH_PORT` | `22` | Puerto SSH; si se omite, usa `22`. |
| `AZURE_VM_APP_DIR` | `/opt/analogos` | Directorio remoto del Compose y `.env`. |
| `AZURE_VM_APP_PORT` | `8000` | Puerto de la VM que se publica hacia Internet. |
| `ATLAS_RELEASES_PATH` | `/srv/analogos/releases/atlas30` | Directorio persistente del Atlas dentro de la VM. |

Los dos directorios deben ser rutas absolutas sin espacios ni comillas. No agregues
al repositorio `.env` de producción, claves SSH, tokens, contraseñas ni datos
locales originales.

Antes de guardar `AZURE_VM_KNOWN_HOSTS`, obtén la clave pública del host por un
canal confiable (por ejemplo, la consola de Azure) y compara su huella. No uses
una salida de `ssh-keyscan` sin verificarla como si fuera identidad autenticada.
El workflow mantiene `StrictHostKeyChecking=yes`.

## Primera publicación y comprobación

1. Sube esta configuración en una pull request hacia `main` y espera a que pasen
   los jobs de CI.
2. Crea los secrets y variables, prepara los directorios y permisos de la VM, y
   confirma que Docker Compose puede ejecutarse con el usuario SSH.
3. Fusiona la pull request en `main`. El job de despliegue fallará indicando el
   secret o variable ausente si falta configuración.
4. Al terminar, abre:
   - `http://<IP-o-DNS-de-la-VM>:8000/` para el frontend.
   - `http://<IP-o-DNS-de-la-VM>:8000/docs` para Swagger.
   - `http://<IP-o-DNS-de-la-VM>:8000/openapi.json` para comprobar el contrato
     OpenAPI.
5. En la VM comprueba estado y logs:

   ```bash
   cd /opt/analogos
   docker compose --env-file .env -f docker-compose.yml ps
   docker compose --env-file .env -f docker-compose.yml logs --tail=100 app
   ```

## Rollback

Las imágenes se etiquetan por commit y se conservan en GHCR. Para volver a una
versión anterior, edita únicamente el valor `IMAGE` en `/opt/analogos/.env` para
usar `ghcr.io/<owner>/<repo>:sha-<commit-anterior>` y ejecuta:

```bash
cd /opt/analogos
docker compose --env-file .env -f docker-compose.yml pull
docker compose --env-file .env -f docker-compose.yml up -d --wait
```

No borres la publicación persistente del Atlas durante un rollback de código.

## Datos necesarios para completar el despliegue real

La configuración del repositorio ya deja preparado el flujo, pero no puede
desplegar hasta tener:

- IP pública o DNS de la VM, sistema operativo, puerto SSH y usuario dedicado.
- Clave SSH y huella de host verificable; la clave privada se guarda solo como
  GitHub Secret.
- Directorio de despliegue, puerto público elegido y ruta persistente para el
  Atlas.
- Decisión de acceso a la app: IPs permitidas y si el HTTP sin TLS es aceptable
  temporalmente.
- Decisión sobre las publicaciones del Atlas: confirmar si se desplegará una
  versión y cómo se transferirá/resguardará.
- Confirmar que el paquete GHCR puede ser privado y crear un PAT de solo lectura
  para que la VM lo descargue.

No envíes claves privadas, PAT ni credenciales por el chat. Guárdalos directamente
en **GitHub Secrets**; comparte aquí solo datos no secretos si necesitas ayuda
para ajustar nombres, rutas o puertos.
