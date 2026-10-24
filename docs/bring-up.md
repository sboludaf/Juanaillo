# Puesta en marcha del banco H60

Esta guía cubre el **banco de pruebas de avance fijo durante tres segundos**. Para el control temporal de dos botones consulta [la web local](../web/README.md), que requiere otro firmware y protocolo. El objetivo futuro es conducción autónoma, pero esta imagen no implementa navegación, regulación de velocidad ni una interfaz de conducción continua. La [referencia de hardware](hardware.md) y los [resultados](tested-results.md) corresponden a una sola unidad.

## Preparar software sin conectar hardware

Se usa Python 3.10 o posterior. El único paquete del host es pyserial 3.5; las pruebas con transporte simulado no abren puertos y no necesitan instalarlo.

Desde la raíz del repositorio, en Linux:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r host/requirements.txt
mkdir -p .local
python -m unittest discover -s host -p 'test_*.py' -v
make -C firmware/forward-3s test
```

El puente de pruebas C necesita un compilador C nativo. El firmware de aplicación completo requiere además Arm GNU Toolchain y dependencias del fabricante importadas localmente. Las fuentes de terceros no se redistribuyen como parte de este repositorio:

```bash
python scripts/import_vendor.py --source /ruta/al/paquete-del-fabricante.zip
make -C firmware/forward-3s
```

El build genera `firmware/forward-3s/build/manifest.json` y sus artefactos locales. `arm-none-eabi-` debe estar en PATH; `CROSS_COMPILE` permite seleccionar otra instalación. Consultar también la [documentación del firmware](../firmware/README.md) y la [referencia de herramientas](tools-reference.md).

En Windows, la preparación del host es:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r host/requirements.txt
New-Item -ItemType Directory -Force .local | Out-Null
.\.venv\Scripts\python.exe -m unittest discover -s host -p "test_*.py" -v
```

El cliente acepta `COM3` o la forma extendida de un puerto COM. Las pruebas C del host se omiten en Windows. El funcionamiento físico del adaptador, DTR/RTS, cierre del puerto y temporización de la sesión sólo se ha probado en Linux; la compatibilidad Windows del código no es una validación de hardware Windows.

## Identificar y preservar la placa

1. Comprobar revisión, alimentación y etiquetas de los conectores. Para conectar o retirar motores, quitar batería y todos los USB con la placa apagada.
2. Preparar el acceso USB-DEBUG con un cable de datos. La aplicación y la ROM usan configuraciones serie diferentes; no intercambiar sus recetas.
3. Identificar el microcontrolador y su capacidad real antes de leer o escribir rangos de Flash. El PID de familia por sí solo no identifica el tamaño exacto instalado.
4. Guardar dos lecturas completas concordantes de la Flash y su identidad local, fuera del repositorio. No utilizar desprotección o borrado para obtener una copia.
5. Revisar imagen, manifiesto, vectores, fuentes y alcance del borrado. La carga debe comprobar la identidad viva y la Flash actual antes de modificarla, y verificar por readback el resultado completo previsto.

Las órdenes concretas de identificación, copias, baseline, plan de carga y aplicación están en [tools-reference.md](tools-reference.md). Sus modos offline permiten revisar el trabajo antes de abrir un puerto. Esta guía no incluye una orden genérica de grabación que pueda aplicarse a cualquier H60 o tamaño de Flash.

La imagen de tres segundos **sí tiene capacidad motriz**. Para una primera puesta en marcha desde un estado desconocido, programar y arrancar con los mazos desconectados. En un montaje ya verificado puede mantenerse la condición de ruedas elevadas autorizada en la sesión, con corte accesible; no hace falta pedir una desconexión nueva por rutina. La carga y el arranque de aplicación son pasos distintos: no añadir GO ni reset automático al final de una verificación de Flash.

## Comprobar la aplicación

El arranque explícito se realiza con `tools/h60_boot.py`, usando el resultado verificado de carga; ver sus opciones en la referencia de herramientas. El banco arranca con entradas de motor bajas y no se mueve por enviar INFO o STATUS.

