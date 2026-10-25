# Del ordenador a la H60: firmware y primera comunicación

Esta es la ruta principal para una **OpenCTR H60 V3.7 con STM32F407VE de 512 KiB**, un ordenador Linux y el firmware `manual-hold`, perfil 6. Termina con una consulta de estado y, opcionalmente, los cuatro botones de movimiento. No hace falta un ST-Link para la entrada ROM por USB-DEBUG comprobada en esta revisión.

El recorrido separa operaciones: preparar software → identificar USB → respaldar el firmware original → compilar → revisar y cargar → arrancar → consultar estado. No es necesario instalar primero el firmware antiguo de avance de tres segundos.

| Plataforma | Alcance de esta guía |
| --- | --- |
| Linux | Ruta de compilación y comunicación comprobada en la H60 del proyecto. Los comandos siguientes usan una shell Linux. |
| Windows | Hay selección de puertos COM y dependencias Python; DTR/RTS y la placa real no están validados en Windows. Consultar [drivers USB](usb-drivers.md). |
| macOS | Consultar drivers y puertos del sistema. No se ha validado la puesta en marcha física ni se ofrece aquí una receta de compilación probada. |

Si la placa no es V3.7, el chip o su tamaño no coinciden, o el cableado de motores es distinto, detenerse en la identificación. No copiar una configuración de otra revisión para superar una comprobación.

## 1. Preparar el ordenador sin conectar la placa

Para Debian/Ubuntu, los componentes necesarios para pruebas y compilación son:

```bash
sudo apt update
sudo apt install git python3 python3-venv make gcc gcc-arm-none-eabi binutils-arm-none-eabi libnewlib-arm-none-eabi libnewlib-dev
```

Para otras distribuciones, buscar los paquetes equivalentes: Python con venv, Git, compilador C nativo, GNU Make, Arm GNU Toolchain y newlib con `libc_nano`. La [guía de firmware](../firmware/README.md) describe los ajustes para instalaciones que separan las cabeceras y bibliotecas de newlib.

Clonar el repositorio y crear el entorno Python:

```bash
git clone https://github.com/sboludaf/Juanaillo.git
cd Juanaillo
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Comprobar el software sin acceder a hardware:

```bash
python scripts/h60_doctor.py
make check
```

El diagnóstico no abre puertos; las pruebas usan transportes simulados. La ausencia del paquete del fabricante no impide las pruebas nativas, pero sí la compilación ARM del paso 4.

## 2. Conectar e identificar el USB correcto

En un montaje nuevo, quitar batería y USB antes de desconectar los mazos de motor. Mantenerlos desconectados durante la primera identificación, carga y consulta. Conectar un **cable USB de datos a USB-DEBUG**, no a USB-COM, y usar la alimentación indicada para la placa en [hardware](hardware.md).

| Conector de la H60 ensayada | Adaptador / UART | Uso en esta guía |
| --- | --- | --- |
| USB-DEBUG | CH340 / USART1, PA9–PA10 | ROM, carga y aplicación `manual-hold` |
| USB-COM | CH9102 / USART3, PD8–PD9 | No es el puerto de este firmware |

Un LED encendido no demuestra que el ordenador haya enumerado el USB. Seguir [drivers y permisos](usb-drivers.md) si no aparece un puerto.

```bash
python scripts/h60_doctor.py
python tools/h60_recovery.py ports
```

Escoger el puerto que aparece al conectar USB-DEBUG. Los ejemplos usan `/dev/ttyUSB0`; **sustituirlo por el de la unidad presente**. Una ruta estable bajo `/dev/serial/by-id/` evita que cambie el nombre al conectar otros adaptadores.

```bash
PORT=/dev/ttyUSB0
```

Cerrar monitores serie y cualquier servidor que ya controle esa placa antes de abrir una sesión ROM. Solo un proceso debe ser propietario del puerto; no resolver un conflicto ejecutando el cliente como administrador ni abriendo otro programa sobre el mismo puerto.

## 3. Identificar el chip y conservar el firmware original

La ROM usa **115200, 8E1**. La aplicación usa **230400, 8N1**; no intercambiar estas configuraciones. `--entry inverted-both` solicita la secuencia DTR/RTS comprobada para USB-DEBUG de la V3.7, incluido reset. No modifica la Flash.

Preparar las rutas y comprobar primero el modo offline:

```bash
mkdir -p .local
python tools/h60_recovery.py identify \
  --port "$PORT" --out-dir .local/identity-01 --entry inverted-both
