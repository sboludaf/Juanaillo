# Validación del repositorio preparado para publicación

## Recorrido ordenador → placa, 25 de octubre de 2026

- `make check`: 114 pruebas Python (30 de herramientas/privacidad y ejemplo de comunicación, 14 del importador y diagnóstico USB, 35 del host y 35 de la web), además de los grupos nativos de firmware y commissioning. Todas pasan sin abrir puertos serie.
- El diagnóstico usa metadatos USB, permisos, enlaces de descriptores de procesos visibles y consultas de versión. Las ocho pruebas nuevas cubren adaptadores, driver asociado, ausencia de TTY, permisos de inspección, dispositivos que desaparecen y omisión de números de serie. No se instala ningún driver desde las pruebas.
- Las once pruebas del ejemplo verifican el modo serie offline, hash y perfil antes de abrir, envío exclusivo de INFO/STATUS, cierre sin repetición y HTTP de lectura sin reclamar control ni seguir redirecciones. El contrato serie se ensaya con transporte simulado, no con una placa real.
- Revisión independiente de los comandos y de los argumentos de la guía: separación de ROM, carga, arranque y consulta; hashes del plan, resultado y manifiesto; ruta principal de perfil 6 y exclusividad del puerto. Los enlaces Markdown relativos resuelven.
- Se exportó el árbol publicable a una carpeta temporal limpia, sin dependencias importadas, builds ni archivos privados. `make check` pasó también allí. Después se importaron los 41 archivos originales verificados para cada build y se compilaron `manual-hold` y `forward-3s` con GNU Arm 14.2.1 y newlib local.
- El BIN de `manual-hold` reconstruido en esa copia tiene **7444 bytes** y SHA256 `2f742d7f3f479d744e8ded4b70657313c9477230b02d565ea1c0082b5e0898a2`: coincide con la imagen de la corrección anterior. El ejemplo serie validó ese build en dry-run con un puerto ficticio, sin abrirlo.
- Las fuentes oficiales de drivers WCH y su selección se documentan por sistema. No se afirma una instalación o prueba física nueva en Windows/macOS y no se redistribuyen instaladores sin términos verificados.
- La revisión de árbol e historial no encontró los patrones configurados de datos privados. Se corrigieron las rutas de ejemplo a `.local/`; la grafía antigua también queda excluida y bloqueada por el comprobador público.

No se ha grabado, reiniciado ni movido una placa durante esta ampliación de documentación. La evidencia física anterior se conserva separada en las secciones siguientes y en [resultados reales](tested-results.md).

## Historial de validación anterior

Comprobación realizada el 24 de octubre de 2026, sin abrir puertos serie ni mover hardware durante el empaquetado.

- `make check`: 18 pruebas Python de herramientas/privacidad, 6 del importador y 35 del host, además de los grupos nativos de firmware y commissioning. Todas pasan.
- Cuatro skills validadas por formato y evaluadas por otro agente con casos de identificación/respaldo, repetición autorizada y publicación. Las referencias locales Markdown resuelven.
- Se copió exclusivamente el contenido seleccionado por Git a un árbol temporal limpio, sin vendor, builds, entorno privado ni datos del equipo. `make test` pasó en esa copia.
- En la copia limpia se importaron los 41 archivos necesarios desde el paquete original mediante checksums y se reconstruyó el firmware. El BIN fue idéntico al usado en los ensayos físicos: **7132 bytes**, SHA256 `8fc79c5214a0521d9351b803d8b5353a81b6df3d0bfbb7280648b7aac7fa5feb`.
- El escáner del árbol publicable y la revisión de contenido no encontraron las rutas o identificadores reales conocidos de la instalación de origen. La revisión no sustituye la comprobación de futuros cambios e historial antes de publicar.

En la entrega inicial, las herramientas ROM portables se comprobaron con un simulador y el firmware se relacionó con los ensayos por un BIN idéntico. Posteriormente, para activar la web, se probaron también las herramientas portables sobre la H60 real, según la ampliación siguiente.

Los artefactos de build, fuentes importadas, dumps y registros privados se mantienen fuera del historial público. El workflow de GitHub ejecuta únicamente comprobaciones offline; no reconstruye dependencias del fabricante ni acciona hardware.

## Ampliación: web local y perfil 5

- `make check` incluye además 18 pruebas del backend web y 7 grupos nativos de `manual-hold`; las pruebas Python suman 77. Todas pasan.
- UI comprobada con Playwright Chromium, en escritorio y móvil, contra simulación: presión y liberación, heartbeats, pérdida de foco, conexión, exclusión de otro navegador, recarga sin reanudar movimiento y límite de 10 s. Browser plugin no estaba disponible. Se contrastaron composición, tipografía, paleta, controles/espaciado y adaptación móvil con el concepto generado.
- Con las herramientas portables se obtuvieron dos lecturas reales concordantes de 512 KiB, se cargó exclusivamente el sector 0 y se verificó toda la Flash posterior. El resto se conservó y el arranque fue una fase explícita sin MOVE.
- Firmware `manual-hold`: BIN 7248 bytes, SHA256 `e6d399791ab7733f1e5ea2e4303740cc352a0abbdcc76084370b12b5846e502a`. El build independiente dio los mismos BIN/HEX.
- Se comprobó la cadena real WebSocket → backend → USB → MCU con pulsaciones breves de avance y retroceso. Los cuatro encoders fueron coherentes en ambos sentidos y se confirmó STOP/IDLE. Los datos numéricos están en `tested-results.md`; las claves, identificadores y registros permanecen privados.

