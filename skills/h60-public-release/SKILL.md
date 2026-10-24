---
name: h60-public-release
description: Preparar código y evidencias de OpenCTR H60 para un repositorio público, revisando datos privados, historial y procedencia de dependencias.
---

# Preparar una publicación pública

Lee `THIRD_PARTY.md` y `docs/publication.md`. Aplica este flujo cuando se vaya a compartir o publicar material, no como requisito para cada cambio local.

- Empieza desde una selección de fuentes propias; no copies todo el workspace de una placa. Los backups de Flash, UID, registros crudos, fotos del entorno, cuentas de red, credenciales y configuraciones de acceso permanecen privados.
- Respeta la procedencia de cada archivo. Que un repositorio sea público no le da una licencia MIT; la referencia Project0 inspeccionada tenía una licencia pendiente. Un ZIP del fabricante sin licencia global no debe incluirse entero. Distribuye importadores/verificaciones y conserva localmente los términos de las dependencias importadas.
- Elimina rutas personales y valores de identidad de herramientas, manifiestos, ejemplos y metadatos de build. Usa rutas CLI/relativas. Los ejemplos de calibración deben identificarse como ejemplo, nunca como identidad o configuración universal.
- Ejecuta `python scripts/check_public_tree.py`; tras preparar el commit, usa su modo `--staged`. Revisa también el diff real y, si existe, el historial. `.gitignore` no elimina archivos ya versionados ni secretos en commits anteriores.
- Prueba la copia portable desde un árbol temporal limpio: tests offline, importación local permitida y build si están disponibles las dependencias. No conectes ni actives una placa como parte de la revisión pública.
- Comprueba autor/correo del commit y enlaces/documentación. No publiques mensajes o datos personales para acreditar una prueba: usa resultados numéricos saneados con método y límites.

La entrega local no implica crear un remoto. Para publicar, utiliza la cuenta/nombre/visibilidad acordados y autenticación oficial de navegador o conector; no pidas ni guardes contraseñas o tokens en el chat o en archivos del repositorio.

Informa qué se incluyó, qué quedó privado o dependiente de importación, comprobaciones realizadas y si el remoto existe realmente. No prometas ausencia absoluta de secretos por pasar un escáner.