```

Sin `--execute`, la herramienta muestra el plan y no abre el puerto. Para identificar realmente la placa:

```bash
python tools/h60_recovery.py identify \
  --port "$PORT" --out-dir .local/identity-01 --entry inverted-both --execute
```

Debe obtener una identidad coherente con el STM32F407VE de 512 KiB. El PID de familia no demuestra por sí solo la revisión de la placa; comprobar también la serigrafía. Después, realizar **dos lecturas completas y concordantes**:

```bash
python tools/h60_recovery.py backup \
  --port "$PORT" --out-dir .local/backup-01 --entry inverted-both --execute
```

El resultado correcto informa `status: verified` y deja dos BIN, `identity.json`, `baseline.json`, registros y resultado en `.local/backup-01/`. Copiar ese directorio a otro almacenamiento privado antes de cargar. Si hay discrepancias, timeout, protección o una identidad inesperada, conservar el intento y seguir [diagnóstico](troubleshooting.md); no desproteger, borrar ni repetir transacciones a ciegas.

Cada directorio de ejecución debe ser nuevo. Un intento fallido no se arregla borrando sus pruebas: diagnosticarlo y elegir otro nombre para un intento deliberado posterior. `.local/` está ignorado por Git y puede contener datos propios de la unidad; no publicar su contenido.

## 4. Preparar y revisar el firmware de cuatro botones

Obtener del vendedor/fabricante el paquete **OpenCTR H60 code.zip** correspondiente a la revisión indicada en `firmware/manual-hold/vendor-lock.json`. Hace falta el código STM32; el firmware de fábrica, un paquete TB6612 antiguo o un recurso ROS no lo sustituyen. Las dependencias no se redistribuyen en este repositorio; [procedencia y requisitos](../firmware/README.md).

```bash
python scripts/import_vendor.py \
  --source '/ruta/al/OpenCTR H60 code.zip' \
  --destination firmware/manual-hold/vendor
make -C firmware/manual-hold test
make -C firmware/manual-hold all
```

Sustituir la ruta del ZIP. El importador reconoce la estructura interna y verifica sus hashes: no requiere traducir los nombres de las carpetas. Si rechaza el paquete, comprobar la revisión o pedir el recurso correcto; no desactivar la verificación.

El build genera `h60-manual-hold.bin`, HEX, ELF, map y `manifest.json` bajo `firmware/manual-hold/build/`. Compilar no abre serie, graba ni mueve motores.

Este firmware tiene una configuración de banco fija:

| Parámetro | Configuración |
| --- | --- |
| UART de aplicación | USART1 / USB-DEBUG, 230400, 8N1 |
| Protocolo | Perfil 6, marcador `H60_MANUAL_TURN_CONTROL_V1__` |
| Canales y avance del R5 | A trasera derecha, B trasera izquierda, C delantera derecha, D delantera izquierda; inversión eléctrica B/D |
| PWM | 10 % diferencial, 5 kHz |
| Caducidad / gesto máximo | MOVE caduca a 150 ms; un gesto dura como máximo 10 s |
| Arranque / STATUS / CAPS | No solicitan movimiento |

Los detalles están en [manual-hold](../firmware/manual-hold/README.md). `profiles/r5-tested.example.json` documenta medidas del montaje; editar ese JSON **no reconfigura este firmware en ejecución**. Otro montaje requiere revisar canales y sentidos en el código y repetir su validación. No aumentar PWM ni inventar geometría o ganancias para pasar las comprobaciones.

Antes del plan, inspeccionar los artefactos locales:

```bash
python tools/h60_recovery.py inspect firmware/manual-hold/build/h60-manual-hold.bin
python -m json.tool firmware/manual-hold/build/manifest.json
```

Comprobar perfil 6, el marcador anterior, `wake_scheduler: dwt-qualified` y `wake_max_ms: 6`. La inspección del BIN valida su estructura, no la seguridad de cualquier imagen externa.

## 5. Planificar, revisar y cargar solo el sector 0

Conservar los mazos desconectados y cerrar todo propietario anterior del puerto. Crear el plan es offline:

```bash
python tools/h60_flash.py plan \
  --image firmware/manual-hold/build/h60-manual-hold.bin \
  --manifest firmware/manual-hold/build/manifest.json \
  --baseline .local/backup-01 \
  --output .local/flash-plan.json \
  --port "$PORT" --entry inverted-both
