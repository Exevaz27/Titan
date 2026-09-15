# Plan de trabajo de Titán

**Objetivo:** convertir Titán en un asistente distribuido seguro y mantenible, con la PC Linux DDR3 como nodo central y Windows como satélite ejecutor autenticado.

## Principios

1. La PC Linux conserva el cerebro, servidor y memoria.
2. Windows sólo ejecuta acciones autorizadas localmente.
3. Ninguna acción destructiva se ejecuta sin política y confirmación.
4. Todo resultado remoto debe estar confirmado por el satélite.
5. Las pruebas automatizadas preceden a la exposición en LAN.
6. La privacidad de memoria se decide por categoría, no por accidente.

## Estado actual

Completado:

- Separación del núcleo Linux y satélite Windows.
- Dependencias y lanzadores específicos por plataforma.
- Plantilla systemd para la PC DDR3.
- Registro individual de dispositivos y revocación por rol.
- Gestor visual local para administrar dispositivos con botones.
- Persistencia correcta de configuración.
- Autenticación base API/WebSocket/satélite.
- Eliminación de `shell=True` en lanzador y TV.
- Protección de extracción ZIP.
- Confirmaciones de acciones críticas.
- Estados RPC sin falsos éxitos.
- Límites de entrada para servidor.
- Pruebas unitarias de primitivas de seguridad.
- Documentación inicial de auditoría.

Pendiente:

- Ejecutar pruebas con dependencias completas.
- Confinar todas las rutas de archivos.
- Formalizar permisos y confirmaciones por origen.
- Añadir auditoría de acciones.
- Separar roles del WebSocket.
- Política de privacidad de memoria.
- Actualizar documentación histórica y contratos.

## Fase 1: Entorno reproducible

**Tareas**

- Crear un entorno virtual Windows real con `Scripts\\python.exe`.
- Instalar `requirements.txt`.
- Verificar versiones de Python, FastAPI, Pydantic y websockets.
- Documentar instalación Linux y Windows por separado.
- Añadir un comando de diagnóstico que compruebe dependencias sin arrancar hardware.

**Criterio de aceptación**

`run.bat`, `python -m unittest discover -s tests -v` y `compileall` funcionan en una instalación limpia compatible.

## Fase 2: Pruebas de autenticación

**Tareas**

- Ejecutar `tests/test_server_security.py` con FastAPI instalado.
- Probar API sin token, token inválido y token válido.
- Probar `/ws` con HUD autorizado.
- Probar registro de satélite con token API, token de satélite y token inválido.
- Probar `/ws/mic` con límite de clientes y bloques demasiado grandes.
- Verificar que los tokens no aparezcan en logs ni respuestas.

**Criterio de aceptación**

Un cliente desconocido no puede ejecutar API, RPC, audio, cámara, pantalla ni cambios de configuración.

## Fase 3: Política de acciones

**Tareas**

Crear `core/action_policy.py` con:

- Clasificación de riesgo.
- Origen de la solicitud.
- Permiso requerido.
- Confirmación obligatoria.
- Tiempo de expiración.
- Identificador único de operación.
- Prevención de doble ejecución.

**Acciones críticas**

- Apagar, reiniciar y suspender.
- Vaciar papelera.
- Mover, sobrescribir o enviar archivos.
- Finalizar procesos.
- Activar vigilancia.
- Capturar cámara o pantalla.
- Cambiar credenciales o configuración.

**Criterio de aceptación**

La misma política se aplica a voz, HUD, Telegram, Gemini y RPC.

## Fase 4: Confinamiento de archivos

**Tareas**

- Definir raíces permitidas por operación.
- Bloquear `.env`, bases de datos, configuración y claves.
- Resolver rutas con `Path.resolve()`.
- Rechazar enlaces simbólicos que salgan de la raíz permitida.
- Exigir confirmación para mover, sobrescribir o enviar.
- Añadir pruebas de traversal, rutas UNC, rutas absolutas y enlaces.

**Criterio de aceptación**

Ninguna herramienta puede leer, modificar o enviar una ruta fuera de su política.

## Fase 5: RPC y satélite Windows

**Tareas**

- Separar WebSocket HUD y WebSocket satélite.
- Mantener token específico por dispositivo.
- Añadir heartbeat y expiración de registro.
- Rechazar múltiples satélites ambiguos o seleccionar uno explícitamente.
- Firmar o correlacionar cada RPC con sesión y dispositivo.
- Registrar resultado real, timeout y cancelación.
- Añadir modo simulación para pruebas sin Windows.

