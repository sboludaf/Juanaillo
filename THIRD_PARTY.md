# Procedencia y dependencias externas

La licencia MIT de este repositorio cubre sus herramientas, firmware de aplicación y documentación propios. No cambia los derechos de las dependencias.

## Material que no se redistribuye

- Paquetes ZIP de OpenCTR/XTARK, firmware de fábrica, ejemplos y drivers del fabricante: el material inspeccionado no incluía una licencia global que autorizara redistribuir todo el paquete. Algunos archivos conservan avisos de derechos reservados.
- CMSIS/ARM, STM32 Standard Peripheral Library y startup del fabricante: conservan avisos y términos propios. Se obtienen del paquete original y se importan localmente con checksums; no se incluyen en Git.
- Backups completos de Flash y registros de la unidad: pueden contener firmware de terceros e identificadores únicos. Se conservan únicamente en almacenamiento privado.
- El repositorio de referencia [YongZheXiong/project0](https://github.com/YongZheXiong/project0) ayudó a localizar la secuencia de entrada USB. Su archivo LICENSE era un placeholder sin licencia definitiva en la revisión consultada. Se cita como referencia, sin copiar su código ni atribuirle una licencia MIT.

Las secuencias, interfaces y observaciones técnicas se documentan como hechos de interoperabilidad. Las herramientas portables de este repositorio implementan el protocolo de STM32 a partir de su especificación y las verificaciones propias.

## Referencias primarias

- [ST AN3155: protocolo USART del bootloader](https://www.st.com/resource/en/application_note/an3155-how-to-use-usart-protocol-in-bootloader-on-stm32-mcus-stmicroelectronics.pdf).
- [ST AN2606: modos y periféricos del bootloader](https://www.st.com/resource/en/application_note/an2606-stm32-microcontroller-system-memory-boot-mode-stmicroelectronics.pdf).
- [ST RM0090: referencia STM32F407 y familias relacionadas](https://www.st.com/resource/en/reference_manual/dm00031020-stm32f405415-stm32f407417-stm32f427437-and-stm32f429439-advanced-armbased-32bit-mcus-stmicroelectronics.pdf).
- [XTARK](https://www.xtark.cn/): fabricante; consultar revisión y recursos oficiales de la placa adquirida.

## Dependencias de ejecución

Python y la toolchain GNU Arm se instalan por separado. `pyserial` se instala como dependencia, no se copia dentro de este repositorio. Consulta sus términos en sus respectivas distribuciones.

## Drivers USB del ordenador

`drivers/README.md` y `docs/usb-drivers.md` indican los drivers de los adaptadores CH340 y CH9102 y enlazan a las páginas oficiales de WCH. No se copian instaladores propietarios sin una autorización de redistribución identificada. Linux utiliza los módulos de su propio kernel; Windows y macOS tienen instrucciones y descargas oficiales. Instalar el driver del ordenador es distinto de cargar el firmware del STM32.

El diagnóstico USB y el ejemplo de consulta son código propio del proyecto. No incluyen código de los drivers de WCH ni requieren ejecutar instaladores descargados para funcionar en modo offline.