El puerto siempre se indica explícitamente. Los ejemplos siguientes son **offline**: verifican el manifiesto local y muestran el hash que debe revisarse; no abren el puerto.

```bash
python -m host.pulse_client identify --port /dev/ttyUSB0 --outdir .local/identify
python -m host.pulse_client pulse --port /dev/ttyUSB0 --outdir .local/forward-3s
```

El manifiesto predeterminado se resuelve respecto al repositorio, no respecto al directorio de trabajo. Para otro build, usar `--manifest RUTA`.

Para una consulta real, especificar el SHA256 revisado del manifiesto junto con `--execute`:

```bash
python -m host.pulse_client status --port /dev/ttyUSB0 --outdir .local/status --manifest-sha256 HASH_REVISADO --execute
```

`HASH_REVISADO` se sustituye por los 64 dígitos del manifiesto local comprobado. En Windows se utiliza el ejecutable de la venv y `--port COM3`. El cliente compara el descriptor completo del dispositivo: perfil 4, canales A/B/C/D, inversión B/D, 10 %, 5 kHz, 3000 ms, lease y marcador.

## Ejecutar un único ensayo de avance

Antes de reconectar mazos, retirar de nuevo toda alimentación. Usar un montaje estable que permita el giro libre de las ruedas y un corte de alimentación accesible. La referencia de canales y sentidos debe corresponder al montaje que se va a ensayar.

Con la aplicación arrancada y una consulta coherente en IDLE, el ensayo explícito es:

```bash
python -m host.pulse_client pulse --port /dev/ttyUSB0 --outdir .local/forward-3s --manifest-sha256 HASH_REVISADO --execute
```

El directorio de salida debe ser nuevo. La secuencia verifica quietud, envía STOP/PREPARE, comprueba el lease y transmite **un FIRE**. Mantiene heartbeats durante los tres segundos y exige DONE, consumo 1 y entradas bajas al terminar. Un error solicita STOP, cierra sin reset y no repite FIRE. Puede solicitarse STOP por separado con la acción `stop` y los mismos argumentos de sesión local; sólo un proceso debe tener abierto el puerto.

El resultado `forward-verified` exige cuatro deltas normalizadas positivas. Un contador inverso, insuficiente o ambiguo produce un fallo de dirección o de seguimiento; no corrige una calibración ni provoca otra prueba. DONE conserva el disparo consumido hasta un arranque nuevo explícito. Cambiar el nonce en el host no sustituye ese arranque.

`raw.jsonl` y `result.json` son evidencias locales y pueden incluir puerto, tiempos y nonce de sesión. Conservarlos fuera de cualquier publicación. Este repositorio sólo contiene el [resumen numérico anonimizado](tested-results.md).

## Camino hacia conducción autónoma

El banco deja un mapa probado de canales, encoders y sentidos. Para habilitar autonomía hace falta completar trabajo distinto:

1. Registrar un perfil físico revisado: diámetro efectivo de rueda, vía, cuentas por vuelta y sentidos, geometría y escala de batería. Conservar procedencia y versión de cada medición.
2. Implementar y probar regulación de velocidad por rueda, límites de PWM y aceleración, desarmado, caducidad de órdenes y parada bajo carga. Un 10 % común en lazo abierto no regula cuatro velocidades iguales.
3. Añadir odometría con unidades y tiempos definidos, comprobar IMU y sensores, y contrastar desplazamiento real del chasis.
4. Definir una interfaz de órdenes acotadas desde un supervisor autónomo, con estados, prioridades y reacción a pérdida de comunicaciones. Integrar después planificación y navegación.
5. Validar cada etapa con pruebas reproducibles y criterios de aceptación. Los resultados del banco de tres segundos no habilitan por sí solos conducción continua ni navegación sin supervisión.

Una interfaz manual puede ser útil como herramienta de diagnóstico durante ese trabajo. El producto previsto es conducción autónoma; no se presenta la teleoperación como resultado final de este proyecto.