**Criterio de aceptación**

Toda acción remota tiene origen, destino, identificador, timeout, resultado y auditoría.

## Fase 6: Robustez asíncrona

**Tareas**

- Mover subprocessos y red bloqueante a ejecutores.
- Separar comandos urgentes de tareas largas.
- Permitir cancelar generación, TTS, RPC y búsqueda.
- Añadir límites de cola y backpressure.
- Incorporar circuit breaker para Gemini, Telegram, ADB y STT.
- Evitar que una orden lenta bloquee “pará”, mute o emergencia.

**Criterio de aceptación**

El HUD y las interrupciones responden aunque Gemini, ADB o una herramienta tarde o falle.

## Fase 7: Privacidad y memoria

**Tareas**

- Añadir clasificación `local`, `cloud_allowed` y `private`.
- Pedir consentimiento para embeddings cloud.
- Implementar búsqueda local para datos privados.
- Cifrar memoria sensible en reposo.
- Añadir exportación y borrado completo.
- Documentar retención y destino de cada dato.

**Criterio de aceptación**

El usuario puede saber qué se guarda, dónde se guarda, qué se envía y cómo borrarlo.

## Fase 8: Observabilidad

**Tareas**

- Correlation ID por comando.
- Logs estructurados sin secretos.
- Historial de acciones y usuario/origen.
- Métricas de latencia STT, Gemini, TTS, RPC y ADB.
- Health checks por subsistema.
- Alertas de reconexión y fallos repetidos.

**Criterio de aceptación**

Un fallo puede diagnosticarse con logs y métricas sin reproducirlo inmediatamente.

## Fase 9: Documentación y contratos

**Tareas**

- Actualizar `README.md`.
- Corregir `DOCUMENTO_MAESTRO.md` para reflejar archivos existentes.
- Documentar endpoints reales, autenticación y roles.
- Documentar tablas SQLite reales.
- Eliminar promesas de módulos inexistentes.
- Añadir guía de recuperación y rotación de tokens.

**Criterio de aceptación**

La documentación coincide con el árbol, configuración y comportamiento reales.

## Fase 10: Nuevas funciones

Sólo después de las fases anteriores:

- Panel de dispositivos autorizados.
- Confirmación visual en HUD y Telegram.
- Modo simulación y pruebas de extremo a extremo.
- Backup y restauración de memoria.
- Perfiles de permisos por usuario/dispositivo.
- Automatizaciones programadas con límites.
- Modo emergencia local.
- Control de cuota para Gemini, imágenes y STT.

## Estrategia de pruebas

### Unitarias

- Seguridad de tokens.
- Validación de rutas.
- Política de acciones.
- Confirmaciones y expiración.
- Persistencia `.env`.
- Estados RPC.
- Resolución de aplicaciones y canales.

### Integración

- REST con TestClient.
- WebSocket HUD.
- WebSocket satélite.
- Micrófono PCM.
- Reconexión y heartbeat.
- Mocks de Gemini, Telegram, TTS y ADB.

### Seguridad negativa

- Token ausente, inválido y cruzado entre roles.
- Payload excesivo.
- ZIP traversal.
- Shell injection.
- Rutas UNC y traversal.
- RPC falso.
- Repetición de confirmación.
- Doble ejecución por timeout.

### Hardware

- Windows real: volumen, archivos, procesos, energía y captura.
- Linux real: servicio central, SQLite y red.
- TV real: ADB, encendido y canales.
- J2 real: audio, cámara y reconexión.

## Orden inmediato recomendado

1. Crear entorno Windows reproducible.
2. Ejecutar pruebas REST/WebSocket.
3. Implementar `action_policy.py`.
4. Confinar rutas de archivos.
5. Separar roles WebSocket.
6. Añadir auditoría y correlation IDs.
7. Definir privacidad de memoria.
8. Actualizar README y documento maestro.
9. Ejecutar pruebas de hardware.
10. Recién entonces agregar nuevas funciones.

## Decisiones pendientes del propietario

- Confirmar si la vigilancia J2 será sólo bajo demanda o continua.
- Definir qué operaciones de archivos se permiten sin confirmación.
- Decidir si el modo rebelde se conserva en producción.
- Definir tiempo de expiración de confirmaciones.
- Elegir si el HUD usa un token compartido o tokens por dispositivo.
- Confirmar retención y categorías autorizadas para embeddings cloud.
