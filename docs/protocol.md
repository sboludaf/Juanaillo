# Protocolo del banco de avance de tres segundos

Este contrato corresponde al perfil **4** y al marcador `H60_FORWARD3S_SINGLE_SHOT_V1`. Ejecuta una sola secuencia fija por arranque: cuatro motores, direcciones `[+1, −1, +1, −1]`, PWM diferencial del 10 % a 5 kHz durante 3000 ms. No ofrece órdenes de velocidad, armado general, teleoperación ni navegación autónoma.

## Transporte y trama

USB-DEBUG usa USART1 a **230400, 8N1**, sin RTS/CTS. El cliente pide DTR activo y RTS inactivo para mantener BOOT bajo y reset liberado en el circuito V3.7 probado. No genera un pulso de reset al abrir la aplicación. En Linux desactiva HUPCL; la rama Windows admite puertos COM, pero su comportamiento físico aún no se ha validado.

Una trama es `AA 55 LEN ID PAYLOAD SUM8`. `LEN` cuenta toda la trama, incluidos sus cinco bytes fijos. `SUM8` es la suma módulo 256 de todos los bytes anteriores. Los enteros multibyte del payload están en orden **big-endian**. La respuesta conserva el ID de la petición.

Ejemplos sin nonce ni movimiento:

| Petición | Bytes completos |
| --- | --- |
| STATUS | `AA 55 05 70 74` |
| INFO/CAPS | `AA 55 05 76 7A` |
| STOP | `AA 55 05 74 78` |

El parser de firmware acepta peticiones de hasta 13 bytes. Una trama inválida o incompleta durante 30 ms lleva a FAULT. El cliente no busca otra cabecera ni repite una transacción después de una respuesta inesperada, checksum erróneo o timeout.

## Órdenes

| ID | Nombre | Payload de petición | Respuesta |
| --- | --- | --- | --- |
| `0x70` | STATUS | Vacío | Estado de 36 bytes |
| `0x76` | INFO/CAPS | Vacío | Descriptor de 48 bytes |
| `0x63` | ENCODERS | Vacío | Cuatro `uint16`, orden A/B/C/D |
| `0x74` | STOP | Vacío | Estado; desactiva salidas |
| `0x71` | PREPARE | Nonce del arranque, `uint64` | Estado READY si se cumplen condiciones |
| `0x75` | KEEPALIVE | Mismo nonce, `uint64` | Estado; renueva lease vigente |
| `0x73` | FIRE | Mismo nonce, `uint64` | Estado con disparo ya consumido |

Por compatibilidad, `0x62` vacío y `0x50` con seis bytes cero también solicitan STOP. No se utiliza `0x50` con una velocidad distinta de cero.

El nonce lo genera el RNG del STM32 al arrancar; el host lo lee de STATUS y lo devuelve sin sustituirlo. Cambiar de nonce en la sesión es un error. Un fallo del RNG deja el firmware en FAULT. Esto evita repetir paquetes de un arranque anterior; no autentica el UID de la placa ni demuestra qué imagen contiene. La asociación con la imagen se establece mediante compilación, manifiesto, carga y readback separados.

## Descriptor CAPS, 48 bytes

El prefijo usa `>BBBBHHHHII`; a continuación van los 28 bytes ASCII del marcador, sin terminador NUL en la respuesta.

| Offset | Tipo | Campo | Valor fijo |
| ---: | --- | --- | --- |
| 0 | `uint8` | Versión | 1 |
| 1 | `uint8` | Perfil | 4 |
| 2 | `uint8` | Máscara de canales | 15: A/B/C/D |
| 3 | `uint8` | Máscara de inversión | 10: B/D |
| 4 | `uint16` | Duty diferencial, milésimas | 100 |
| 6 | `uint16` | Frecuencia PWM, Hz | 5000 |
| 8 | `uint16` | Espera mínima de activación, ms | 3 |
| 10 | `uint16` | Duración PWM, ms | 3000 |
| 12 | `uint32` | Envolvente desde FIRE, µs | 3005000 |
| 16 | `uint32` | Lease, ms | 100 |
| 20 | ASCII[28] | Marcador | `H60_FORWARD3S_SINGLE_SHOT_V1` |

