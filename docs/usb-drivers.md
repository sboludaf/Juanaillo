# Conectar el ordenador: USB y drivers

El driver USB crea un puerto serie en el ordenador. No cambia el firmware de la H60 ni garantiza que el microcontrolador responda. En la unidad **H60 V3.7** probada hay dos adaptadores distintos:

| Conector de la H60 | Adaptador / VID:PID observado | Linux habitual | Uso en este proyecto |
| --- | --- | --- | --- |
| USB-DEBUG | CH340, `1a86:7523` | `ch341` → `/dev/ttyUSB…` | Respaldo, carga ROM y aplicación propia por USART1 |
| USB-COM | CH9102, `1a86:55d4` | `cdc_acm` → `/dev/ttyACM…` | USART3; no es el puerto del firmware publicado |

Comprueba las etiquetas físicas y el identificador del dispositivo. El VID:PID identifica el adaptador, no demuestra revisión de placa, tamaño de Flash ni firmware. Otro montaje puede enumerar con otros números de puerto.

## Primero: diagnóstico que no abre serie

Desde la raíz del repositorio:

```bash
python3 scripts/h60_doctor.py
python3 scripts/h60_doctor.py --json
```

El diagnóstico lee la enumeración USB, comprueba dependencias y consulta versiones de herramientas. No abre dispositivos serie, modifica DTR/RTS, reinicia la placa ni transmite bytes UART. Tampoco muestra el número de serie USB, UID del MCU, usuario o nombres de procesos.

En Linux muestra adaptadores conocidos incluso si todavía no tienen puerto TTY, el driver asociado, permisos del usuario actual y PIDs visibles con el dispositivo abierto. Una lista vacía de propietarios **no demuestra que el puerto esté libre**: el sistema puede ocultar procesos ajenos. La presencia de un módulo bajo `kernel_drivers_loaded_or_builtin` tampoco sustituye la comprobación del driver asociado al puerto.

En Windows/macOS utiliza la enumeración de pyserial si está instalado. En macOS oculta el sufijo de nombres de puerto que puede contener el número de serie; para seleccionar el puerto real, consulta `/dev/cu.*` localmente. Si falta pyserial, instala `requirements.txt` en la venv de la [guía de inicio](getting-started.md). El diagnóstico no instala paquetes ni requiere administrador.

## Linux: usar los drivers del sistema

