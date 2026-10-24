# Validación del repositorio preparado para publicación

Comprobación realizada el 24 de octubre de 2026, sin abrir puertos serie ni mover hardware durante el empaquetado.

- `make check`: 18 pruebas Python de herramientas/privacidad, 6 del importador y 35 del host, además de los grupos nativos de firmware y commissioning. Todas pasan.
- Cuatro skills validadas por formato y evaluadas por otro agente con casos de identificación/respaldo, repetición autorizada y publicación. Las referencias locales Markdown resuelven.
- Se copió exclusivamente el contenido seleccionado por Git a un árbol temporal limpio, sin vendor, builds, entorno privado ni datos del equipo. `make test` pasó en esa copia.
- En la copia limpia se importaron los 41 archivos necesarios desde el paquete original mediante checksums y se reconstruyó el firmware. El BIN fue idéntico al usado en los ensayos físicos: **7132 bytes**, SHA256 `8fc79c5214a0521d9351b803d8b5353a81b6df3d0bfbb7280648b7aac7fa5feb`.
- El escáner del árbol publicable y la revisión de contenido no encontraron las rutas o identificadores reales conocidos de la instalación de origen. La revisión no sustituye la comprobación de futuros cambios e historial antes de publicar.

Las herramientas ROM portables nuevas se comprobaron con un simulador. El acceso ROM y los resultados físicos anteriores proceden de las herramientas de la sesión original; no se declara que la nueva entrega portable haya vuelto a grabar una placa. El firmware y sus resultados físicos sí quedan relacionados por el BIN idéntico.

Los artefactos de build, fuentes importadas, dumps y registros privados se mantienen fuera del historial público. El workflow de GitHub ejecuta únicamente comprobaciones offline; no reconstruye dependencias del fabricante ni acciona hardware.