El cliente exige igualdad de todos los campos y del marcador antes de PREPARE/FIRE. No acepta como equivalente otro perfil que anuncie sólo la misma duración.

## Estado STATUS, 36 bytes

Formato: `>BBBBIIQ4HII`.

| Offset | Tipo | Campo |
| ---: | --- | --- |
| 0 | `uint8` | Versión |
| 1 | `uint8` | Perfil |
| 2 | `uint8` | Estado |
| 3 | `uint8` | Flags |
| 4 | `uint32` | Tiempo desde arranque, ms |
| 8 | `uint32` | Lease restante, ms |
| 12 | `uint64` | Nonce del arranque |
| 20 | `uint16[4]` | Contadores A/B/C/D |
| 28 | `uint32` | Número de disparos consumidos: 0 o 1 |
| 32 | `uint32` | Motivo (`reason`) |

Estados: `0 IDLE`, `1 READY`, `2 WAKE`, `3 RUNNING`, `4 DONE`, `5 FAULT`.

| Bit de flags | Significado |
| ---: | --- |
| 0 | Imagen capaz de activar motores |
| 1 | Disparo consumido; no se limpia hasta un nuevo arranque |
| 2 | Salida solicitada por WAKE/RUNNING |
| 3 | Entradas GPIO y temporizadores comprobados en estado bajo/desactivado |

IDLE/READY requieren `0x09`, WAKE/RUNNING `0x07` y DONE `0x0B`. El bit 3 describe comprobaciones del controlador, no una medición eléctrica externa.

Motivos: `0 BOOT`, `1 STOP`, `2 PREPARED`, `3 FIRED`, `4 FINISHED`, `5 LEASE`, `6 FRAME`, `7 NONCE`, `8 SEQUENCE`, `9 MOVING`, `10 LATE`, `11 HARDWARE`, `12 RNG`. El STOP final puede dejar `reason=1` conservando DONE y el contador de disparos en 1.

## Secuencia y tiempos

1. INFO/CAPS y STATUS deben coincidir con la imagen revisada. Se requiere IDLE sin disparo previo.
2. El host envía STOP y observa los cuatro encoders quietos durante al menos 1,1 s. El firmware exige 1000 ms de quietud.
3. Un STOP reciente, de como máximo 500 ms, precede a PREPARE. READY dura como máximo 300 ms desde el primer PREPARE y su lease de 100 ms debe mantenerse vigente. Repetir PREPARE no alarga ese plazo.
4. El host valida READY, nonce, flags y lease otra vez. Marca FIRE como intentado antes de transmitirlo y nunca lo repite.
5. El firmware consume el disparo antes de activar GPIO. WAKE valida una espera real de 3–4 ms; RUNNING aplica el patrón fijo durante 3000 ms.
6. KEEPALIVE se envía aproximadamente cada 20 ms durante la actividad. Un lease caducado no se revive con un heartbeat tardío.
7. El firmware corta por tiempo de PWM o envolvente software de 3005 ms desde FIRE. El host espera DONE hasta un plazo de 3,25 s y solicita STOP ante error.
8. Se comprueban DONE, flags `0x0B`, consumo 1 y encoders estabilizados. DONE no vuelve a READY con PREPARE/HB/FIRE. FAULT tampoco se rearma por protocolo.

Los cuatro canales usan corte software DWT/ISR/bucle y un IWDG de respaldo. La envolvente programada no constituye una garantía independiente de corte eléctrico ante cualquier avería. No se afirma que el oscilador LSI del IWDG aporte un plazo eléctrico exacto.

## Lectura de movimiento

El host acumula deltas de muestras sucesivas con aritmética modular de 16 bits, usando el tiempo del firmware. Rechaza saltos incompatibles con 10000 cuentas/s, huecos de más de 250 ms y totales absolutos mayores de 32767. No aplica el antiguo límite de media vuelta: un ensayo de tres segundos puede acumular miles de cuentas.

Con los signos manuales `[-1,+1,-1,+1]`, sólo declara `forward-verified` cuando los cuatro totales normalizados son positivos y de al menos ocho cuentas. Un resultado inverso o inconcluso no provoca otra prueba ni modifica un perfil físico. Se guardan muestras raw y resultado en un directorio nuevo; los registros reales permanecen fuera del repositorio público.
