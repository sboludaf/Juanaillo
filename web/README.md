# Web local de conducción

Interfaz temporal con cuatro botones, **Avance, Retroceso, Izquierda y Derecha**: mantener pulsado mueve; soltar detiene. Funciona con ratón, pantalla táctil y teclado. Los giros se realizan sobre el sitio, con un lado avanzando y el otro retrocediendo. Perder foco, ocultar la página, cerrar la conexión o dejar de renovar el control provoca parada. Cada pulsación tiene un máximo de 10 s; al alcanzarlo hay que soltar y pulsar de nuevo.

Es una herramienta de diagnóstico para un chasis estable y ruedas elevadas, previa al desarrollo de conducción autónoma. Mantiene el PWM fijo al 10 %; no regula velocidad por encoders.

## Firmware requerido

Necesita `firmware/manual-hold`, **perfil 6**. El perfil 5 anterior solo admitía avance/retroceso y debe actualizarse; el firmware de avance fijo de 3 s, perfil 4, tampoco acepta este protocolo. El backend exige el descriptor del perfil 6 antes de cualquier MOVE y no envía órdenes de giro a una versión anterior.

El mapa del R5 medido es A=trasera derecha, B=trasera izquierda, C=delantera derecha y D=delantera izquierda:

| Botón | Valor MOVE | Sentidos eléctricos A/B/C/D | Movimiento físico |
| --- | ---: | --- | --- |
| Avance | +1 | `[+1,-1,+1,-1]` | Ambos lados avanzan |
| Retroceso | -1 | `[-1,+1,-1,+1]` | Ambos lados retroceden |
| Izquierda | +2 | `[+1,+1,+1,+1]` | Derechas avanzan; izquierdas retroceden |
| Derecha | -2 | `[-1,-1,-1,-1]` | Izquierdas avanzan; derechas retroceden |

Otras instalaciones deben comprobar su propio mapa. Al girar con cuatro ruedas fijas se produce deslizamiento lateral; el PWM común no garantiza una velocidad angular ni un ángulo concreto.

Las flechas y WASD equivalen a los cuatro botones. Espacio o Enter actúan sobre el botón que tiene el foco. Los atajos con Ctrl, Meta o Alt no inician movimiento y detienen una pulsación vigente.

El dispositivo caduca MOVE a 150 ms y limita un gesto a 10 s. El servidor renueva MOVE aproximadamente cada 50 ms solo mientras tiene una intención de navegador vigente; el navegador la renueva cada 50 ms y el servidor la caduca a 250 ms. El límite de 10 s no se extiende con heartbeats ni con cambios de dirección. Antes de cambiar el patrón de motores, el firmware corta todas las salidas y vuelve a realizar la espera de activación. STOP normal permite otra pulsación; FAULT requiere revisión y reinicio deliberado. Los cortes dependen del software/ISR/DWT, con IWDG de respaldo; no son mediciones eléctricas certificadas.

Compilar y cargar es un paso separado, con identificación, respaldo, plan y readback completo: consulta [firmware](../firmware/README.md) y [herramientas](../docs/tools-reference.md). No se graba ni se mueve la placa al ejecutar un build o un test.

## Preparar el servidor

Desde la raíz del repositorio, usando un entorno Python propio:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Sin modo explícito, el programa muestra un dry-run y no inicia servidor ni abre serie:

```bash
python -m web.server
```

Para probar sin placa:

```bash
python -m web.server --simulate --bind 127.0.0.1 --port 8766
```

Para hardware real con la imagen correcta ya cargada:

```bash
python -m web.server --execute \
  --serial-port /dev/ttyUSB0 \
  --manifest firmware/manual-hold/build/manifest.json \
  --manifest-sha256 HASH_REVISADO_DEL_MANIFIESTO \
  --bind 0.0.0.0 --port 8765
```

Sustituye `HASH_REVISADO_DEL_MANIFIESTO` por el SHA256 revisado del build local. El puerto debe ser el USB-DEBUG comprobado. El cliente mantiene una única sesión serie y no intenta reconectarla, resetear o repetir MOVE después de un error. Espera 350 ms una sola vez al abrir, porque el CH340 puede reiniciar transitoriamente el MCU; el timeout de respuesta durante funcionamiento sigue siendo 40 ms y el lease del dispositivo sigue en 150 ms.

El servidor imprime un enlace con una clave efímera en el fragmento `#token=...`. Para otro dispositivo de la misma red, usa la dirección local del ordenador servidor en lugar de la de loopback, conservando ese fragmento. El servicio no publica un túnel a Internet. Si usas un nombre DNS local, decláralo con `--allow-host`; no se aceptan Origin/Host arbitrarios.

## Acceso y parada

- Se admite un solo navegador controlador. Otro navegador no roba una pulsación activa.
- La clave queda en `.local/web/<sesión>/token.txt`, privada e ignorada por Git; nunca la copies a documentación, capturas públicas o URLs del remoto.
- El navegador retira la clave de la barra y la conserva solo en memoria/sessionStorage. Recargar o reconectar no reanuda una pulsación vieja: hay que volver a mantener un botón.
- El servidor no mantiene una cola de movimientos. La intención actual, su secuencia y su caducidad se comprueban justo antes de transmitir.
- Cerrar normalmente el servidor intenta STOP y cierra la sesión. Una pérdida del proceso deja de renovar el lease del MCU.
- La API de estado es de lectura; no existen endpoints HTTP GET/POST de movimiento o STOP. El control requiere WebSocket autenticado y Origin coincidente.

El enlace mostrado permite controlar motores: compártelo únicamente con el operador previsto. La interfaz mantiene los controles deshabilitados si falta autenticación, conexión, estado válido o si hay un fallo.

## Pruebas

```bash
python -m unittest discover -s web -p 'test_*.py' -v
make -C firmware/manual-hold test
```

Las pruebas automáticas usan un dispositivo simulado o un transporte falso. Las comprobaciones de navegador se hacen contra `--simulate`, no contra una placa real. Durante la puesta en marcha del perfil 5 se comprobaron también una orden breve real de avance, otra de retroceso y STOP mediante WebSocket, con cuatro encoders de signo coherente y estado final de reposo. La ampliación a giros del perfil 6 tiene validación offline; todavía requiere cargar esa imagen y comprobar físicamente los giros.
