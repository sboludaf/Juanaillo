# Herramientas de recuperación, carga y arranque

Ejecutar los ejemplos desde la raíz del repositorio. Los módulos de `tools/` son
una implementación propia del protocolo público
[ST AN3155](https://www.st.com/resource/en/application_note/an3155-how-to-use-usart-protocol-in-bootloader-on-stm32-mcus-stmicroelectronics.pdf).
No incluyen código de Project0 ni bibliotecas del fabricante. El `LICENSE` de la
revisión de Project0 consultada era un marcador provisional, no una licencia MIT.

Las operaciones que abren un puerto requieren `--execute`. Su ausencia valida o
describe la operación sin abrir serie ni crear el directorio de ejecución. La
enumeración `ports` tampoco abre los puertos. No hay búsqueda automática de un
controlador, reintentos de transacciones, desprotección, escritura de option bytes
ni comando ROM `GO`.

## Datos locales

Guardar identidades, imágenes leídas, planes y resultados bajo `..local/`, excluido
de Git. Esos archivos pueden contener el UID necesario para asociar un backup
con su MCU. Los resúmenes de consola omiten el UID. No publicar esos registros ni
sus binarios sin revisarlos. Los UID de las pruebas se generan como datos
sintéticos y no proceden de un dispositivo.

Los planes guardan rutas relativas a su propio directorio. Se vinculan por SHA256
a la imagen, manifiesto, fuentes, artefactos, baseline y herramientas utilizadas.
Mover toda la estructura conservando sus relaciones mantiene esa asociación;
modificar una entrada exige generar y revisar otro plan.

## Puerto y entrada ROM

```sh
python3 tools/h60_recovery.py ports
mkdir -p .local
python3 tools/h60_recovery.py identify \
  --port /dev/ttyUSB0 --out-dir ..local/identity-01 --entry inverted-both
```

La última orden es offline. Añadir `--execute` solicita la operación indicada.
`--port` es siempre explícito: por ejemplo, una ruta Linux o `COM7` en Windows.
El puerto debe corresponder a USB-DEBUG. La revisión física V3.7 es una asociación
del operador: PID `0x0413` identifica la familia, no demuestra por sí solo el
encapsulado o la placa. Las herramientas exigen leer 512 KiB del registro MCU;
no usan un tamaño de Flash supuesto como alternativa.

`--entry manual`, predeterminado, presupone que el MCU ya está en ROM y no
programa una secuencia de reset. `--entry inverted-both` aplica la secuencia
comprobada para el circuito H60: DTR afirmado significa BOOT0 bajo; RTS afirmado
mantiene reset. No se prueban polaridades alternativas automáticamente.

ROM usa 8E1 y 115200 baudios por defecto. `--baud 57600` permite preparar una
sesión a menor velocidad; no es una recuperación automática. Cada sesión ROM
sincroniza una vez con `0x7F`. Un ACK inesperado, timeout o NACK aborta la sesión;
no se corrigen bits ni se resincroniza dentro de una operación de escritura.

Linux desactiva y comprueba HUPCL antes de enviar la sincronización. No restaura
DTR/RTS al cerrar. Abrir un CH340 puede producir un transitorio de reset aunque
el programa no lo solicite: estas opciones no certifican el estado eléctrico.
Windows tiene soporte de nombre COM y pyserial, pero esa ruta no se ha probado
en el banco y no dispone de HUPCL POSIX.

## Backup e inspección

```sh
python3 tools/h60_recovery.py inspect firmware/forward-3s/build/h60-forward-3s.bin
python3 tools/h60_recovery.py backup \
  --port /dev/ttyUSB0 --out-dir ..local/backup-01 --entry inverted-both
```

Con `--execute`, `backup` identifica el MCU y obtiene dos lecturas completas de
512 KiB en una sesión ROM. Publica un baseline verificado solo si coinciden.
Una operación fallida conserva sus archivos parciales y se marca incompleta.
El directorio debe ser nuevo; no se sobrescriben backups ni resultados.

`inspect` acepta BIN e Intel HEX, verifica rangos, checksums, solapamientos y
vectores plausibles. Es una comprobación estructural; no demuestra que un
firmware inhiba motores o sea apropiado para el montaje.

## Plan y carga limitada al sector 0

El build debe producir BIN, HEX, ELF, map y `build/manifest.json`. Se comprueban
sus cuatro hashes, las fuentes relativas al proyecto, el marcador del firmware
y la equivalencia de BIN/HEX. Solo se admiten imágenes alineadas de hasta 16 KiB.
No está implementada una restauración de fábrica que borre sectores adicionales.

```sh
python3 tools/h60_flash.py plan \
  --image firmware/forward-3s/build/h60-forward-3s.bin \
  --manifest firmware/forward-3s/build/manifest.json \
  --baseline ..local/backup-01 --output ..local/flash-plan.json \
  --port /dev/ttyUSB0 --entry inverted-both
```

La orden anterior es enteramente offline e imprime el SHA256 del plan. Revisar
ese JSON y usar su hash concreto en la siguiente orden:

```sh
python3 tools/h60_flash.py apply \
  --plan ..local/flash-plan.json --plan-sha256 SHA256_DEL_PLAN_REVISADO \
  --out-dir ..local/flash-01
```

El valor `SHA256_DEL_PLAN_REVISADO` es un marcador que debe sustituirse. Sin
`--execute`, `apply` valida todo y deja el puerto cerrado. Con `--execute`:

1. Entra en una sesión ROM e identifica el mismo MCU del baseline.
2. Lee y compara los 512 KiB completos antes de emitir cualquier borrado.
3. Borra exclusivamente el sector 0 y escribe únicamente el payload revisado.
4. Lee los 512 KiB y exige la imagen completa esperada, incluidos los sectores
   1 a 7 intactos y el resto del sector 0 rellenado con `0xFF`.
5. Cierra la sesión sin `GO`, reset de salida ni cambios de protección.

Un intento de borrado o escritura se marca consumido antes de su primer envío;
ni siquiera un fallo del primer ACK permite repetirlo dentro del ejecutor. Un
fallo requiere revisar el resultado y preparar deliberadamente una nueva sesión.

## Reutilizar un readback verificado

Para una siguiente imagen no es necesario presentar una copia de un readback
como dos lecturas independientes:

```sh
python3 tools/h60_recovery.py baseline \
  --flash-result ..local/flash-01/result.json --out-dir ..local/baseline-next
```

Esta operación copia y verifica el resultado y readback completos de una carga
previa de estas herramientas. Registra `source_kind=verified-flash-readback` y
`read_count=1`. La siguiente carga conserva la comparación completa en vivo
antes del borrado. No se realizan lecturas MCU al importar este baseline.

## Arranque separado, sin órdenes de motor

`apply` imprime también el SHA256 de su `result.json`. El arranque exige ese
resultado y su readback completos:

```sh
python3 tools/h60_boot.py \
  --flash-result ..local/flash-01/result.json --result-sha256 SHA256_DEL_RESULTADO \
  --port /dev/ttyUSB0
```

Sin `--execute` es offline. Con él, reserva un registro exclusivo y durable
antes de abrir el puerto, solicita BOOT0 bajo y un único reset de 80 ms mediante
el circuito `inverted-both`. Usa 230400/8N1 y transmite **cero bytes UART**.
`application_response_verified=false` es intencional: identificar la aplicación
corresponde al cliente de `host/`.

Resetear reinicia el estado de disparo único de la aplicación. No se combina
reset y movimiento en estas herramientas. El registro predeterminado
`boot-request.json` impide repetir el arranque automáticamente; `--record`
permite nombrar un intento nuevo explícito.

## Pruebas sin hardware

```sh
python3 -m unittest discover -s tests -p 'test_recovery.py' -v
python3 -m unittest discover -s tests -p 'test_flash.py' -v
```

El ROM simulado comprueba identidad y comparación antes del borrado, límites de
direcciones, sector único, preservación de cola, fallo de ACK, corrupción de
readback y ausencia de reintentos. También se comprueban los modos offline y el
arranque sin TX. Estas pruebas no abren dispositivos serie reales.
