# Resultados probados

Resumen numérico anonimizado de una unidad H60 V3.7, obtenido el **24 de octubre de 2026**. No se distribuyen registros de conexión, nonce reales, identificadores de placa, fotografías privadas ni copias del firmware de fábrica. Los números permiten revisar qué se midió y qué permanece pendiente.

## Encoders: ocho ensayos manuales

En cada ensayo se declararon cinco vueltas de rueda en sentido de avance. No se enviaron órdenes de movimiento. La tabla usa el incremento neto del encoder de la rueda manipulada; el orden A/B/C/D quedó asociado al chasis mediante observación individual.

| Canal | Rueda | Ensayo | Cuentas netas | Magnitud por vuelta |
| --- | --- | ---: | ---: | ---: |
| A | Trasera derecha | 1 | −7791 | 1558,2 |
| A | Trasera derecha | 2 | −7818 | 1563,6 |
| B | Trasera izquierda | 1 | +7816 | 1563,2 |
| B | Trasera izquierda | 2 | +7792 | 1558,4 |
| C | Delantera derecha | 1 | −7808 | 1561,6 |
| C | Delantera derecha | 2 | −7809 | 1561,8 |
| D | Delantera izquierda | 1 | +7800 | 1560,0 |
| D | Delantera izquierda | 2 | +7765 | 1553,0 |

Una captura adicional de la trasera derecha se excluyó por petición explícita de repetir el ensayo. No se atribuye una causa técnica al descarte.

La media global es **1559,975 cuentas/vuelta**. Se eligió **1561** como valor común para esta unidad, por decisión del operador. No es una especificación exacta del fabricante ni una calibración transferible a cualquier motor. Los signos manuales resultantes son `[-1,+1,-1,+1]`.

## Dirección de salida

La observación de las ruedas y los ensayos conjuntos llevaron a invertir B y D. La referencia de salida de avance es:

```text
orden de canales: A  B  C  D
motor_sign:       +1 -1 +1 -1
encoder_sign:     -1 +1 -1 +1
```

A se contrastó visualmente en una prueba individual. Los resultados conjuntos siguientes comprueban además cuatro incrementos normalizados de avance positivos con el patrón corregido. No se modificó automáticamente ningún archivo de calibración a partir de un ensayo.

## Tres rondas de avance de tres segundos

Condición fija de las tres rondas: cuatro motores, duty diferencial 100‰, 5 kHz, PWM programado de 3000 ms, máscara de inversión `0x0A`, nonce nuevo por arranque y heartbeat durante el ensayo.

| Ronda | Delta raw A | Delta raw B | Delta raw C | Delta raw D | Muestras seguidas |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | −2738 | +2955 | −2808 | +2686 | 113 |
| 2 | −2826 | +2982 | −2817 | +2782 | 114 |
| 3 | −2816 | +2989 | −2912 | +2860 | 114 |

Al aplicar los signos de encoder, todos los valores son positivos:

| Ronda | Avance A | Avance B | Avance C | Avance D |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 2738 | 2955 | 2808 | 2686 |
| 2 | 2826 | 2982 | 2817 | 2782 |
| 3 | 2816 | 2989 | 2912 | 2860 |

Las tres terminaron con `forward-verified`, estado DONE, flags `0x0B` y un solo disparo consumido. El STOP posterior dejó `reason=STOP`; las salidas se comprobaron bajas mediante registros GPIO/temporizadores. No se hizo una medición externa de tensión de motor ni un registro de osciloscopio que certificara los tiempos eléctricos.

La diferencia entre cuentas de ruedas muestra que un PWM común no equivale a regular una velocidad común. Estas pruebas no validan distancia recorrida por el chasis, seguimiento de trayectoria, odometría ni conducción autónoma.

El BIN propio empleado en esas rondas tenía 7132 bytes y SHA256:

```text
8fc79c5214a0521d9351b803d8b5353a81b6df3d0bfbb7280648b7aac7fa5feb
```

El repositorio conserva fuentes para reconstruirlo; no publica el BIN ni el firmware de fábrica. Un manifiesto generado localmente debe verificarse junto con sus fuentes y artefactos antes de utilizar otra compilación.

## Verificación de software y alcance

El cliente original y el ensayo físico se usaron en Linux con pyserial 3.5. La versión portable conserva la lógica de nonce, FIRE único, heartbeat, STOP y análisis, y añade rutas relativas y selección de puertos COM. La rama Windows sólo tiene pruebas simuladas: **no se declara una prueba física en Windows**.

