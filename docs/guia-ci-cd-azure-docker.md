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

### 1. Crear la VM y reservar sus datos de conexión

1. En Azure Portal, crea una VM Linux con Ubuntu 22.04 o 24.04. Asígnale una
   IP pública estática o configura un nombre DNS estable; `AZURE_VM_HOST` debe
   seguir apuntando a la VM después de reinicios.
2. Durante la creación, habilita SSH y usa una clave pública SSH. Limita el
   acceso administrativo a tu IP siempre que sea posible. No habilites SSH con
   contraseña para facilitar Actions.
3. En **Networking**, confirma que la VM tenga una Network Security Group (NSG)
   asociada y una regla TCP de entrada para SSH (normalmente `22`) que permita
   conectarte desde tu IP administrativa. Más adelante revisarás también el
   acceso del runner y el puerto de la app.
4. Anota la IP pública o el DNS, el usuario inicial de Ubuntu y el puerto SSH
   (normalmente `22`). No pongas esos valores en el código.

### 2. Conectarte como administrador e instalar Docker

Estos comandos se ejecutan en una **terminal de tu computadora** (Linux/macOS o
WSL), no en GitHub ni en el editor de archivos. Usa la clave administrativa
asociada con la VM y el usuario inicial que Azure mostró al crearla:

```bash
ssh -i RUTA_A_TU_CLAVE_ADMIN usuario-inicial@IP_O_DNS_DE_LA_VM
```

