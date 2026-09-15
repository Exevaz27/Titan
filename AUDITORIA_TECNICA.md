# Auditoría técnica de Titán

**Fecha:** 2026-09-14  
**Alcance:** código Python propio, servidor REST/WebSocket, satélite Windows, herramientas de sistema, audio, memoria, Telegram, TV, configuración, pruebas y documentación.

## 1. Resumen ejecutivo

Titán es un asistente distribuido: la PC Linux DDR3 aloja el cerebro, el servidor y la memoria; la PC Windows actúa como satélite ejecutor; el HUD, Telegram, audio y TV son interfaces o integraciones adicionales.

La revisión detectó una superficie de control remoto amplia y originalmente sin autenticación suficiente. También encontró ejecución mediante shell, acciones sensibles sin confirmación central, rutas de archivos sin confinamiento, extracción ZIP vulnerable, falsos éxitos RPC, persistencia destructiva de `.env` y discrepancias entre documentación e implementación.

Se aplicaron correcciones iniciales de seguridad y robustez. El proyecto aún no debe considerarse listo para exposición fuera de una LAN controlada hasta completar las pruebas de integración y revisar todos los permisos de despliegue.

## 2. Correcciones aplicadas

- Autenticación por `TITAN_API_TOKEN` para API y WebSocket.
- Token separado `TITAN_SATELLITE_TOKEN` para el satélite Windows.
- Cookie de sesión para que el HUD reutilice el token recibido inicialmente.
- Límites para prompts, imágenes Base64, bloques PCM y micrófonos simultáneos.
- Eliminación de `shell=True` del lanzador de aplicaciones.
- Eliminación de `shell=True` del controlador ADB de TV.
- Lista explícita de aplicaciones de sistema permitidas.
- Validación contra traversal al extraer ZIP.
- Confirmación central para apagado, reinicio, suspensión, papelera, archivos y procesos.
- Estados RPC diferenciados: `success`, `timeout`, `pending`, `error` y `warning`.
- Falsos éxitos de volumen y mute reemplazados por errores explícitos.
- Persistencia de `GEMINI_API_KEY` sin sobrescribir el resto de `.env`.
- Escritura atómica de la modificación de `.env`.
- Separación de dependencias Linux/Windows y arranques por rol.
- `run_linux.sh` para el núcleo central y `run.bat` para el satélite Windows.
- Plantilla `titan.service.example` para arranque persistente en Linux.
- Registro individual de dispositivos por rol con revocación y hashes de tokens.
- Gestor visual local `/admin` para listar, autorizar y revocar dispositivos sin comandos repetitivos.
- Pruebas unitarias de tokens, roles, cookies, loopback y rutas ZIP.

## 3. Hallazgos y riesgo residual

### Crítico

#### Autorización distribuida todavía pendiente de prueba real

La capa de autenticación está implementada en `core/security.py`, `server/web_server.py` y `desktop/remote_satellite.py`, pero las pruebas REST/WebSocket reales están condicionadas a tener instaladas las dependencias del servidor.

**Riesgo:** una configuración incorrecta de variables de entorno o de proxies puede dejar el sistema inaccesible o autorizar más roles de los deseados.

**Acción:** ejecutar pruebas de integración con FastAPI y probar un cliente HUD, un satélite válido, un cliente sin token y un satélite falso.

### Alto

#### Confirmación dependiente del flujo conversacional

La confirmación se centralizó en `brain/local_intents.py`, pero debe probarse que una orden de Gemini no pueda ejecutar directamente la acción pendiente desde otro canal o tarea concurrente.

**Acción:** añadir identificador de solicitud, vencimiento de confirmación, origen autorizado y bloqueo contra doble ejecución.

#### Rutas de archivos todavía no confinadas globalmente

Las operaciones de copiar, mover, crear, leer, abrir y enviar archivos aún aceptan rutas amplias. La protección ZIP no sustituye una política general de rutas.

**Acción:** implementar un servicio de rutas permitidas y proteger carpetas del sistema, `.env`, bases de datos y configuración.

#### Memoria y embeddings

`core/memory.py` puede enviar texto a Google Embeddings. Esto requiere una política por categoría para distinguir información privada y datos autorizados para nube.

**Acción:** añadir consentimiento, clasificación de memoria, modo sólo local y borrado completo.

### Medio

- Las pruebas de integración del servidor están preparadas, pero actualmente se omiten por dependencias ausentes.
- El proyecto conserva muchos `except Exception` amplios que dificultan diagnóstico.
- Existen operaciones de red y subprocessos síncronos dentro de flujos asíncronos.
- El estado global complica pruebas y recuperación parcial.
- La documentación maestra menciona módulos, endpoints y tablas que no coinciden exactamente con el árbol actual.
- La disponibilidad real de audio, ADB, Telegram, Edge-TTS y Gemini depende del entorno externo.

## 4. Estado de pruebas

Ejecutado correctamente:

- Compilación del código propio con `compileall`.
- Suite `tests.test_security`: 5 pruebas correctas.
- Pruebas de límites de rutas y tokens.
- Diagnósticos del editor sin errores en archivos modificados.
- Búsqueda global en código propio sin usos restantes de `shell=True`.

Pendiente por entorno:

- Pruebas FastAPI con `TestClient`.
- Pruebas reales WebSocket.
- Pruebas de `google-genai` y persistencia de API key.
- Pruebas de audio y Edge-TTS.
- Pruebas Windows de volumen, procesos, archivos y energía.
- Pruebas ADB contra la TV real.

## 5. Decisiones de diseño adoptadas

- Titán permanece en la PC Linux DDR3 siempre encendida.
- Windows continúa como satélite remoto para no cargar la PC principal.
- El acceso previsto es LAN autorizada, no Internet abierta.
- Las acciones sensibles usan un perfil configurable y requieren confirmación por defecto.
- La memoria cloud sólo debe utilizarse con consentimiento.

## 6. Recomendación de operación actual

Antes de abrir el servicio en una red doméstica, configurar tokens fuertes y diferentes:

```env
TITAN_API_TOKEN=token_largo_para_hud_y_api
TITAN_SATELLITE_TOKEN=token_largo_distinto_para_windows
```

No incluir `.env` en repositorios, copias públicas ni capturas. No exponer el puerto 8000 a Internet. Probar primero sólo desde localhost y después desde un dispositivo LAN controlado.

## 7. Conclusión

La base de seguridad mejoró sustancialmente, pero el proyecto todavía necesita pruebas de integración, confinamiento general de rutas, control de permisos por acción, política de privacidad de memoria y actualización de documentación antes de considerarse estable para uso remoto continuo.