Para el CH340, el módulo es `ch341` y el enlace al puerto puede aparecer como `ch341-uart`; para la función serie estándar del CH9102, WCH documenta compatibilidad con el driver [CDC-ACM incluido en Linux](https://github.com/WCHSoftGroup/ch343ser_linux#description). El control ensayado usa estos drivers del sistema; no requiere compilar un driver WCH externo ni reemplazar `cdc_acm`.

Comprobaciones útiles, sin abrir el puerto:

```bash
lsusb
modinfo ch341
modinfo cdc_acm
ls -l /dev/ttyUSB* /dev/ttyACM*
id
```

Que una orden `ls` no encuentre uno de los patrones es normal si solo se conecta el otro adaptador. Si `modinfo` no está instalado, usa el diagnóstico y la documentación de tu distribución. Si falta realmente un módulo, instala el paquete de módulos que corresponda **a tu kernel y distribución**, no un binario descargado para otro sistema.

Si existe el puerto pero falta permiso de lectura/escritura, revisa el grupo y las ACL de ese nodo. En Ubuntu/Debian suele ser `dialout`; cuando esa sea la política de tu equipo, un administrador puede añadir tu usuario a ese grupo:

```bash
sudo usermod -aG dialout "$USER"
```

Después hay que cerrar y abrir la sesión para aplicar el grupo. Si ya tienes acceso mediante ACL, no hace falta cambiar grupos. No ejecutes toda la aplicación como root ni conviertas todos los puertos en accesibles para cualquiera.

Si el puerto aparece y desaparece, revisa cable de datos, alimentación y registro del kernel. Una intervención de `brltty` o ModemManager debe confirmarse en el registro antes de cambiar servicios; no los desinstales o desactives por rutina. Si otro proceso mantiene abierto el puerto, cierra deliberadamente ese propietario antes de usar otro cliente. La web es un propietario del puerto aunque nadie pulse un botón.

## Windows: descarga oficial para el chip correcto

1. Conecta USB-DEBUG con un cable de datos y abre **Administrador de dispositivos → Puertos (COM y LPT)**. Si falta el driver, revisa también los dispositivos desconocidos y sus identificadores de hardware.
2. Para CH340/CH341 (`VID_1A86&PID_7523` en la unidad probada), usa [CH341SER.EXE de WCH](https://www.wch-ic.com/downloads/CH341SER_EXE.html). WCH publica este instalador para Windows y lo identifica como firmado/certificado por Microsoft.
3. Para CH9102 (`VID_1A86&PID_55D4` en la unidad probada), usa [CH343SER.ZIP de WCH](https://www.wch-ic.com/downloads/CH343SER_ZIP.html). WCH incluye CH9102 en esta familia de drivers VCP y declara certificación WHQL/HCK. **El instalador CH340 no sustituye al de CH9102.**
4. Descarga y extrae el paquete del fabricante; sigue su instalador o la instalación mediante INF que incluya. Comprueba la procedencia y firma digital, sin desactivar las comprobaciones de firma del sistema.
5. Vuelve a comprobar qué `COM…` ha aparecido y utiliza ese puerto explícitamente en los comandos. Si ya aparece un puerto funcional con el driver del sistema, no es necesario reemplazarlo solo para seguir la guía.

Los enlaces conducen a páginas oficiales de descarga, no a espejos de terceros. Las versiones cambian; el archivo que se instala debe corresponder al sistema y arquitectura elegidos. El driver permite enumerar, pero la secuencia física DTR/RTS de recuperación de esta H60 **solo se ha validado en Linux**.

## macOS: comprobar primero el puerto existente

Busca el dispositivo en Información del Sistema → USB y los puertos `/dev/cu.*`. Si el sistema ya crea el puerto y funciona, no instales otro driver por rutina.

Cuando sea necesario, WCH publica el paquete [CH34XSER_MAC.ZIP](https://www.wch.cn/downloads/CH34XSER_MAC_ZIP.html) para ambas familias. Su [guía oficial y paquetes](https://github.com/WCHSoftGroup/ch34xser_macos#installation) explican qué instalador corresponde a la versión y arquitectura de macOS y cómo autorizar su extensión desde los ajustes del sistema. Sigue esa guía sin desactivar protecciones globales del sistema. Este repositorio no declara una prueba física en macOS.

## Drivers USB frente a dependencias del firmware

Los drivers CH340/CH9102 pertenecen al **ordenador**. CMSIS, las bibliotecas STM32 y los archivos del fabricante importados al compilar pertenecen al **firmware de la placa**. Instalar un driver USB no sustituye la [preparación de dependencias y compilación](../firmware/README.md).

Este repositorio publica su diagnóstico y las instrucciones, y enlaza los instaladores originales; no copia instaladores cuya redistribución no se ha establecido. Linux normalmente ya proporciona los módulos necesarios. La carpeta [drivers/](../drivers/README.md) mantiene este índice de fuentes. Si una página WCH requiere JavaScript, ábrela en un navegador normal y busca el nombre exacto del paquete.

Referencias verificadas el 25 de octubre de 2026: [CH341SER](https://www.wch-ic.com/downloads/CH341SER_EXE.html), [CH343SER](https://www.wch-ic.com/downloads/CH343SER_ZIP.html), [CDC-ACM y CH9102 en WCH](https://github.com/WCHSoftGroup/ch343ser_linux), [macOS en WCH](https://github.com/WCHSoftGroup/ch34xser_macos). Para el mapeo de USART y el alcance de la unidad ensayada, consulta [hardware](hardware.md).
