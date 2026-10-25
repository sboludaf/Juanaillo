# Drivers del ordenador para OpenCTR H60 V3.7

Empieza por la [guía USB y drivers](../docs/usb-drivers.md), que explica instalación, identificación del chip, permisos y diagnóstico. No se instala ningún driver al clonar el repositorio o ejecutar sus pruebas.

| Adaptador | Sistema | Fuente original |
| --- | --- | --- |
| CH340/CH341 de USB-DEBUG | Windows | [WCH: CH341SER.EXE](https://www.wch-ic.com/downloads/CH341SER_EXE.html) |
| CH9102 de USB-COM | Windows | [WCH: CH343SER.ZIP](https://www.wch-ic.com/downloads/CH343SER_ZIP.html) |
| CH340 y CH9102 | macOS | [WCH: CH34XSER_MAC.ZIP](https://www.wch.cn/downloads/CH34XSER_MAC_ZIP.html) y [guía oficial](https://github.com/WCHSoftGroup/ch34xser_macos) |
| CH340/CH341 | Linux | Módulo `ch341` del kernel/distribución |
| CH9102 | Linux | Módulo `cdc_acm` del kernel/distribución; [explicación del fabricante](https://github.com/WCHSoftGroup/ch343ser_linux#description) |

El driver no es firmware y no adapta el protocolo de una revisión H60 a otra. El firmware publicado usa USB-DEBUG/USART1, no USB-COM/USART3.

Se publican enlaces oficiales en lugar de copias de instaladores sin términos de redistribución verificados. Así el usuario obtiene la versión original adecuada a su sistema. Los módulos Linux suelen estar ya incluidos; el driver VCP externo del fabricante no es necesario para la ruta serie probada. Consulta [procedencia](../THIRD_PARTY.md).
