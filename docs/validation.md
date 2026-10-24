# Validación del repositorio preparado para publicación

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
