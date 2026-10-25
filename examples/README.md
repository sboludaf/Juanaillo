# Consultar la H60 desde otro programa

`h60_status.py` es un ejemplo Python para el firmware **`manual-hold`, perfil 6**. Reutiliza el mismo descriptor, parser, checksum y validación del controlador web. Solo consulta estado y encoders; no envía MOVE, STOP, heartbeat, comandos ROM, carga de firmware ni pulsos de reset. No convierte cuentas a metros o velocidad.

Ejecuta los comandos desde la raíz del repositorio. La preparación completa está en [la guía de inicio](../docs/getting-started.md).

No se necesita instalar ni ejecutar una aplicación del fabricante. Para la consulta directa por USB, este ejemplo verifica el manifiesto, los artefactos y las fuentes locales del build ya preparado; no lee el ZIP original ni lo exige de nuevo tras importarlo. La consulta HTTP a un servidor ya operativo no necesita el build en el ordenador cliente.

## Si el servidor web ya está en marcha

No abras su puerto serie desde un segundo programa. Consulta su API de lectura:

```bash
python3 examples/h60_status.py http --url http://127.0.0.1:8765
```

Esta orden hace únicamente `GET /api/status`, sin autenticar una sesión de control, tomar su propiedad ni enviar STOP. No necesita `pyserial`, `aiohttp`, la clave web o un manifiesto de build. Acepta solo HTTP en loopback y no sigue redirecciones. El resultado distingue el éxito de la petición (`ok`) de la conexión de la placa (`status.connected`). Si el servidor conserva un error de comunicación, sus encoders pueden ser la última muestra antigua.

## Consulta directa por USB-DEBUG

Debe estar ejecutándose el firmware correcto y **no puede haber otro servidor, terminal serie o cliente con el puerto abierto**. Utiliza el USB-DEBUG comprobado. Instala las dependencias Python y prepara el build de `manual-hold` según la guía de inicio.

Primero valida el build local y muestra el plan sin abrir el puerto:

```bash
python3 examples/h60_status.py serial --port /dev/ttyUSB0 \
  --manifest firmware/manual-hold/build/manifest.json
```

Comprueba el build y copia el campo `manifest_sha256` del JSON. Para realizar una única consulta:

```bash
python3 examples/h60_status.py serial --port /dev/ttyUSB0 \
  --manifest firmware/manual-hold/build/manifest.json \
  --manifest-sha256 HASH_REVISADO --execute
```

`HASH_REVISADO` se sustituye por los 64 dígitos revisados. En Windows usa el Python de la venv y `--port COM3`; el comportamiento físico de las líneas de control solo se ha ensayado en Linux.

Se abre una sola sesión **230400 baudios, 8N1**, sin control de flujo. El cliente solicita las líneas DTR/RTS conocidas para mantener BOOT bajo y reset liberado, desactiva HUPCL en POSIX y espera una sola vez 350 ms antes de INFO. **Abrir el CH340 puede producir un transitorio de reset aunque no se solicite**: no lo utilices para inspeccionar una sesión motriz activa. En una puesta en marcha desconocida, mantén los motores desconectados o las ruedas elevadas con corte accesible.

Se exige igualdad del descriptor completo del perfil 6 antes de aceptar STATUS. Un perfil 4, perfil 5, timeout o checksum incorrecto termina la consulta sin repetición automática. Al cerrar no se restablecen las líneas ni se solicita STOP: esta utilidad no es un mando de parada. La consola omite nonce y UID y no crea registros de bytes UART ni archivos de ejecución.

## Datos recibidos

El JSON serie contiene `status.state`, `status.flags`, `status.uptime_ms`, `status.encoders` en orden A/B/C/D, motivo y límites. El bit `all_low` describe comprobaciones del firmware, no una medición eléctrica externa. Los encoders son contadores `uint16`; obtener posición, velocidad u odometría exige seguir muestras y tratar wraps con el método adecuado.

Las tramas sin payload usadas por ambos perfiles son:

| Consulta | Trama completa |
| --- | --- |
| INFO/CAPS | `AA 55 05 76 7A` |
| STATUS | `AA 55 05 70 74` |

La respuesta INFO del perfil 6 tiene descriptor de 48 bytes; STATUS tiene payload de **44 bytes**. No leas esos 44 bytes con el formato de 36 bytes del banco `forward-3s`. Consulta [el contrato general y sus perfiles](../docs/protocol.md), [el firmware actual](../firmware/manual-hold/README.md) y el código mantenido en `web/serial_client.py` antes de ampliar el ejemplo.
