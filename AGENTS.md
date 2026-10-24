# Working with OpenCTR H60 Lab

Este repositorio documenta una H60 V3.7 real. El objetivo futuro es conducción autónoma; el estado actual es puesta en marcha y firmware de banco. Lee primero `README.md`, `docs/hardware.md` y `docs/tested-results.md`. Usa las instrucciones del usuario de la sesión para concretar el trabajo, sin inferir autorización para publicar ni mover hardware por el mero hecho de abrir el repositorio.

## Skills del proyecto

Abre solo la skill pertinente; sus rutas son relativas a este repositorio y funcionan sin instalar nada globalmente.

| Petición | Skill |
|---|---|
| Identificar placa, puertos, bootloader o preparar respaldo | `skills/h60-bringup/SKILL.md` |
| Importar, compilar, revisar plan, cargar o recuperar firmware | `skills/h60-flash/SKILL.md` |
| Encoders, correspondencia de ruedas, polaridad o ensayo motriz | `skills/h60-wheels/SKILL.md` |
| Preparar material para GitHub público | `skills/h60-public-release/SKILL.md` |

## Datos que cambian las decisiones

- H60 V3.7 y revisiones V3.2/V3.6 no comparten todos los detalles de drivers, IMU y UART. Verifica la revisión y el enrutado antes de portar firmware.
- USB-DEBUG usa USART1 PA9/PA10 y el adaptador CH340 en la unidad ensayada. USB-COM usa USART3 PD8/PD9 y CH9102. No interpretes LEDs de alimentación como enumeración USB.
- El bootloader ROM se identificó como 0x31/PID0x0413 y 512 KiB. Obtén identidad/tamaño de la unidad presente, sin fijar su UID en código o planes públicos.
- A/B/C/D fueron trasera derecha / trasera izquierda / delantera derecha / delantera izquierda en el R5 ensayado. El ejemplo usa encoder_sign `[-1,+1,-1,+1]` y motor_sign `[+1,-1,+1,-1]`. Revalidar en otro montaje; no deducir un signo del otro.
- `forward-3s` aplica la inversión B/D en el PWM. El antiguo ensayo con dirección eléctrica positiva en los cuatro no lo hacía: confundir ambos produciría giro contrario en las izquierdas.
- La web temporal usa `firmware/manual-hold`, perfil 6: avance, retroceso y giro sobre el sitio izquierda/derecha; MOVE/STOP reutilizables, lease 150 ms y límite absoluto 10 s hasta soltar y pulsar de nuevo. El perfil 5 anterior solo admite avance/retroceso y el backend actual lo rechaza antes de MOVE. No aplicar estos protocolos al perfil 4 de 3 s. No hay movimiento automático al abrir la web; una sesión autenticada debe mantener una pulsación vigente.
- Para el R5 medido, las órdenes lógicas MOVE son `+1` avance, `-1` retroceso, `+2` izquierda y `-2` derecha. Los giros usan direcciones eléctricas A/B/C/D `[+1,+1,+1,+1]` y `[-1,-1,-1,-1]`, respectivamente. Esto aplica las polaridades físicas conocidas; no confundir derecha/izquierda con el signo eléctrico de un único motor.
- Los 3 segundos se cortan por software ISR/DWT, con IWDG y caducidad de órdenes como respaldo. No describirlo como un corte eléctrico certificado o un temporizador autónomo de 3 s.
- La toolchain, las pruebas, la importación de fuentes y la lectura de archivos no deben abrir puertos serie. No añadas movimiento al conectar USB, descubrir el dispositivo, arrancar o compilar.

## Hardware y autorización

Mantén una separación clara entre comprobaciones offline, lecturas ROM, escritura de Flash y movimiento. Si la sesión ya autoriza una operación y las condiciones físicas siguen siendo conocidas, continúa sin pedir la misma confirmación de nuevo. Anuncia un ensayo motriz inmediatamente antes de ejecutarlo e indica duración, sentido, ruedas elevadas y corte de alimentación accesible. Si falta una condición física necesaria, pide solo ese dato.

No ejecutes ensayos físicos como parte de tests/CI. Un FIRE por arranque y un nonce nuevo no justifican repetir automáticamente: un nuevo pulso necesita estar dentro de la petición activa del usuario. Conserva el intento y el resultado incluso si falla. Ante una respuesta dudosa, STOP si es posible, cierre y diagnóstico; nunca reenvíes FIRE a ciegas.

## Cambios y validación

- Conserva los ZIP y respaldos originales fuera del árbol publicable. Modifica fuentes propias o prepara parches/importaciones deterministas; no edites silenciosamente el paquete del fabricante.
- Antes de cambiar un protocolo, comprueba sus dos extremos: descriptor, perfil, longitudes, nonce, estado, heartbeat, STOP y one-shot. Las pruebas de una versión anterior no validan un descriptor nuevo.
- Una imagen de banco no habilita el perfil general de conducción. No inventes PID, geometría, tensión calibrada o límites para satisfacer el validador.
- Ejecuta las pruebas offline adecuadas al cambio y registra qué se comprobó realmente. Distingue resultado de software, observación visual y medición eléctrica.
- No publiques material privado. Usa `scripts/check_public_tree.py` antes de un commit destinado a GitHub y revisa también el contenido/historial. Consulta `docs/publication.md`.