python -m json.tool .local/flash-plan.json
```

Revisar imagen, identidad, puerto y alcance: `erase_sectors: [0]`, `auto_go: false`, `auto_reset: false`. El plan vincula los hashes de build, fuentes, herramientas y backup. Anotar el `plan_sha256` que imprimió la creación. Puede comprobarse sin herramientas adicionales:

```bash
python -c 'import hashlib,pathlib; print(hashlib.sha256(pathlib.Path(".local/flash-plan.json").read_bytes()).hexdigest())'
```

Sustituir `SHA256_DEL_PLAN_REVISADO` por esos 64 dígitos. Primero validar sin abrir el puerto:

```bash
python tools/h60_flash.py apply \
  --plan .local/flash-plan.json --plan-sha256 SHA256_DEL_PLAN_REVISADO \
  --out-dir .local/flash-01
```

Después de revisar el plan, solicitar la carga explícita añadiendo `--execute`:

```bash
python tools/h60_flash.py apply \
  --plan .local/flash-plan.json --plan-sha256 SHA256_DEL_PLAN_REVISADO \
  --out-dir .local/flash-01 --execute
```

La herramienta identifica el mismo MCU, compara los 512 KiB actuales con el backup antes de borrar, modifica exclusivamente el sector 0 y verifica los 512 KiB posteriores, incluidos los sectores 1–7 conservados. Exigir `status: verified`. Si algo falla, no se reintenta automáticamente ni se arranca la aplicación.

## 6. Arrancar es una operación distinta de cargar

Solo con un resultado de carga verificado, usar el `result_sha256` que imprimió `apply`. También se obtiene así:

```bash
python -c 'import hashlib,pathlib; print(hashlib.sha256(pathlib.Path(".local/flash-01/result.json").read_bytes()).hexdigest())'
```

Sustituir `SHA256_DEL_RESULTADO_VERIFICADO` y revisar primero sin `--execute`:

```bash
python tools/h60_boot.py \
  --flash-result .local/flash-01/result.json \
  --result-sha256 SHA256_DEL_RESULTADO_VERIFICADO --port "$PORT"
```

Para solicitar el arranque:

```bash
python tools/h60_boot.py \
  --flash-result .local/flash-01/result.json \
  --result-sha256 SHA256_DEL_RESULTADO_VERIFICADO --port "$PORT" --execute
```

La herramienta solicita un único reset, no transmite bytes UART ni órdenes de motor. `application_response_verified: false` es normal en este paso: se comprueba la respuesta en el siguiente. Conserva el registro de intento y no lo repite por sí sola.

## 7. Comprobar la comunicación sin solicitar movimiento

El ejemplo [h60_status.py](../examples/h60_status.py) permite estudiar y comprobar la comunicación del perfil 6. Antes de iniciar el servidor web y sin otro proceso propietario del puerto, preparar la consulta:

```bash
python examples/h60_status.py serial \
  --port "$PORT" --manifest firmware/manual-hold/build/manifest.json
```

El modo predeterminado valida el build, muestra el SHA256 del manifiesto y deja el puerto cerrado. Usar el hash revisado en la consulta real:

```bash
python examples/h60_status.py serial \
  --port "$PORT" --manifest firmware/manual-hold/build/manifest.json \
  --manifest-sha256 SHA256_DEL_MANIFIESTO_REVISADO --execute
