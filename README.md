# OpenCTR H60 Lab

Herramientas y documentación en español para empezar a trabajar con una **OpenCTR H60 V3.7 / STM32F407VET6** desde Linux por USB, sin depender de leer los tutoriales originales en chino.

El objetivo del proyecto es servir de base para **conducción autónoma**. Actualmente cubre identificación, recuperación, respaldo, carga controlada, calibración de encoders y una prueba de avance de cuatro ruedas de 3 segundos. La navegación autónoma, el control de velocidad calibrado y la odometría completa siguen pendientes.

[English overview](README.en.md) · [Hardware](docs/hardware.md) · [Puesta en marcha](docs/bring-up.md) · [Resultados reales](docs/tested-results.md) · [Guía para agentes](AGENTS.md)

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
python tools/h60_recovery.py --help
python host/pulse_client.py --help
```

Para compilar el firmware hacen falta GNU Make, un compilador C nativo para las pruebas y la toolchain `arm-none-eabi`. Las dependencias del fabricante **no se redistribuyen**: [importación y compilación](firmware/README.md).

Antes de conectar motores, sigue [la puesta en marcha por etapas](docs/bring-up.md). Un cable que solo carga puede encender LEDs sin crear ningún puerto serie. USB-COM y USB-DEBUG tienen funciones distintas; no cambies de puerto a ciegas.

Los comandos que escriben o accionan hardware necesitan ejecución explícita. Las pruebas locales y la inspección de archivos no abren puertos serie. Los datos que salen del chip deben guardarse en `.local/`, ignorado por Git.

## Comprobaciones offline

```bash
make check
```

No necesita placa ni paquetes del fabricante para los tests nativos. La reconstrucción ARM sí requiere importarlos. Consulta la [validación de la copia limpia](docs/validation.md).

## Estado actual y próximos pasos

El firmware publicado es una herramienta de banco, no un controlador de navegación. Para avanzar hacia conducción autónoma hay que completar los límites y el control de velocidad, medir geometría, validar sensores y acordar una interfaz con el ordenador de navegación. Consulta [la hoja de ruta](docs/roadmap.md).

## Publicación y licencias

Este repositorio solo incluye código y documentación propios bajo [MIT](LICENSE). Las dependencias externas mantienen sus licencias y se importan localmente; véase [procedencia y exclusiones](THIRD_PARTY.md).

No publiques backups de Flash, UID del chip, registros crudos, credenciales, claves SSH, configuraciones WiFi/Tailscale ni rutas personales. La revisión pública se realiza sobre los archivos que Git va a incluir, no solo sobre `.gitignore`; véase [publicación](docs/publication.md).
