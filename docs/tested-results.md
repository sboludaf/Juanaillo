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