```

Esta consulta envía únicamente INFO/CAPS y STATUS, sin STOP ni MOVE. Debe identificar el perfil 6 y devolver estado actual y encoders; el puerto se cierra al terminar. Abrir el adaptador puede producir un transitorio de reset, como se explica en la [referencia de transporte](tools-reference.md#puerto-y-entrada-rom).

Para la ruta web, iniciar después el único servidor propietario del puerto. El hash anterior es **del manifiesto local que se ha revisado**, no del BIN ni del plan. También puede obtenerse así:

```bash
python -c 'import hashlib,pathlib; print(hashlib.sha256(pathlib.Path("firmware/manual-hold/build/manifest.json").read_bytes()).hexdigest())'
```

Sustituir `SHA256_DEL_MANIFIESTO_REVISADO`:

```bash
python -m web.server --execute \
  --serial-port "$PORT" \
  --manifest firmware/manual-hold/build/manifest.json \
  --manifest-sha256 SHA256_DEL_MANIFIESTO_REVISADO \
  --bind 127.0.0.1 --port 8765
```

Este inicio comprueba el descriptor y solicita STOP; no envía MOVE. Dejar el proceso en primer plano. En otra terminal, esta consulta solo lee HTTP y no abre serie ni toma el control:

```bash
python3 examples/h60_status.py http --url http://127.0.0.1:8765
```

El resultado esperado es `simulated: false`, `connected: true`, `ready: true`, `state: idle`, `moving: false`, `held: false`, `stop_pending: false` y `error: null`. Los encoders aparecen como cuatro contadores A/B/C/D. Un timeout o un estado antiguo no demuestra una conexión actual ni una parada física.

El cliente antiguo `host/pulse_client.py` corresponde al perfil 4 de tres segundos: no usarlo para identificar este perfil 6. Para implementar otra interfaz, consultar el [contrato de bytes del perfil 6](../firmware/manual-hold/README.md#wire-contract): STATUS/CAPS y sus longitudes difieren del perfil 4. No enviar velocidades ROS ni órdenes de un firmware de fábrica a esta aplicación.

## 8. Primera prueba opcional con los cuatro botones

La comunicación ya puede verificarse con los motores desconectados. Para una prueba motriz, detener el servidor con Ctrl+C, quitar batería y USB y reconectar mazos según el mapa comprobado. Colocar el chasis estable con las ruedas elevadas, manos fuera y un corte de alimentación accesible. Después alimentar la placa y arrancar deliberadamente el servidor anterior.

Abrir el enlace que imprime el servidor, incluido su fragmento `#token=...`. Ninguna rueda debe moverse al abrirlo. Mantener brevemente **Avance** y soltar: solicitar movimiento requiere esa pulsación vigente. Comprobar sentido de las cuatro ruedas y retorno a reposo; probar otra dirección solo tras evaluar el resultado anterior. El sentido correcto depende del cableado de cada montaje.

La web ofrece Avance, Retroceso, Izquierda y Derecha al 10 %. Soltar, perder conexión o foco detiene la intención; 10 s es el límite de una pulsación, no una duración recomendada de prueba. No hay PID de velocidad, distancias o ángulos calibrados ni navegación autónoma. Los [resultados](tested-results.md) distinguen los ensayos motrices del perfil anterior de las comprobaciones sin MOVE y pruebas de software del perfil 6; los giros siguen pendientes de ensayo motriz documentado.

Para entrar desde otro ordenador de la red hay que iniciar el servidor con un bind adecuado, como describe [la web](../web/README.md), y conservar su clave privada. Cada reinicio del servidor genera otra clave. Si se apaga la H60 mientras el servidor sigue abierto, el error serie queda bloqueado: tras recuperar alimentación, cerrar y volver a iniciar explícitamente el servidor y usar su enlace nuevo; recargar la página no recupera esa sesión serie.