Las pruebas offline del host cubren pérdida de heartbeat, caducidad que no se revive, STOP tras error, FIRE sin repetición, descriptores incompatibles, nonce cambiado, contadores con wrap y saltos ambiguos. Un puente serial simulado ejecuta también el núcleo C real con ticks de 1 ms. Estas pruebas verifican lógica y contrato; no sustituyen las comprobaciones eléctricas ni las pruebas de carga del robot.

Las herramientas ROM portables incorporadas al preparar el repositorio se validaron con una ROM simulada. No se repitieron identificación, copia ni grabación físicas durante ese empaquetado. El BIN de aplicación reconstruido sí coincide byte a byte con el de 7132 bytes empleado en las tres rondas físicas.

Para reproducir la verificación actual, seguir [bring-up](bring-up.md). Para ampliar el proyecto hacia autonomía hay trabajo pendiente de geometría, control de velocidad, odometría, sensores y supervisión.

## Control web temporal

Con perfil 5 se validó un recorrido completo WebSocket autenticado → servidor → USB-DEBUG → H60 y STOP. Una pulsación breve de avance produjo deltas A/B/C/D `[-341,+385,-357,+346]`; retroceso produjo `[+307,-382,+294,-208]`. Ambas terminaron paradas y la sesión quedó en IDLE, sin una orden sostenida. No se guardan aquí claves, puertos personales ni registros crudos.

El nuevo flujo portable de recuperación y carga también obtuvo dos lecturas reales concordantes de 512 KiB y verificó la carga completa del perfil 5. La validación eléctrica de corriente, tensión y tiempos exactos sigue fuera del alcance de estos resultados.

## Ampliación de giros, perfil 6

La web y `manual-hold` incorporan giros sobre el sitio a izquierda y derecha. Se mantienen el PWM del 10 %, el lease de 150 ms y el límite absoluto de 10 s. Las nuevas órdenes son `+2/-2` y los patrones eléctricos A/B/C/D son `[+1,+1,+1,+1]` para izquierda y `[-1,-1,-1,-1]` para derecha, aplicando el mapa de ruedas y polaridades ya medido.

Nueve grupos nativos comprueban los cuatro patrones de comparadores PWM y las 32 transiciones entre órdenes en RUNNING y WAKE, además de STOP, lease, nonce y límite compartido. El build ARM de 7256 bytes se reprodujo con BIN/HEX idénticos; SHA256 del BIN:

```text
a6367b446f48201e441a4d5518bab7f93f5a3578410357b708ccea7ad6e4e282
```

Esta ampliación se preparó con la placa apagada. Después de que el operador la encendiera, se compararon los 512 KiB vivos con el readback previo del perfil 5, se modificó solo el sector 0 y se verificó la Flash completa. SHA256 posterior: `640605cd84df3b0978b4776867524c0042d1f875dc76074ef1fa00494be5bd4f`. Los sectores 1–7 quedaron conservados.

Se arrancó el perfil 6 y se comprobó la conexión real por USB-DEBUG, descriptor, estado IDLE, WebSocket autenticado y STOP. La sesión solo transmitió INFO, STATUS y STOP; no se enviaron órdenes MOVE. Los giros siguen pendientes de ensayo motriz: la evidencia real del perfil 5 anterior no valida por sí sola los giros ni el comportamiento en suelo.

## Corrección de pulsaciones simultáneas y sincronización

Las entradas simultáneas ahora provocan STOP recuperable, conservan la sesión y exigen soltar todos los controles antes de una pulsación nueva. Las pruebas de navegador se hicieron solo en simulación con dos dedos reales, teclado y combinaciones de entrada; no se enviaron movimientos reales para esa comprobación.

Se corrigió además un defecto de sincronización de wake: el origen físico se captura después de GPIO11/DSB y la activación PWM se califica por DWT dentro de 4–6 ms, con lease y duración absoluta intactos. Once grupos nativos comprueban fases de tick y costes de configuración; véase [validación](validation.md). No se pudo determinar el motivo exacto del FAULT que originó esta revisión, porque el servidor anterior no lo conservó antes del reinicio.

El BIN corregido de 7444 bytes, SHA256 `2f742d7f3f479d744e8ded4b70657313c9477230b02d565ea1c0082b5e0898a2`, se cargó tras comparación completa con la imagen anterior. Se modificó solo el sector 0 y el readback completo coincidió con `a07f171eff058c03dbeb66c3a2e3a2cf90c5070666681cf9bfc9f9873f681546`; sectores 1–7 conservados. Se verificaron arranque, conexión real, WebSocket autenticado y STOP/IDLE sin MOVE. Esto no acredita una medición eléctrica ni un nuevo ensayo motriz.
