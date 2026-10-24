---
name: h60-wheels
description: Calibrar encoders, relacionar canales y ruedas, comprobar polaridad o ejecutar ensayos motrices limitados de OpenCTR H60 usando las referencias medidas.
---

# Encoders y ruedas

Lee `docs/hardware.md`, `docs/tested-results.md` y el perfil elegido en `profiles/`. Usa `docs/protocol.md` para cambios de cliente/firmware.

Los datos del R5 ensayado son un ejemplo: A=trasera derecha, B=trasera izquierda, C=delantera derecha, D=delantera izquierda. Se adoptaron 1561 cuentas/vuelta, encoder_sign `[-1,+1,-1,+1]` y motor_sign `[+1,-1,+1,-1]`. Otra instalación necesita sus propias referencias; no deduzcas motor_sign a partir de encoder_sign.

Para calibrar, parte de una marca y un número de vueltas declarados por el operador. Conserva deltas netas, sentido y repeticiones; excluye una tanda si se pidió repetirla y documenta el motivo real, sin inventar una avería. Dividir cuentas por vueltas produce una estimación; el valor común 1561 fue una decisión de ingeniería, no un nominal universal del fabricante.

Para una orden eléctrica positiva conocida, `motor_sign = encoder_sign * sign(delta_raw)`. Para comprobar avance ya corregido, exige `encoder_sign * delta_raw > 0` en cada rueda. No confundas el ensayo antiguo raw-positive de los cuatro con el firmware actual que invierte B/D.

Ejecuta movimientos solo dentro de la petición activa y con las condiciones físicas conocidas: ruedas elevadas, chasis estable, sin manos en las ruedas y corte accesible. No pidas confirmar de nuevo la misma autorización de una sesión. Anuncia duración y sentido antes de actuar. Si falta un dato físico necesario, pregunta solo por ese dato.

El cliente de la prueba de 3 s verifica perfil/descriptor/nonce y un disparo por arranque. Durante los 3 s renueva el heartbeat aproximadamente cada 20 ms; la aplicación caduca a 100 ms. Para repetir por petición expresa se necesita un arranque nuevo controlado; un reset no es permiso para repetir automáticamente.

Los encoders son uint16. En una prueba larga sigue muestras frecuentes para resolver wraps y detectar saltos, no apliques el límite de media vuelta del ensayo corto. Guarda observación visual si existe; no la inventes ni obligues a ocho nuevas pruebas manuales cuando las referencias ya son válidas.

Al acabar comprueba DONE, salidas bajas según registros y encoders estabilizados. Esto no certifica tensión/corriente ni duración eléctrica. La prueba fija tampoco valida PID, odometría o conducción autónoma.

Para la web temporal lee `web/README.md` y `firmware/manual-hold/README.md`: perfil 6 con MOVE/STOP reutilizables, heartbeat de navegador, lease serie de 150 ms y límite absoluto de 10 s. MOVE `+1/-1` indica avance/retroceso y `+2/-2` giro izquierda/derecha sobre el sitio. En el R5 medido, izquierda usa A/B/C/D `[+1,+1,+1,+1]` eléctricos y derecha `[-1,-1,-1,-1]`: un lado avanza y el otro retrocede. El perfil 5 anterior solo admitía avance/retroceso; no le envíes órdenes de giro ni lo aceptes como perfil 6. No lo trates como un FIRE de perfil 4 ni fuerces resets entre pulsaciones normales. Un fallo serie queda bloqueado; no reanudes una pulsación vieja tras reconectar o alcanzar el límite. Verifica UI contra simulación; acceder a una página de QA no autoriza a mover una placa real.
