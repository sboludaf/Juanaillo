# Comunicar un ordenador con la H60

El recorrido de instalación y carga está en [la guía de inicio](getting-started.md). Esta página explica cómo comprobar que tu programa habla con la aplicación correcta. Usa [el ejemplo Python](../examples/README.md) para una primera consulta sin órdenes de motor.

La comunicación utiliza las herramientas Python de este repositorio: no necesita una aplicación de control de OpenCTR/XTARK instalada o en ejecución. El ejemplo USB y el servidor comprueban el build local completo, incluidas sus fuentes importadas; esa comprobación no implica instalar un programa del fabricante. El cliente HTTP solo necesita poder acceder al servidor que ya tiene la conexión USB.

## Elegir puerto, firmware y protocolo

En la H60 V3.7 ensayada, el controlador de este repositorio usa **USB-DEBUG → CH340 → USART1 PA9/PA10**. USB-COM lleva otro adaptador y llega a USART3: no es un puerto alternativo para el mismo protocolo. Los [drivers USB](usb-drivers.md) permiten que aparezca el puerto; no instalan ni cambian el firmware del STM32.

| Sesión | Serie | Para qué sirve |
| --- | --- | --- |
| Bootloader ROM de STM32 | 115200, 8E1 | Identificar el chip, hacer backup y cargar Flash mediante `tools/` |
| Aplicación `manual-hold`, perfil 6 | 230400, 8N1 | INFO/CAPS, STATUS, encoders y control temporal de cuatro direcciones |
| Aplicación `forward-3s`, perfil 4 | 230400, 8N1 | Ensayo anterior de un único avance de tres segundos |

El firmware de fábrica puede tener otro contrato. Un puerto que se abre correctamente no demuestra compatibilidad. Los clientes comprueban el descriptor y rechazan otro perfil; no hay conversión automática entre perfiles 4, 5 y 6.

## Consulta directa por USB

Con `manual-hold` perfil 6 ya cargado y el servidor web cerrado, desde la raíz del repositorio:

```bash
python3 examples/h60_status.py serial \
  --port /dev/ttyUSB0 \
  --manifest firmware/manual-hold/build/manifest.json
```

Este primer comando es offline. Verifica el build e imprime el SHA256 que se debe revisar. Para la consulta real, se añade `--manifest-sha256 HASH_REVISADO --execute`, según [el ejemplo completo](../examples/README.md). El cliente envía INFO/CAPS y STATUS y cierra; no envía MOVE, STOP ni comandos ROM. El resultado contiene el estado y los cuatro contadores en orden A/B/C/D.

Solo un proceso debe abrir el puerto. No ejecutes esta consulta mientras el servidor web, una terminal serie u otro programa lo utilice. El CH340 puede producir un transitorio de reset al abrir: INFO/STATUS no son órdenes de movimiento, pero abrir un puerto tampoco es una operación eléctricamente pasiva. La primera comprobación se hace sin motores conectados; no cambies conexiones con batería o USB puestos.

## Consultar un servidor que ya está conectado

Si el servidor web ya tiene el puerto, usa su API HTTP de lectura:

```bash
python3 examples/h60_status.py http --url http://127.0.0.1:8765
```

Esto solicita `GET /api/status`. No abre serie, no reclama el control, no envía STOP y no requiere la clave del WebSocket de movimiento. Comprueba `simulated`, `connected`, `ready`, `state` y `error`: un HTTP correcto no demuestra que la placa siga conectada. Si el backend está en error, los encoders pueden ser el último dato guardado. `moving: false` sin conexión no confirma una parada física.

## Contrato de la aplicación perfil 6

Las tramas son `AA 55 LEN ID PAYLOAD SUM8`; `LEN` cuenta la trama entera y `SUM8` es la suma módulo 256 de los bytes anteriores. Los campos multibyte usan big-endian. Peticiones de consulta completas:

| Petición | Bytes enviados | Respuesta |
| --- | --- | --- |
| INFO/CAPS | `AA 55 05 76 7A` | 48 bytes de payload; exige perfil 6 y marcador `H60_MANUAL_TURN_CONTROL_V1__` |
| STATUS | `AA 55 05 70 74` | 44 bytes de payload |
| ENCODERS | `AA 55 05 63 67` | Cuatro `uint16`, A/B/C/D |

STATUS utiliza `>BBBBIIQ4HIIiI`: versión, perfil, estado, flags, uptime, lease restante, nonce del arranque, cuatro contadores, contador de gestos, motivo, dirección y tiempo restante del gesto. El nonce pertenece al arranque y no es una contraseña. Los contadores son valores raw de 16 bits: no equivalen a metros ni a velocidad sin calibración y seguimiento temporal.

Los estados son IDLE, WAKE, RUNNING, LIMIT y FAULT. Para control, MOVE `0x77` lleva nonce `uint64` y dirección `int8`: `+1` avance, `-1` retroceso, `+2` izquierda y `-2` derecha. STOP es `0x74` sin payload. Una aplicación propia debe conservar el lease de 150 ms, el máximo absoluto de 10 s y la parada ante pérdida de intención del operador; no debe generar renovaciones indefinidas a partir de una orden antigua ni borrar un FAULT.

El [servidor existente](../web/README.md) ya implementa ese control y mantiene el único propietario de serie. Para integrar otro programa, parte del contrato y del cliente comprobado en [web/serial_client.py](../web/serial_client.py). La especificación detallada está en [el README del firmware](../firmware/manual-hold/README.md#wire-contract). [protocol.md](protocol.md) documenta principalmente el perfil 4 y señala sus diferencias con el perfil 6.
