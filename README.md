# 🇦🇷 Che Asistente // Asistente de Voz para Windows con Gemini API

Asistente de voz local modular para Windows con tonada y personalidad argentina de confianza, accionado por la API de Google Gemini (vía `google-genai` con Function Calling), síntesis de voz neural ultra-fluida con `edge-tts` (`es-AR-TomasNeural`), control total de Windows (aplicaciones nativas y portables, archivos y sistema) y un servidor web local con WebSockets para emitir el estado a una pantalla secundaria (tablet, celular o segundo monitor).

---

## 🚀 Arquitectura y Arranque

Titán se ejecuta en la PC Linux DDR3, que permanece encendida y aloja el núcleo, el servidor web, Gemini, la memoria, Telegram y el control de la TV. La PC Windows no ejecuta el núcleo: funciona como satélite opcional para acciones locales de Windows.

### Núcleo Linux DDR3

En Linux, instalá y ejecutá:

```bash
./run_linux.sh
```

Para producción, usá [titan.service.example](titan.service.example) como plantilla de `systemd`.

### Satélite Windows

En Windows, ejecutá `run.bat`. Ese script sólo inicia `titan_satellite.py` y se conecta al servidor Linux configurado en `TITAN_SERVER_HOST`.

Si Windows está apagado, Titán sigue disponible desde la DDR3 para Telegram, HUD, memoria, TV y servicios centrales; únicamente quedan fuera de línea las acciones que requieren esa PC.

### Encender Windows remotamente

Titán puede enviar Wake-on-LAN desde Linux. Configurá en `.env` la MAC de la interfaz Ethernet de Windows:

```env
WINDOWS_MAC_ADDRESS=AA:BB:CC:DD:EE:FF
WINDOWS_WOL_BROADCAST=255.255.255.255
```

En Windows hay que activar Wake-on-LAN en BIOS/UEFI y en el adaptador de red, y dejar la PC conectada a la corriente, preferentemente por cable Ethernet. La orden es “prendé la PC Windows”. Wake-on-LAN confirma que la señal fue enviada, no que el equipo terminó de iniciar.

### Autorizar dispositivos

La DDR3 mantiene el registro de dispositivos autorizados en `authorized_devices.json`. Generá las credenciales sólo desde la DDR3:

```bash
python scripts/manage_devices.py enroll hud-celular --role api
python scripts/manage_devices.py enroll windows-satellite --role satellite
python scripts/manage_devices.py list
python scripts/manage_devices.py revoke hud-celular
```

El comando `enroll` muestra el token una sola vez. Para el HUD se abre la dirección inicial con `token` y `device_id`; para el satélite se configuran `TITAN_DEVICE_ID` y `TITAN_SATELLITE_TOKEN` en su `.env`. Un dispositivo revocado deja de poder usar Titán aunque conserve su token.

También podés abrir el gestor visual directamente en la DDR3:

```bash
chmod +x scripts/abrir_gestor_dispositivos.sh
./scripts/abrir_gestor_dispositivos.sh
```

La pantalla `/admin` muestra los dispositivos registrados y las conexiones activas. Desde ahí podés autorizar un HUD o un satélite, copiar su token una sola vez y revocarlo con un botón.

#### ¿Qué ocurre con un dispositivo no autorizado?

Puede estar conectado a la red Wi-Fi, pero Titán rechaza su acceso. No puede consultar el estado, enviar órdenes, usar el micrófono, recibir eventos, capturar pantalla/cámara ni registrarse como satélite. El servidor cierra su WebSocket con código `1008` y la API responde `401`.

## 🚀 Inicio Rápido

### 1. Iniciar con un solo clic
Simplemente hacé doble clic en:
```bat
run.bat
```
*(Si es la primera vez, configurará automáticamente el entorno virtual `.venv` y descargará las dependencias)*.