Reemplaza `RUTA_A_TU_CLAVE_ADMIN`, `usuario-inicial` y
`IP_O_DNS_DE_LA_VM` por tus valores reales. Tras conectarte, el prompt cambia:
ahora estás ejecutando comandos **dentro de la VM** como el usuario
administrador. Instala Docker Engine y el plugin Compose siguiendo la guía
oficial para Ubuntu:
[Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
Después, todavía dentro de la VM, verifica:

```bash
sudo docker --version
sudo docker compose version
```

No continúes hasta que ambos comandos muestren una versión instalada.

### 3. Crear el usuario `deploy` y las carpetas en la VM

Ejecuta estos comandos **en la terminal SSH conectada a la VM**, como el
usuario administrador inicial. `sudo` solicita la contraseña del administrador
si la sesión la requiere; no es una contraseña para `deploy`.

```bash
sudo adduser --disabled-password --gecos "" deploy
sudo usermod -aG docker deploy
sudo mkdir -p /opt/analogos
sudo chown deploy:deploy /opt/analogos
sudo mkdir -p /srv/analogos/releases/atlas30
sudo chown 10001:10001 /srv/analogos/releases/atlas30
```

`deploy` queda sin contraseña y se autenticará por clave SSH. El grupo `docker`
equivale prácticamente a privilegios de `root`, por eso la cuenta debe ser
dedicada y su clave debe protegerse. `/opt/analogos` contendrá Compose y `.env`;
`/srv/analogos/releases/atlas30` conserva datos Atlas. El UID/GID `10001`
corresponde al usuario sin privilegios del contenedor.

Si todavía no tienes una publicación Atlas, esa carpeta puede quedar vacía: el
resto de la aplicación puede iniciar, pero las rutas Atlas no tendrán un índice.

### 4. Generar el par de claves en tu computadora

Abre **otra terminal local en tu computadora** (Linux/macOS o WSL). No ejecutes
estos comandos en la sesión SSH ni en la terminal de la VM: el archivo privado
debe quedarse en tu computadora para guardarlo directamente como Secret en
GitHub.

Primero crea la carpeta SSH si no existe y genera una clave exclusiva para el
despliegue:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/analogos_azure_deploy
chmod 600 ~/.ssh/analogos_azure_deploy
```

Cuando `ssh-keygen` pregunte por una frase de contraseña, pulsa **Enter** dos
veces para dejarla vacía. Esto se hace solo para esta clave dedicada porque
Actions no tiene un agente interactivo para desbloquearla. No uses ni compartas
una clave personal existente.

Se crean dos archivos en tu computadora:

- `~/.ssh/analogos_azure_deploy`: clave **privada**. No la muestres ni la copies
  a la VM; más adelante pegarás su contenido en el Secret
  `AZURE_VM_SSH_KEY`.
- `~/.ssh/analogos_azure_deploy.pub`: clave **pública**. Esta sí se instalará
  en la VM.

### 5. Instalar la clave pública en la cuenta `deploy`

Primero, en la **terminal local de tu computadora**, muestra la clave pública:

```bash
cat ~/.ssh/analogos_azure_deploy.pub
```

Copia la línea completa que empieza con `ssh-ed25519`. No copies el archivo
privado sin `.pub`.

Ahora vuelve a la **terminal SSH de la VM como usuario administrador inicial**
(la sesión del paso 2). Crea la carpeta de llaves de `deploy`:

```bash
sudo install -d -o deploy -g deploy -m 700 /home/deploy/.ssh
sudo nano /home/deploy/.ssh/authorized_keys
```

En el editor `nano`, pega la línea pública copiada, en una sola línea. Guarda
con `Ctrl+O`, pulsa `Enter` para confirmar el nombre y sal con `Ctrl+X`. Luego,
todavía **en la VM como administrador**, ajusta permisos:

```bash
sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys
sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

### 6. Probar el acceso `deploy` desde tu computadora

Este paso se ejecuta **en una terminal local nueva de tu computadora**, no
dentro de la VM. Reemplaza el host por la IP/DNS y cambia `22` si configuraste
otro puerto:

```bash
ssh -i ~/.ssh/analogos_azure_deploy -o IdentitiesOnly=yes \
  -p 22 deploy@IP_O_DNS_DE_LA_VM
```

No debe pedir una contraseña de `deploy`. Si pregunta `Are you sure you want to
continue connecting`, verifica primero la huella del servidor siguiendo la
sección `AZURE_VM_KNOWN_HOSTS` antes de aceptar. Si aparece `Permission denied
(publickey)`, comprueba que copiaste el archivo `.pub` en
`/home/deploy/.ssh/authorized_keys` y que aplicaste los permisos indicados.

Cuando la conexión funcione, el prompt de la terminal cambia otra vez: ahora
estás **dentro de la VM como `deploy`**. Ejecuta allí:

```bash
whoami
docker version
docker compose version
test -w /opt/analogos && echo "/opt/analogos escribible"
test -d /srv/analogos/releases/atlas30 && echo "Directorio Atlas existe"
```

`whoami` debe imprimir `deploy`. Si Docker muestra permiso denegado, confirma
que el usuario pertenece al grupo `docker` y cierra la sesión con `exit`;
conéctate de nuevo para que se aplique el grupo. La carpeta Atlas pertenece al
UID `10001`, no a `deploy`; el job de despliegue comprobará que el contenedor
pueda escribir allí. Al terminar la comprobación, ejecuta `exit` para volver a
la terminal local.

Si usas un puerto SSH distinto, reemplaza `22` en los comandos y configura
`AZURE_VM_SSH_PORT` en GitHub. Nunca copies la clave privada al
`authorized_keys`.

### 7. Abrir únicamente los puertos necesarios en Azure

En Azure Portal abre la VM → **Networking** → reglas de entrada de la NSG y
agrega:

1. Una regla TCP para SSH, normalmente puerto `22`. Como origen, elige tu IP
   administrativa o una red de confianza. El runner hospedado por GitHub no
   tiene una IP de salida fija sencilla de mantener en una allowlist. Para
   restringir SSH de forma estricta, considera un runner self-hosted en Azure,
   VPN o bastion.
2. Una regla TCP para el puerto de aplicación que usarás, por defecto `8000`.
   Restringe el origen a las redes que necesiten acceder. Evita `Any` si la
   aplicación no debe ser pública.

Si cambias el puerto de SSH, tanto la NSG como `AZURE_VM_SSH_PORT` deben usar el
mismo valor. El puerto de aplicación debe coincidir con `AZURE_VM_APP_PORT`.

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

Configura estos valores en el repositorio de GitHub
**Gabrielipc/no-sky-is-the-limit**:

1. Abre **Settings** del repositorio.
2. En la barra lateral, abre **Secrets and variables → Actions**.
3. Usa **New repository secret** para cada secreto y **Variables → New repository
   variable** para cada variable. Respeta exactamente los nombres (mayúsculas y
   guiones bajos); el workflow los busca literalmente.
4. Configúralos como valores del repositorio, no como secretos de una cuenta
   personal. Así estarán disponibles para el workflow de este repositorio.

No pegues valores secretos en commits, archivos `.env`, incidencias, capturas ni
mensajes. GitHub oculta un Secret después de guardarlo: si no recuerdas su valor,
reemplázalo por uno nuevo.

### Secrets

| Nombre | Valor |
|---|---|
| `AZURE_VM_HOST` | IP pública estática o DNS de la VM, por ejemplo `20.30.40.50` o `mi-vm.eastus.cloudapp.azure.com`. No incluyas `https://`, usuario ni puerto. |
| `AZURE_VM_USER` | Usuario SSH creado en la VM; en estos pasos es `deploy`. |
| `AZURE_VM_SSH_KEY` | Contenido completo de la clave privada `analogos_azure_deploy`, incluyendo las líneas `-----BEGIN OPENSSH PRIVATE KEY-----` y `-----END OPENSSH PRIVATE KEY-----`. Nunca uses el archivo `.pub`. |
| `AZURE_VM_KNOWN_HOSTS` | Línea de host SSH obtenida y verificada por un canal confiable. Debe corresponder al host y puerto configurados. |
| `GHCR_USERNAME` | Nombre de usuario de GitHub propietario del PAT que puede leer el paquete; no es el correo ni un nombre para mostrar. |
| `GHCR_PULL_TOKEN` | PAT clásico con permiso mínimo `read:packages` y acceso de lectura al paquete de GHCR. No uses `GITHUB_TOKEN` aquí: este secreto lo usa la VM para descargar la imagen. |

#### Cómo llenar cada Secret

1. **`AZURE_VM_HOST`**: copia la IP pública estática o el DNS desde la vista
   **Overview** de la VM en Azure. Verifica desde tu equipo que corresponde a
   esa VM. Guarda solo el host, por ejemplo `20.30.40.50`.
2. **`AZURE_VM_USER`**: escribe `deploy` si seguiste los pasos anteriores.
3. **`AZURE_VM_SSH_KEY`**: en tu computadora abre el archivo privado con un
   editor local (`~/.ssh/analogos_azure_deploy`), copia todo su contenido y
   pégalo en el campo del Secret. No compartas ni imprimas ese contenido en
   logs. La clave pública termina en `.pub` y no se pega en este Secret.
4. **`AZURE_VM_KNOWN_HOSTS`**: primero verifica la identidad SSH de la VM:
   - En Azure Portal usa la consola/Run Command de la VM para obtener la clave
     pública del servidor, por ejemplo:
     `sudo cat /etc/ssh/ssh_host_ed25519_key.pub`.
   - En tu equipo compara la huella de esa clave con la huella que presenta la
     VM. Para una clave pública guardada en `vm_host_ed25519.pub`, ejecuta
     `ssh-keygen -lf vm_host_ed25519.pub`.
   - Solo después de que coincidan, genera la línea conocida con
     `ssh-keyscan -p 22 -t ed25519 IP_O_DNS_DE_LA_VM`. `ssh-keyscan` por sí solo
     **no verifica** la identidad; la verificación previa es obligatoria.
   - Copia la línea resultante completa, que empieza con el host o
     `[host]:puerto`, y guárdala como `AZURE_VM_KNOWN_HOSTS`. Para el puerto
     estándar `22` normalmente aparece el host sin corchetes. Si usas otro
     puerto, debe aparecer `[IP_O_DNS]:PUERTO`.
5. **`GHCR_USERNAME` y `GHCR_PULL_TOKEN`**:
   - Usa la cuenta GitHub con acceso de lectura al paquete
     `ghcr.io/gabrielipc/no-sky-is-the-limit`.
   - En GitHub abre **Settings → Developer settings → Personal access tokens →
     Tokens (classic) → Generate new token (classic)**.
   - Ponle una nota identificable, elige una fecha de expiración y marca
     únicamente `read:packages`. Si el paquete es privado y pertenece a una
     organización, confirma que la cuenta/token tenga acceso a ese paquete y
     cumple las políticas de SSO de la organización, si aplican.
   - Genera el token y cópialo inmediatamente a `GHCR_PULL_TOKEN`; GitHub no
     volverá a mostrar su valor completo. Copia el nombre de la cuenta dueña del
     token a `GHCR_USERNAME`.
   - No marques `write:packages` ni `delete:packages` para esta descarga. Si el
     paquete es privado, puedes probar las mismas credenciales desde la VM con
     `docker login ghcr.io`; no las envíes por chat.

En la página **Actions secrets and variables**, para guardar un Secret, pulsa
**New repository secret**, escribe el nombre exacto de la tabla, pega el valor y
pulsa **Add secret**. Repite por cada uno. Para una Variable abre la pestaña
**Variables**, pulsa **New repository variable**, completa el nombre y valor y
pulsa **Add variable**.

El workflow usa `GITHUB_TOKEN` automáticamente para publicar la imagen; no crees
un token de publicación adicional. GHCR suele crear el paquete como privado.
El token de descarga se conserva en GitHub Secrets y el workflow inicia sesión
en GHCR durante el despliegue; al terminar cierra la sesión de Docker en la VM.

### Variables

| Nombre | Ejemplo | Uso |
|---|---|---|
| `AZURE_VM_SSH_PORT` | `22` | Puerto SSH de la VM. Opcional; si no existe, el workflow usa `22`. |
| `AZURE_VM_APP_DIR` | `/opt/analogos` | Ruta absoluta donde Actions copiará `docker-compose.yml` y creará `.env`. Obligatoria. |
| `AZURE_VM_APP_PORT` | `8000` | Puerto del host publicado hacia el puerto `8000` del contenedor. Opcional; predeterminado `8000`. |
| `ATLAS_RELEASES_PATH` | `/srv/analogos/releases/atlas30` | Ruta absoluta del volumen Atlas en la VM. Obligatoria. |

#### Cómo llenar cada Variable

1. `AZURE_VM_SSH_PORT`: escribe `22`, salvo que hayas configurado otro puerto
   SSH tanto en `sshd` como en la NSG.
2. `AZURE_VM_APP_DIR`: escribe `/opt/analogos`, igual a la ruta creada en la
   VM. Actions creará ahí el archivo Compose y `.env`.
3. `AZURE_VM_APP_PORT`: escribe `8000`, o el puerto que abriste para la app en
   la NSG. Si decides omitir la variable, asegúrate de que la NSG permita el
   puerto predeterminado `8000`.
4. `ATLAS_RELEASES_PATH`: escribe
   `/srv/analogos/releases/atlas30`, exactamente igual a la carpeta persistente
   creada en la VM.

Para crear cada una, abre la pestaña **Variables**, pulsa **New repository
variable**, escribe el nombre y valor, y guarda. Ambas rutas deben ser absolutas
y no contener espacios ni comillas. Los puertos deben ser números entre `1` y
`65535`.

Los dos directorios deben ser rutas absolutas sin espacios ni comillas. No agregues
al repositorio `.env` de producción, claves SSH, tokens, contraseñas ni datos
locales originales.

Antes de guardar `AZURE_VM_KNOWN_HOSTS`, obtén la clave pública del host por un
canal confiable (por ejemplo, la consola de Azure) y compara su huella. No uses
una salida de `ssh-keyscan` sin verificarla como si fuera identidad autenticada.
El workflow mantiene `StrictHostKeyChecking=yes`.

## Primera publicación y comprobación paso a paso

1. Guarda y verifica todos los Secrets y Variables de las secciones anteriores.
2. Desde tu equipo, confirma la conexión SSH como `deploy` y la ejecución de
   `docker compose version`, usando la clave privada de despliegue.
3. Confirma que las reglas de entrada de la NSG permiten el SSH del runner y que
   la ruta del Atlas existe y tiene propietario UID/GID `10001`.
4. Sube la configuración en una pull request hacia `main` y espera a que pasen
   `Backend tests`, `Frontend tests and build` y `Docker image smoke test`.
5. Fusiona la pull request en `main`. En **Actions**, abre la ejecución creada
   por el `push` y revisa en orden `Publish image to GHCR` y `Deploy production
   on Azure VM`. El despliegue solo empieza si las comprobaciones y la
   publicación de imagen terminan correctamente.
6. Si falla el paso **Validate deployment settings and prepare SSH**, revisa el
   nombre y tipo de cada Secret/Variable que reporta el error; las credenciales
   requeridas deben estar en **Secrets** y las rutas/puertos en **Variables**.
   Después puedes seleccionar **Re-run failed jobs** en esa ejecución.
7. Si la validación pasa pero falla la conexión, revisa IP/DNS, puerto SSH,
   regla NSG, permisos de la clave y coincidencia de `AZURE_VM_KNOWN_HOSTS`.
   Si falla el `docker pull`, verifica `GHCR_USERNAME`, el PAT y el acceso de la
   cuenta al paquete.
8. Al terminar, abre:
   - `http://<IP-o-DNS-de-la-VM>:8000/` para el frontend.
   - `http://<IP-o-DNS-de-la-VM>:8000/docs` para Swagger.
   - `http://<IP-o-DNS-de-la-VM>:8000/openapi.json` para comprobar el contrato
     OpenAPI.
9. En la VM comprueba estado y logs:

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