## Ampliación: giros y perfil 6

- `manual-hold` añade órdenes lógicas de izquierda/derecha y un descriptor nuevo. Los nueve grupos nativos comprueban los cuatro patrones eléctricos/PWM, las 32 transiciones entre órdenes durante WAKE y RUNNING, la caducidad de MOVE y el límite absoluto compartido de 10 s.
- La compilación ARM genera un BIN de 7256 bytes, SHA256 `a6367b446f48201e441a4d5518bab7f93f5a3578410357b708ccea7ad6e4e282`; BIN y HEX se reprodujeron de forma independiente.
- Las 30 pruebas web cubren las cuatro órdenes, la trama de giro, rechazo del perfil 5 antes de MOVE, STOP antes de una intención nueva, cancelación de órdenes pendientes, exclusión de otro navegador, caducidad y límite compartido. Con las demás suites hay 89 pruebas Python, además de los grupos nativos.
- Playwright Chromium comprobó los cuatro botones, flechas/WASD, ratón y tacto, pulsaciones opuestas y parada al soltar, cancelar, perder captura o foco. Se usó únicamente simulación local; no había Browser plugin disponible. Las vistas 1440×1000, 1366×768, 390×844 y 320×780 no mostraron recortes ni errores de consola.
- Se preparó un plan local para modificar solo el sector 0, tomando como baseline el readback completo verificado del perfil 5. El dry-run verifica imagen, fuentes, artefactos y baseline sin abrir el puerto. Es un baseline procedente de una lectura anterior, no dos lecturas nuevas.
- Tras el encendido confirmado por el operador, se ejecutó ese plan: comparación viva completa, escritura solo del sector 0 y readback de 512 KiB idéntico a lo esperado, conservando sectores 1–7. SHA256 completo: `640605cd84df3b0978b4776867524c0042d1f875dc76074ef1fa00494be5bd4f`.
- Se comprobó el arranque del perfil 6, su descriptor, conexión real, WebSocket autenticado y STOP/IDLE. No se envió MOVE; la verificación física de giros sigue pendiente y no se atribuyen al nuevo perfil las pruebas motrices reales del anterior.

## Pulsaciones simultáneas

- El navegador registra todos los dedos, punteros y teclas. Un segundo control detiene el gesto; una liberación parcial o heartbeat anterior no lo reanuda. Para volver a mover deben soltarse todos los controles y recibirse la confirmación de STOP y un estado de reposo antes de una pulsación nueva.
- El backend trata un solapamiento válido como parada recuperable y conserva WebSocket y propietario. Direcciones inválidas, secuencias repetidas y fallos reales del firmware siguen siendo errores. Se conservan motivo y código del FAULT para diagnosticarlo antes de reiniciar.
- Las 35 pruebas web comprueban conflicto, liberación, continuación sin reconectar, cancelación mientras STOP está pendiente, rechazo de mensajes inválidos y registro de FAULT sin nonce. Con el resto de suites hay 94 pruebas Python.
- Playwright Chromium, solo contra simulación, comprueba dos dedos reales (opuestos y sobre el mismo botón), dos teclas, entradas mixtas, liberación parcial y tercer control, cancelación, pérdida de captura, modificadores, estado desactualizado y límite de 10 s. Cada recuperación exige liberación y pulsación nueva; no se reanuda por heartbeat ni repetición de tecla.

## Corrección del origen temporal de wake

La versión anterior programaba PWM a partir del tick entero leído antes de activar físicamente GPIO11 y exigía después una ventana de 4–5 ms por DWT. Una sección crítica que cruzase un tick pendiente o el coste de configurar los temporizadores podía producir un FAULT falso en los bordes. La corrección mide desde después de GPIO11 y DSB, califica PWM por tiempo real dentro de 4–6 ms y comprueba el plazo de nuevo antes de habilitar los temporizadores. El parser y los ticks enteros no habilitan PWM.

Los once grupos nativos incluyen 1000 fases de tick, cuatro costes de sección crítica, siete costes de configuración, wrap de DWT, bordes de 4/6 ms y un ciclo fuera de plazo. STOP, lease de 150 ms y límite absoluto de 10 s conservan prioridad. BIN y HEX se reconstruyeron idénticos; el BIN corregido ocupa 7444 bytes y tiene SHA256 `2f742d7f3f479d744e8ded4b70657313c9477230b02d565ea1c0082b5e0898a2`.

El defecto temporal se comprobó mediante código y pruebas de fase. No se conoce el motivo concreto del FAULT que motivó la revisión, porque el servidor anterior no lo conservaba antes del reinicio. El diagnóstico nuevo registra ese motivo; no borra ni rearma automáticamente un fallo real.

La imagen corregida se instaló comparando primero los 512 KiB vivos con el readback anterior y verificando después toda la Flash, con sectores 1–7 intactos. SHA256 completo: `a07f171eff058c03dbeb66c3a2e3a2cf90c5070666681cf9bfc9f9873f681546`. El arranque fue una operación separada. Se verificaron descriptor, WebSocket autenticado y STOP/IDLE reales; la sesión solo envió INFO, STATUS y STOP, sin MOVE.