### 2. Configurar tu API Key de Gemini
Obtené tu clave gratuita en [Google AI Studio](https://aistudio.google.com/) y podés:
- Colocarla en el archivo `.env`:
  ```env
  GEMINI_API_KEY=tu_api_key_aqui
  ```
- O ingresar a la interfaz web y hacer clic en el botón de engranaje ⚙️ para guardarla directamente.

---

## 📱 Pantalla Secundaria (HUD Futurista)
Abrí en el navegador de tu computadora, tablet o celular (en la misma red Wi-Fi):
```
http://localhost:8000
```
O desde otro dispositivo:
```
http://[IP-DE-TU-COMPU]:8000
```

### Funciones del HUD:
- **Orbe Reactivo**: Cambia de color y animaciones según el estado del asistente (espera, escuchando, pensando, ejecutando herramientas, hablando).
- **Visualizador de Ondas**: Anima los anillos sonoros en tiempo real según el volumen detectado.
- **Feed en Vivo**: Muestra la transcripción de tus órdenes, las respuestas del asistente y el detalle de cada acción realizada.
- **Botón "Hablar Ahora" (Push-to-Talk)**: Tocá para activar la escucha instantáneamente.
- **Botón "Probar Voz"**: Escuchá una frase de prueba con tonada argentina.
- **Barra de Comandos**: Podés escribir órdenes manuales sin necesidad de hablar.

---

## 🎙 Métodos de Activación

1. **Por Voz (Palabras Clave / Wake-Word)**:
   - *"Che asistente"*
   - *"Asistente"*
   - *"Che gemini"*
   - *"Escuchame"*
   - *(Podés decir la palabra clave sola o seguida de la orden: "Che asistente, abrí Spotify")*.

2. **Atajo de Teclado Global (Hotkey)**:
   - Presioná **`Ctrl + Espacio`** (o **`Alt + A`**) desde cualquier ventana o juego para que el asistente comience a escuchar de inmediato.

3. **Botón en Pantalla Secundaria**:
   - Tocá el botón grande de micrófono o el orbe central en el panel web.

---

## 📁 Catálogo de Programas Portables (`apps_catalog.json`)

Para que el asistente reconozca tus programas portables o ejecutables en distintos discos (`C:`, `D:`, `E:`), edita el archivo `apps_catalog.json`:

```json
{
  "apps": {
    "inkscape": "E:\\Programas\\Inkscape\\bin\\inkscape.exe",
    "photoshop": "D:\\Diseño\\Photoshop.exe",
    "juego": "E:\\Juegos\\MiJuego\\juego.exe",
    "blender": "C:\\Portables\\Blender\\blender.exe"
  },
  "carpetas_escaneo_portable": [
    "E:\\Programas",
    "C:\\Portables",
    "D:\\Portables"
  ]
}
```

*¡También podés pedirle por voz que agende un programa!*
> *"Che, guardate el ejecutable de Blender en C:\Portables\blender.exe con el nombre blender"*

---

## 🛠 Comandos y Capacidades del Asistente

- **Abrir Programas**: *"Abrí Chrome"*, *"Poné Inkscape"*, *"Abrí la calculadora"*, *"Abrí el Bloc de notas"*.
- **Buscar Archivos**: *"Buscame la factura de marzo en formato PDF"*, *"Fijate dónde dejé las fotos del viaje"*.
- **Accionar sobre Archivos**:
  - *"Abrí el archivo reporte.xlsx"*
  - *"Mostrame en la carpeta el archivo notas.txt"*
  - *"Mandá este archivo a la papelera"* *(Usa papelera de reciclaje segura, nada se borra permanentemente sin posibilidad de recuperarlo)*.
  - *"Leeme qué dice el archivo tareas.txt"*
- **Control de Volumen y Medios**:
  - *"Subí el volumen"* / *"Bajá el volumen"* / *"Poné el volumen al 50%"* / *"Muteá el audio"*.
  - *"Pausá la música"* / *"Siguiente canción"* / *"Canción anterior"*.
- **Sistema**:
  - *"Minimizá todo"* / *"Mostrame el escritorio"*.
  - *"Bloqueá la compu"*.
  - *"Sacá una captura de pantalla"*.
  - *"¿Cómo viene la memoria y el espacio en los discos?"*

---

## 🏗 Arquitectura del Proyecto

```
asistente-argen-win/
├── .env.example / .env        # Claves de API y configuración
├── requirements.txt           # Dependencias probadas (Python 3.11)
├── install.bat / run.bat      # Scripts de inicio de 1 clic
├── main.py                    # Orquestador asíncrono
├── config.json                # Configuración persistente (voz, palabras clave, etc.)
├── apps_catalog.json          # Catálogo de rutas de ejecutables y portables
├── core/                      # Logger, Config y State Manager (Event Bus)
├── audio/                     # Listener de micrófono, Wake-Word y Edge-TTS
├── brain/                     # Gemini API, Function Calling y Persona Argentina
├── tools/                     # Lanzador de apps, gestor de archivos, volumen y hotkeys
├── server/                    # Servidor FastAPI, WebSocket hub y HUD Web
└── tests/                     # Suite de pruebas unitarias
```
