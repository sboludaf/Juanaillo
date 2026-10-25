# Diagnóstico de conexión y firmware H60

Esta tabla corresponde a H60 V3.7 y al recorrido de [inicio](getting-started.md). Empezar por las comprobaciones que no abren puertos. Conservar el intento fallido y su error antes de reiniciar nada; no repetir una escritura o una orden de movimiento para averiguar si llegó.

## Comprobar el ordenador sin abrir serie

```bash
python scripts/h60_doctor.py
python tools/h60_recovery.py ports
```

En Linux, si hace falta comprobar quién tiene el puerto, `fuser /dev/ttyUSB0` solo consulta procesos; sustituir el puerto. Si no muestra un proceso de otro usuario, eso no garantiza que el puerto esté libre. Consultar también los mensajes USB recientes con `journalctl -k --since '-5 minutes'`, según los permisos del sistema. No publicar registros completos que contengan identificadores de la unidad.

| Síntoma | Comprobación y siguiente paso |
| --- | --- |
| Se encienden LEDs, pero no aparece puerto | Probar un cable de datos conocido, otro puerto del ordenador y conexión directa. Comparar dispositivos antes/después. La alimentación no demuestra enumeración USB. Revisar [drivers](usb-drivers.md). |
| Aparece un dispositivo, pero el puerto esperado no | Distinguir USB-DEBUG/CH340 de USB-COM/CH9102 por el adaptador detectado y la serigrafía. Este firmware usa USART1 por DEBUG. Los nombres `ttyUSB`/`ttyACM` pueden variar; no bastan para identificar el conector. |
| `Permission denied` | Comprobar propietario/grupo o ACL del dispositivo y las instrucciones de permisos del sistema. Una incorporación a un grupo puede necesitar cerrar y abrir sesión. No usar `chmod 777`, no ejecutar el servidor entero como root y no instalar drivers para resolver un problema de permisos. |
| `Device or resource busy`, acceso exclusivo o respuestas mezcladas | Cerrar monitor serie, otro servidor o cliente de esa misma placa. El servidor web conserva el único puerto; consultar `/api/status` por HTTP mientras está activo. No abrir ROM o un segundo cliente a la vez. |
| El puerto aparece y desaparece o reinicia al abrir | Revisar cable y alimentación. CH340 puede producir un transitorio de reset al abrir; el cliente de aplicación espera 350 ms una sola vez. HUPCL y las líneas DTR/RTS importan: no abrir herramientas de terminal que cambien esas líneas durante otra sesión. |
| El dispositivo se desconecta por un servicio del sistema | Revisar el mensaje concreto del kernel y el proceso que lo reclama. En algunos equipos puede intervenir un servicio de accesibilidad o detección de módem; no se ha demostrado que sea la causa de todos los fallos. Ajustar únicamente el conflicto identificado, con las instrucciones de su distribución; no deshabilitar `brltty` o ModemManager globalmente por rutina. |
| ROM no responde: timeout, NACK o byte inesperado | Confirmar DEBUG, cable, alimentación y que ningún otro proceso lo tiene abierto. ROM es 115200/8E1; `--entry inverted-both` solo corresponde al circuito V3.7 comprobado. Conservar el error. No buscar polaridades, desproteger o repetir tramas a ciegas. |
| Chip, tamaño o revisión no coinciden | No cargar este plan. PID `0x0413` identifica una familia; no garantiza V3.7 ni 512 KiB. Este flujo exige identidad y tamaño reales antes del borrado. |
| Las dos copias de Flash difieren | El backup no es un baseline válido. Conservar ambas lecturas y revisar comunicación/alimentación. No borrar la placa ni elegir arbitrariamente una copia como válida. |
| El importador rechaza hashes o no encuentra archivos | Obtener el paquete STM32 de H60 V3.7 indicado por el lock. No usar el firmware de fábrica, recursos ROS o el paquete TB6612 como sustitutos. No omitir los hashes para forzar otra revisión. |
| `arm-none-eabi-gcc` o `make` no existe | Preparar las dependencias del ordenador según la [guía de inicio](getting-started.md#1-preparar-el-ordenador-sin-conectar-la-placa). Los tests nativos necesitan un compilador C del ordenador; el build ARM necesita la toolchain Arm. |
| Faltan `stdint.h`, `libc_nano` u otras partes de newlib | Comprobar que la toolchain tiene cabeceras y bibliotecas newlib. Si la distribución las separa, usar los overrides documentados `NEWLIB_INCLUDE` y `NEWLIB_LIB_DIR`; no sustituir archivos del fabricante sin revisar. |
| El plan rechaza hashes o el build cambió | No modificar el plan para saltar la comprobación. Restaurar los inputs revisados o reconstruir, crear otro plan y revisarlo. El plan vincula también fuentes y herramientas. |
| `Current Flash differs from the baseline; no erase` | La placa viva ya no contiene la copia esperada. No omitir la comparación. Revisar qué operación anterior ocurrió y usar un baseline respaldado o el readback completo verificado de la carga anterior, con su procedencia. |
| La carga dice `verified`, pero no responde la aplicación | Cargar y arrancar son fases distintas. Usar `h60_boot.py` con el resultado verificado, no repetir la carga. Después consultar el perfil 6 a 230400/8N1. |
| `application_response_verified: false` al arrancar | Es normal: el comando de arranque transmite cero bytes UART. La respuesta se comprueba después mediante CAPS/STATUS o el servidor web. |
| El directorio, plan o registro de arranque ya existe | Las herramientas no sobrescriben evidencias ni repiten un intento automáticamente. Revisar el resultado existente antes de decidir otro intento con un nombre nuevo. No borrar el registro para provocar una repetición accidental. |
| Descriptor/manifiesto incompatible, perfil 4 o 5 | La web actual necesita `manual-hold` perfil 6 y el manifiesto de su build. Perfil 4 es el ensayo de tres segundos; perfil 5 carece de giros. Preparar y revisar el firmware correcto, sin adaptar silenciosamente las órdenes a uno antiguo. |
| El firmware de fábrica no entiende STATUS/MOVE | El protocolo documentado aquí corresponde a las aplicaciones propias publicadas. No se afirma que el firmware de fábrica lo acepte. Respaldar e instalar deliberadamente la aplicación antes de usar su cliente. |
| Apagué y encendí la H60 y la web sigue en error | El fallo serie del servidor queda bloqueado. Con alimentación recuperada, detener y volver a iniciar explícitamente el servidor; abrir el enlace nuevo. No hace falta volver a grabar por un ciclo normal de alimentación. |
| Después de reiniciar, la web rechaza la clave | Cada arranque del servidor crea un token nuevo. Usar el enlace recién impreso, incluido el fragmento; el enlace antiguo no corresponde a la sesión actual. |
| Otro navegador ya controla la sesión | Ese navegador es el propietario. Cerrar o liberar esa conexión; no tomar el control desde otro cliente mientras está activo. La consulta HTTP de estado no reclama propiedad. |
| Pulsé dos controles y ahora pide soltarlos | Soltar todos los dedos, teclas y punteros. El conflicto solicita STOP recuperable; una liberación parcial o heartbeat no reanuda el gesto. Esperar reposo confirmado y hacer una pulsación nueva. |
| Se detiene tras mantener pulsado | Hay un límite absoluto de 10 s por gesto. Soltar, esperar la parada y hacer otra pulsación deliberada. No usar heartbeats o cambios de dirección para alargarlo. |
| FAULT, lease vencido o fallo de hardware | Guardar `firmware_reason`, explicación y registro privado antes de cualquier reset. Un STOP desactiva salidas, pero no limpia un FAULT real. Diagnosticarlo y realizar cualquier reinicio como operación separada, nunca para reanudar una orden vieja. |
| Fallo de activación de PWM en una revisión antigua del perfil 6 | El build actual mide wake por DWT desde después de GPIO11/DSB y exige `wake_scheduler: dwt-qualified`, `wake_max_ms: 6`. CAPS por sí solo no distingue ambos builds del perfil 6; comprobar manifiesto y procedencia de la carga. La [validación](validation.md#corrección-del-origen-temporal-de-wake) explica el defecto reproducido, sin atribuirle retrospectivamente un FAULT cuyo motivo no se conservó. |
| Algunas ruedas avanzan y otras retroceden | Detener y comprobar el mapa A/B/C/D y la orientación física. El R5 probado requiere inversión B/D en avance; esa referencia no es una calibración universal. No subir PWM para corregir una polaridad. |
| Cuatro ruedas no giran igual con el mismo PWM | El firmware es de banco en lazo abierto. PWM común no regula velocidad por encoder ni garantiza distancia, ángulo o trayectoria. Es trabajo posterior de calibración y control. |

## Datos útiles para pedir ayuda

Indicar revisión de placa, sistema operativo, conector usado, identificador público del chip USB, comando ejecutado sin claves y error exacto. Distinguir la etapa: enumeración USB, permisos, ROM, backup, importación, compilación, carga, arranque o aplicación. Para la web, acompañar el estado de conexión/perfil y el motivo del fallo.

Mantener privados UID del MCU, dumps de Flash, rutas personales, claves, enlaces con token y registros crudos. Los contadores de encoder de una sesión fallida pueden ser antiguos; no presentarlos como telemetría actual. Los [resultados probados](tested-results.md) indican qué mediciones físicas se han realizado y cuáles siguen pendientes.
