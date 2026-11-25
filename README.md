# ✂️ Clipper en Vivo — clips virales de La Casa de Alofoke 3

App local (corre en tu PC) para sacar clips **mientras el directo de YouTube está pasando**
y exportarlos en vertical 9:16 listos para TikTok, Reels y Shorts.

## Cómo funciona
1. Pegas el link del directo y le das **● Iniciar grabación**. La app va guardando los
   últimos 30 minutos en pedacitos de 4 s (lo viejo se borra solo, no llena el disco).
2. Cuando pasa algo fuerte, aprietas **30 s / 1 min / 2 min / 5 min** (o las teclas `1` `2` `3` `4`).
3. La captura se abre en el editor: marcas **entrada** (`I`) y **salida** (`O`) exactas,
   escribes el hook, eliges formato y si quieres subtítulos automáticos.
4. **🎬 Renderizar** → aparece en "Clips listos" con botón de descarga y un copy con hashtags.

También puedes sacar tramos de un video ya subido o de la repetición del directo
("Capturar de un video ya subido", con desde/hasta tipo `1:02:10`).

## Instalación
**Windows:** doble clic en `iniciar.bat` (instala ffmpeg y Deno con winget la primera vez,
luego cierra y vuelve a abrirlo). Necesitas [Python 3.10+](https://www.python.org/downloads/)
con la casilla "Add to PATH".

**Mac / Linux:** `./iniciar.sh` (necesitas ffmpeg instalado).

Se abre sola en el navegador: http://127.0.0.1:5055

### Subtítulos automáticos (opcional)
```
pip install -r requirements-subtitulos.txt
```
(dentro del `.venv`). La primera vez descarga el modelo Whisper "small" (~500 MB).
Salen palabra por palabra, en mayúsculas, con la palabra que se está diciendo en amarillo.
Para más precisión: `set WHISPER_MODEL=medium` antes de iniciar (más lento).

## ⭐ Plantillas PRO de hooks (15 categorías)

![Lámina de plantillas](plantillas/lamina.png)

Polémica · Curiosidad · Noticias RD · Debate · Viral · Actualidad RD · Humor/Sarcasmo · Impacto ·
Verdad incómoda · Motivacional · Revelación · Alerta · Reflexión · Tendencia · Local/Cotidiano.

**En la app** (pestaña "⭐ Plantillas PRO"), cada plantilla deja cambiar: texto del hook,
palabra resaltada (`*así*`), color de resaltado, encabezado (o quitarlo), icono/emoji
(`-` = ninguno), fondo del panel, posición y tamaño. Funciona en 9:16, 1:1 y 16:9.

**Fuera de la app** (CapCut, Premiere, Canva): en `plantillas/NN-categoria/` hay PNG
transparentes listos para poner encima del video (`vertical.png` 1080×1920, `cuadrado.png`
1080×1080, `horizontal.png` 1920×1080 y `hook.png` recortado). Para crear uno con tu texto:
```
python generar_plantillas.py --cat viral --texto "SE ARMÓ EL *LÍO* 😱" --encabezado "LA CASA DE ALOFOKE" --color "#22D3EE"
```
Para crear categorías nuevas o cambiar colores/iconos por defecto, edita `CATS` en `templates.py`.

## ⚡ Clips más rápido

- **📍 Marcar momento (tecla `M`)**: mientras ves el directo, aprieta `M` cuando pase algo. Queda
  guardado y luego lo conviertes en clip (con los segundos de "antes" y "después" que elijas).
- **🔎 Buscar tomas importantes**: analiza los últimos 5–30 minutos del directo (o una captura) y
  encuentra los picos de audio: gritos, discusiones, risas, aplausos. Las mejores (🔥🔥🔥) quedan
  marcadas solas.
- **🎬 Crear varios clips a la vez**: marca con ✔ los momentos y aprieta un botón: se capturan y
  renderizan todos con la configuración del editor (hook, plantilla, formato, subtítulos, marca de
  agua, portada). Se renderizan `RENDER_WORKERS` a la vez (2 por defecto) y el resto espera en cola.
- **Velocidad "Rápido"** (por defecto) renderiza más ligero; "Máxima calidad" para clips especiales.

## 🖼 Portada, 💬 subtítulos y 💧 marca de agua

- **Portada**: elige un fotograma ("Usar fotograma actual") y escribe el texto. "Crear portada" saca un
  JPG; "Poner la portada al inicio" la pega como primer cuadro del video (0.35 s), que es lo que
  TikTok toma como portada, y se usa también como portada del Reel en Instagram.
- **Subtítulos** palabra por palabra en 4 estilos (amarillo, verde, caja negra, blanco) y 3
  posiciones. Necesitan `requirements-subtitulos.txt` (el Docker ya los trae).
- **Marca de agua**: texto (@usuario) y/o logo (PNG transparente ideal), con posición, tamaño y
  transparencia. Las posiciones de abajo dejan libre la zona de botones de TikTok/Reels.

## 🚀 Publicar en redes desde Clipper

Cada clip listo tiene:
- **📲 Compartir**: en el celular abre el menú de compartir del teléfono → TikTok, Instagram,
  Facebook, WhatsApp… (copia el copy al portapapeles). No necesita configurar nada.
- **🚀 Publicar**: sube directo a tus cuentas conectadas.

| Red | Cómo se publica |
|---|---|
| Facebook | Video en tu **página** (no perfil personal). |
| Instagram | **Reel** en tu cuenta profesional vinculada a la página. Solo con la app en internet. |
| TikTok | A tus **borradores** (terminas en la app de TikTok) o directo. Las apps de TikTok sin auditar solo pueden publicar en privado. |

### Opción A — botones "Conectar" (recomendado)
1. **Meta**: en [developers.facebook.com](https://developers.facebook.com) crea una app tipo
   "Business", agrega *Facebook Login for Business* e *Instagram Graph API*, y registra la dirección
   de retorno `https://TU-APP/oauth/meta/callback`.
2. **TikTok**: en [developers.tiktok.com](https://developers.tiktok.com) crea una app con
   *Login Kit* y *Content Posting API* (permisos `video.upload` y `video.publish`), con retorno
   `https://TU-APP/oauth/tiktok/callback`.
3. En Railway → Variables: `PUBLIC_URL=https://TU-APP`, `META_APP_ID`, `META_APP_SECRET`,
   `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`.
4. En Clipper → **Cuentas para publicar** → Conectar.

### Opción B — pegar tokens
- Facebook/Instagram: en el [Explorador de la Graph API](https://developers.facebook.com/tools/explorer)
  genera un token de usuario con `pages_show_list, pages_manage_posts, pages_read_engagement,
  instagram_basic, instagram_content_publish`, alárgalo en el *Depurador de tokens* ("Extender") y
  consulta `me/accounts`: copia el `id` y el `access_token` de tu página.
- TikTok: token de acceso de tu app de desarrollador.

Los tokens se guardan en el servidor (`cuentas.json` dentro de `/data`) y nunca se muestran en la app.

## Opciones del editor
- **Fondo desenfocado**: el video completo al centro y el mismo video borroso detrás.
- **Pantalla completa (recorte)**: llena la pantalla; mueve "posición" para enfocar a la persona
  que está hablando (izquierda / centro / derecha) y usa zoom si hace falta.
- **Hook** con 10 estilos (TikTok clásico, Viral borde, Amarillo bomba, Última hora, Dos tonos,
  Barra negra, Neón, Fuego, Cómic, Limpio), vista previa en vivo sobre el fotograma real,
  posición arriba/centro/abajo y tamaño. Escribe `*entre asteriscos*` las palabras a resaltar
  en color. Los emojis salen a color.

  ![Estilos de hook](docs/estilos-hook.png)
- **Marca de agua** con tu @.
- Para agregar estilos nuevos edita `STYLES` en `hooks.py` (fuentes en `fonts/`, licencia OFL).

## Ajustes (variables de entorno)
| Variable | Por defecto | Qué hace |
|---|---|---|
| `BUFFER_MIN` | 30 | Minutos del directo que se guardan |
| `CALIDAD` | 1080 | Altura máxima a grabar (720 si tu internet es lento) |
| `WHISPER_MODEL` | small | tiny / base / small / medium |
| `PORT` | 5055 | Puerto de la app |

## Problemas comunes
- **"No se pudo grabar el directo"**: actualiza yt-dlp (`pip install -U "yt-dlp[default]"`),
  asegúrate de tener Deno instalado y revisa `buffer/grabadora.log`.
- **El directo se ve en la app pero no se graba**: el reproductor es solo para mirar; la
  grabación depende de yt-dlp.
- Los clips quedan en la carpeta `clips/`.

## 🌐 Ponerla en línea (acceder desde el celular o cualquier PC)

La app ya viene lista para servidor (`Dockerfile`). Necesita un servidor **encendido 24/7**
(la grabación es un proceso continuo), así que **no sirve en Vercel/Netlify**; usa Railway o Render.

### Opción A — Railway (la más fácil, ~5 US$/mes)
1. Sube esta carpeta a un repositorio de GitHub (privado).
2. En [railway.com](https://railway.com) → **New Project → Deploy from GitHub repo** → elige el repo.
3. En **Variables** agrega: `APP_PASSWORD` = una contraseña fuerte.
4. En **Settings → Volumes** crea un volumen montado en `/data`.
5. En **Settings → Networking → Generate Domain**. Listo: entras con cualquier usuario + tu contraseña.

### Opción B — Render (~7–25 US$/mes)
Sube el repo a GitHub → en [render.com](https://render.com) **New → Blueprint** → elige el repo
(usa `render.yaml`, que ya crea el disco y una contraseña aleatoria; la ves en *Environment*).

### Opción C — Tu propio VPS (Hetzner, DigitalOcean, Contabo…)
```
docker build -t clipper .
docker run -d --restart unless-stopped -p 80:8080 -v clipper-data:/data -e APP_PASSWORD=tuClave clipper
```

### ⚠️ Muy importante: YouTube bloquea servidores
Desde servidores en la nube, YouTube suele responder *"Sign in to confirm you're not a bot"*.
Solución: en la app abre **🍪 Cookies de YouTube** y sube un `cookies.txt` exportado con la
extensión "Get cookies.txt LOCALLY" (usa una **cuenta secundaria**, no la principal).
Si aun así bloquea, usa un proxy residencial con la variable `YT_PROXY=http://usuario:clave@host:puerto`.
Las cookies vencen cada cierto tiempo: si vuelve el error, súbelas de nuevo.

### Variables para servidor
| Variable | Qué hace |
|---|---|
| `APP_PASSWORD` | **Obligatoria en línea.** Contraseña para entrar |
| `DATA_DIR` | Carpeta de datos (en Docker ya es `/data`) |
| `YT_COOKIES` | Alternativa a subir cookies: el contenido de cookies.txt |
| `YT_PROXY` | Proxy para yt-dlp |
| `RENDER_WORKERS` | Clips que se renderizan a la vez (2; súbelo si el servidor tiene más CPU) |
| `PUBLIC_URL` | Dirección pública de la app (para Instagram y los botones Conectar) |
| `META_APP_ID` / `META_APP_SECRET` | App de Meta para conectar Facebook/Instagram |
| `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` | App de TikTok para conectar TikTok |

Subtítulos en servidor: el Docker los incluye con el modelo `base` (necesita ~2 GB de RAM).
Para un plan más barato, construye sin ellos: `docker build --build-arg SUBTITULOS=0 .`

## Ojo con los derechos
El contenido de La Casa de Alofoke es de sus dueños. Los canales de clips suelen funcionar
porque el canal lo permite o porque agregan valor (comentario, reacción, edición). Si te
llegan reclamos de copyright en TikTok/YouTube, el video se puede caer o la cuenta recibir
strikes; revisa las reglas del canal sobre clips.
