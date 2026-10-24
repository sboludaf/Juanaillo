---
name: h60-bringup
description: Identificar revisión, puertos USB, bootloader y preparar una copia de seguridad de OpenCTR H60 antes de modificar firmware o probar motores.
---

# Puesta en marcha de una H60

Lee `docs/hardware.md` y `docs/bring-up.md` desde la raíz del repositorio. Esta skill sirve para conocer el estado de una placa; la carga y los ensayos motrices tienen flujos separados.

- Distingue la revisión física de la placa, la familia del MCU y el firmware instalado. Una captura comercial no demuestra qué imagen está instalada. La validación real de este proyecto fue V3.7 / F407VE / 512 KiB.
- Distingue USB-COM de USB-DEBUG. En la unidad comprobada enumeraron CH9102 y CH340 respectivamente; un cable de carga puede encender la placa sin aportar datos. Enumera dispositivos antes de abrir un puerto; no pruebes órdenes en todos los tty.
- La aplicación de banco usa DEBUG, 230400 8N1. La ROM usa otro encuadre y una entrada DTR/RTS específica. Usa las herramientas del proyecto: no reconstruyas la secuencia a partir del nombre lógico de las señales ni confundas niveles con las aserciones pyserial.
- Empieza por `python tools/h60_recovery.py --help` y sus modos offline. La lectura ROM exige entrar en ROM, lo que puede reiniciar la aplicación aunque no escriba Flash. Informa de ese efecto.
- Lee identidad y tamaño reales. En F4 la firma se leyó en bloque: no sustituyas ese acceso por una lectura corta desalineada que ya dio problemas. No asumas 1 MiB por el nombre STM32F407.
- Conserva identidad, dumps y registros en `.local/`. Un hash y una tabla saneada permiten compartir evidencias sin publicar el UID o toda la Flash. Dos copias del mismo archivo no son dos lecturas independientes.

Si los motores siguen conectados, resuelve la condición física antes de una operación que pueda arrancar firmware desconocido: potencia retirada o ruedas elevadas y corte accesible según el trabajo autorizado. No envíes órdenes de movimiento para comprobar simplemente que el puerto funciona.

Al terminar indica revisión, puerto funcional, protocolo/baud observado, identidad/capacidad comprobadas y qué respaldo existe. Diferencia lo leído de lo declarado por el operador; no habilites navegación por haber identificado el bootloader.
