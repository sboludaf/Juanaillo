# Juanaillo

Juanaillo reúne herramientas y documentación en español para empezar a trabajar con una **OpenCTR H60 V3.7 / STM32F407VET6** desde Linux por USB y avanzar hacia la conducción autónoma, sin depender de leer los tutoriales originales en chino.

El objetivo del proyecto es servir de base para **conducción autónoma**. Actualmente cubre identificación, recuperación, respaldo, carga controlada, calibración de encoders, una prueba de avance de cuatro ruedas de 3 segundos y una web local temporal de Avance, Retroceso, Izquierda y Derecha. La navegación autónoma, el control de velocidad calibrado y la odometría completa siguen pendientes.

[Empieza aquí: ordenador → placa](docs/getting-started.md) · [Drivers USB](docs/usb-drivers.md) · [Problemas y soluciones](docs/troubleshooting.md) · [English overview](README.en.md)

## Del ordenador a la placa

La [guía de inicio](docs/getting-started.md) reúne el recorrido completo para preparar el ordenador, identificar USB-DEBUG, preservar el firmware original, compilar y cargar `manual-hold` perfil 6 y comprobar la comunicación antes de conectar motores. Es la ruta principal para llegar al control de cuatro botones; no exige cargar primero el ensayo antiguo de tres segundos.

1. [Drivers y permisos del USB](docs/usb-drivers.md): Linux, Windows y macOS, con descargas oficiales y diagnóstico que no abre puertos.
2. [Preparar, respaldar, compilar y cargar](docs/getting-started.md): comandos por etapas y comprobaciones antes y después de la Flash.
3. [Comunicar tu programa con la H60](docs/communication.md): ejemplo Python de INFO/STATUS y lectura HTTP del servidor existente.
4. [Resolver bloqueos](docs/troubleshooting.md): cable, puerto equivocado, permisos, programa ocupando el USB, firmware incompatible y reconexión tras apagar la placa.

La ruta real está ensayada en Linux. Las instrucciones de drivers para Windows/macOS no equivalen a haber validado físicamente la grabación o el control en esos sistemas. [Hardware](docs/hardware.md) · [Resultados reales](docs/tested-results.md).

## Qué se ha comprobado

- Placa H60 **V3.7**, MCU STM32F407VET6 y **512 KiB leídos del chip**, ROM bootloader 0x31 / PID 0x0413.
- Acceso al bootloader por **USB-DEBUG y DTR/RTS**, sin ST-Link ni puentes manuales.
- Dos respaldos originales completos e idénticos; los dumps y los identificadores de la placa se conservan fuera de este repositorio.
- Identificación de los cuatro canales y ocho tandas válidas de cinco vueltas manuales.
- En el chasis R5 ensayado: **1561 cuentas/vuelta** adoptadas y signos de motor **[+1, −1, +1, −1]** en orden A/B/C/D.
- Avance conjunto de **3 segundos al 10 % PWM**, parada y cuatro encoders coherentes con avance; confirmado visualmente por el operador.

Son resultados de una unidad y un montaje concretos. No convierten esos valores en especificaciones universales de todas las H60 o motores compatibles.

## Contenido

| Ruta | Uso |
|---|---|
| `firmware/forward-3s/` | Firmware de banco: cuatro motores hacia avance, un disparo explícito de 3 s por arranque |
| `firmware/commissioning/` | Núcleo y pruebas de la puesta en marcha anterior; consultar su alcance antes de compilar |
| `firmware/manual-hold/` | Firmware de control temporal: avance, retroceso y giros sobre el sitio, parada al soltar y máximo 10 s por pulsación |
| `web/` | Web local con cuatro botones, conexión autenticada y parada ante pérdida de control |
| `drivers/` | Índice de drivers USB oficiales y criterios de instalación por sistema |
| `examples/` | Ejemplo Python de comunicación sin órdenes de movimiento |
| `host/` | Cliente USB-DEBUG: descriptor, nonce, heartbeat, STOP y seguimiento de encoders |
| `tools/` | Identificación, backup, plan de carga, escritura limitada y arranque separado |
| `scripts/` | Importación verificada de dependencias y comprobación del árbol publicable |
| `profiles/` | Perfil vacío y ejemplo del R5 ensayado, sin datos personales |
| `docs/` | Conexiones, protocolo, recuperación, resultados y tareas pendientes |
| `skills/` | Flujos para agentes: puesta en marcha, carga, ruedas y publicación |

## Empezar

Usa Python 3.10 o posterior. Los ensayos originales se hicieron en Linux; no se ha comprobado el control de DTR/RTS en Windows o macOS.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/h60_doctor.py
python tools/h60_recovery.py --help
python examples/h60_status.py --help
```

Para compilar el firmware hacen falta GNU Make, un compilador C nativo para las pruebas y la toolchain `arm-none-eabi`. Las dependencias del fabricante **no se redistribuyen**: [importación y compilación](firmware/README.md).

Antes de conectar motores, sigue [la guía de inicio](docs/getting-started.md). Un cable que solo carga puede encender LEDs sin crear ningún puerto serie. USB-COM y USB-DEBUG tienen funciones distintas; no cambies de puerto a ciegas. La [guía del ensayo de tres segundos](docs/bring-up.md) se conserva como procedimiento separado para el perfil 4.

Los comandos que escriben o accionan hardware necesitan ejecución explícita. Las pruebas locales y la inspección de archivos no abren puertos serie. Los datos que salen del chip deben guardarse en `.local/`, ignorado por Git.

## Comprobaciones offline

```bash
make check
```

No necesita placa ni paquetes del fabricante para los tests nativos. La reconstrucción ARM sí requiere importarlos. Consulta la [validación de la copia limpia](docs/validation.md).

## Web local de conducción

La interfaz tiene cuatro botones: **Avance, Retroceso, Izquierda y Derecha**. Mantener pulsado mueve; soltar detiene. Los giros se realizan sobre el sitio, con un lado avanzando y el otro retrocediendo. También detiene al perder foco, visibilidad o conexión. El firmware `manual-hold`, perfil 6, aplica el mapa de polaridades del R5, limita el PWM al 10 % y cada pulsación a 10 s. Es un control temporal para diagnóstico; no sustituye el futuro supervisor autónomo. El perfil 5 anterior solo admitía avance y retroceso: hay que actualizar la placa para usar esta versión.

Consulta [web/README.md](web/README.md) para simulación, firmware correcto y arranque real. La aplicación de 3 s no acepta este protocolo. El servidor simula por defecto; el modo real requiere ejecución explícita y un manifiesto revisado. Las claves de acceso y registros se guardan en `.local/`, nunca en Git.

## Estado actual y próximos pasos

Los perfiles publicados son herramientas de banco y control temporal, no un controlador de navegación. Para avanzar hacia conducción autónoma hay que completar los límites y el control de velocidad, medir geometría, validar sensores y acordar una interfaz con el ordenador de navegación. Consulta [la hoja de ruta](docs/roadmap.md).

## Publicación y licencias

Este repositorio solo incluye código y documentación propios bajo [MIT](LICENSE). Las dependencias externas mantienen sus licencias y se importan localmente; véase [procedencia y exclusiones](THIRD_PARTY.md).

No publiques backups de Flash, UID del chip, registros crudos, credenciales, claves SSH, configuraciones WiFi/Tailscale ni rutas personales. La revisión pública se realiza sobre los archivos que Git va a incluir, no solo sobre `.gitignore`; véase [publicación](docs/publication.md).
