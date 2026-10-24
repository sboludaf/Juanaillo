---
name: h60-flash
description: Importar dependencias, compilar, planificar y cargar o recuperar firmware de OpenCTR H60 con comparación completa, preservando backups y datos privados.
---

# Compilar y cargar firmware

Consulta `firmware/README.md`, `docs/tools-reference.md` y `docs/bring-up.md`. Usa las herramientas actuales y sus `--help`; los planes contienen rutas y hashes locales y no pertenecen al material público.

1. Importa dependencias desde un paquete original mediante `scripts/import_vendor.py`. Verifica sus hashes y deja `vendor/` ignorado. No distribuyas el ZIP ni sustituyas silenciosamente las dependencias por otra versión.
2. Compila y ejecuta las pruebas offline que correspondan. Revisa el descriptor generado y los dos extremos del protocolo. La imagen de banco de avance es perfil 4, inversión B/D y 3 s: no equivale a un firmware general de conducción.
3. Prepara el plan con imagen, manifiesto, identidad y baseline concretos. El alcance de este cargador es el sector 0 de 16 KiB; una imagen mayor necesita otro diseño revisado, no un borrado masivo improvisado.
4. Revisa el dry-run y, dentro de la autorización activa, ejecuta la carga: comparar toda la Flash viva con el baseline antes de borrar, escribir el payload y verificar toda la Flash posterior. Los sectores 1–7 deben conservarse.
5. El arranque normal es una operación explícita posterior a una imagen verificada; no envía FIRE ni debe incorporarse como efecto lateral de compilar o generar un plan.

No hay RDP/unprotect, OTP ni escrituras de EEPROM en este flujo. Si una lectura devuelve datos inesperados, conserva el intento y localiza si llegó a haber borrado/escritura. Si no hubo mutación, una nueva sesión ROM diagnosticada puede reintentarse sin volver a pedir una autorización ya vigente. No repitas a ciegas comandos de escritura, FIRE ni un borrado incierto. Si falló el readback después de escribir, verifica primero el estado real mediante lectura.

Un fallo observado cambió el bit7 de bytes hacia su paridad durante una sesión a 115200; la sesión siguiente leyó correctamente. Es una pista de muestreo/autobaud, no una prueba de firmware corrupto o de cable defectuoso. Mantén los registros de los intentos separados.

Entrega el hash del payload/readback, alcance real de modificación y estado final. No confundas validación estructural, build reproducible y prueba física: son evidencias distintas.
