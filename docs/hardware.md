# Hardware y referencias de la unidad probada

La referencia física es una OpenCTR H60 V3.7 con STM32F407VET6 y cuatro motorreductores CC con encoder. Se identificaron 512 KiB de Flash interna. Estos datos describen una unidad y su cableado; las revisiones, motores o conectores de otra unidad deben comprobarse de nuevo.

## Placa y conexiones

| Elemento | Referencia utilizada |
| --- | --- |
| Microcontrolador | STM32F407VE, Cortex-M4, reloj validado a 168 MHz |
| Alimentación de placa | Entrada anunciada de 7–17 V CC; verificar también la tensión nominal de los motores |
| Puentes de motor | Cuatro canales con AT8236 |
| USB-DEBUG | USART1, PA9 TX / PA10 RX; empleado por el banco actual |
| USB-COM | USART3, PD8 TX / PD9 RX; no es el puerto usado por este banco |
| Aplicación | 230400 baudios, 8N1, sin control de flujo |
| ROM ISP por DEBUG | 115200 baudios, 8E1; sesión distinta de la aplicación |

La cifra anunciada de 50 A corresponde al interruptor MOSFET general. No representa una corriente continua validada por motor. Este trabajo no caracteriza corriente de bloqueo, temperatura, par ni carga admisible.

Los conectores de motor llevan las etiquetas `P+`, `G`, `A`, `B`, `5V`, `P−` en la serigrafía inferior. `P+`/`P−` son salidas del puente hacia el motor; `A`/`B` son señales del encoder y `G` su masa. La vista inferior se refleja al mirar desde arriba. Verificar orientación y niveles del encoder antes de reutilizar un mazo: la etiqueta `5V` no basta para deducir la tolerancia lógica de sus señales.

## Mapa medido de las ruedas

Las posiciones se describen mirando el chasis hacia su avance. Los signos pertenecen a esta unidad y no deben copiarse como calibración universal.

| Canal | Índice de encoder | Rueda | `encoder_sign` | Dirección de salida ensayada / `motor_sign` |
| --- | ---: | --- | ---: | ---: |
| A | 0 | Trasera derecha | −1 | +1 |
| B | 1 | Trasera izquierda | +1 | −1 |
| C | 2 | Delantera derecha | −1 | +1 |
| D | 3 | Delantera izquierda | +1 | −1 |

`encoder_sign × delta_raw` da el incremento positivo de avance. La secuencia de salida `[+1, −1, +1, −1]` consiguió cuatro incrementos de avance positivos en tres rondas de tres segundos. La referencia de A se contrastó además visualmente en un ensayo individual. Los datos están en [resultados probados](tested-results.md).

Se adoptaron **1561 cuentas por vuelta de rueda**, a partir de ocho ensayos manuales de cinco vueltas y una elección común del operador. Son cuentas del temporizador observadas en la rueda, no una especificación de PPR del sensor antes de la reductora. Para otra unidad hay que medir su valor.

## Salidas utilizadas por el firmware de banco

| Canal | Temporizador y canales | GPIO |
| --- | --- | --- |
| A | TIM1 CH1/CH2 | PE9 / PE11 |
| B | TIM1 CH3/CH4 | PE13 / PE14 |
| C | TIM9 CH1/CH2 | PE5 / PE6 |
| D | TIM12 CH1/CH2 | PB14 / PB15 |

El PWM es diferencial a 5 kHz. El 10 % describe la diferencia entre las dos entradas del puente; no significa que ambas señales tengan individualmente un ciclo del 10 %. Al desactivar, el firmware devuelve las ocho entradas a GPIO con nivel `00` y deshabilita los temporizadores.

En el ensayo de tres segundos **todos los canales dependen de corte software por DWT/SysTick y del bucle principal**, con IWDG de respaldo. No hay un corte autónomo OPM/RCR que garantice por sí solo los tres segundos. `ALL_LOW` comprueba registros GPIO y temporizadores, incluida lectura IDR; no mide la tensión externa del motor ni demuestra que una rueda se haya detenido mecánicamente.

## Límites de esta referencia

El banco valida mapeo, sentido, comunicación y cierre del ensayo. No establece diámetro efectivo de rueda, vía, odometría, ganancias PID, escala de batería, geometría de carga ni comportamiento autónomo. Esas mediciones forman parte de la [habilitación futura](bring-up.md#camino-hacia-conducción-autónoma).
