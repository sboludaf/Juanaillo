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
