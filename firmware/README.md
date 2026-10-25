# Firmware y compilación

Hay tres entregas con alcances distintos:

- [forward-3s](forward-3s/README.md): aplicación de banco completa para H60 V3.7; cuatro ruedas hacia avance durante 3 s al 10 % PWM. Invierte B/D y requiere un FIRE explícito, nonce nuevo y heartbeats. El BIN reconstruido coincidió byte a byte con el ensayado en la placa.
- [manual-hold](manual-hold/README.md): aplicación para la web local temporal, perfil 6 con avance, retroceso y giros sobre el sitio al 10 %, lease de 150 ms y máximo 10 s por pulsación. STOP permite una nueva pulsación; los fallos quedan bloqueados. Requiere actualizar el perfil 5 anterior y es un protocolo distinto de `forward-3s`.
- [commissioning](commissioning/README.md): módulos y pruebas propios de puesta en marcha, seguridad, control e IMU. No es una aplicación ARM completa: se excluyeron las integraciones del fabricante cuya redistribución no está establecida.

## Preparar dependencias

Obtén del fabricante o vendedor el paquete de código **OpenCTR H60 code.zip** de la revisión indicada en el [lock de dependencias](forward-3s/vendor-lock.json). No basta con un firmware de fábrica ni con el paquete antiguo TB6612. Pide el paquete de ejemplos STM32 de H60 V3.7 si el vendedor ofrece varios recursos.

El paquete que se ha verificado contiene estos dos archivos internos:

- `OpenCTR_H60V37_Basis_Demo_V1.4.0.zip`
- `OpenCTR_H60V36_R750ROS_V3.61.0602.zip`

El segundo nombre incluye `V36` y `ROS`, pero de él solo se importan dependencias STM32 verificadas: no se carga su aplicación completa ni se instala un nodo ROS. Un paquete que solo contenga programas del ordenador o un BIN no aporta esas fuentes. El [lock](manual-hold/vendor-lock.json) detalla los 41 archivos y sus hashes. Se pueden pasar ambos ZIP internos como dos argumentos `--source`, en lugar del ZIP exterior.

Para pedir el recurso al vendedor:

> Please send the complete STM32 source package "OpenCTR H60 code.zip" for the H60 V3.7, including "OpenCTR_H60V37_Basis_Demo_V1.4.0.zip" and "OpenCTR_H60V36_R750ROS_V3.61.0602.zip". I need the source code and libraries, not only compiled firmware or PC-side ROS nodes.

Si entrega una versión distinta, hay que revisar sus fuentes y compatibilidad antes de actualizar el lock. No usar `--verify` ni cambiar hashes como forma de aceptar un paquete desconocido.

El importador reconoce las rutas internas y verifica el contenido; no es necesario interpretar los nombres chinos de las carpetas. No baja archivos de enlaces no verificados ni abre el hardware.

```bash
python3 scripts/import_vendor.py --source '/path/to/OpenCTR H60 code.zip'
```

También acepta el directorio original extraído. Si los hashes no coinciden, detiene la importación; no desactives la comprobación para usar otra revisión. Consulta [procedencia](THIRD_PARTY.md) y las licencias que acompañan a tu paquete. Los 41 archivos importados y sus avisos quedan en `forward-3s/vendor/`, ignorado por Git.

## Compilar y probar

Instala GNU Make, un compilador C nativo (`cc`) y GNU Arm Embedded (`arm-none-eabi-gcc`, binutils y newlib). El código propio y los tests nativos no requieren una placa conectada.

```bash
make test
make -C firmware/forward-3s all
```

El build ARM genera BIN/HEX/ELF/map y un manifiesto con hashes en `firmware/forward-3s/build/`. No carga ni mueve la placa. Puedes seleccionar otra toolchain con `CROSS_COMPILE`; los overrides `NEWLIB_INCLUDE` y `NEWLIB_LIB_DIR` sirven para distribuciones de newlib separadas. Los detalles están en el README de cada entrega.

Para comprobar reproducibilidad, usa la misma toolchain y dos directorios de salida distintos. El importador y los builds dejan todas sus salidas fuera del historial Git.

La carga es una fase separada: [herramientas ROM y Flash](../docs/tools-reference.md). Ni una compilación válida ni las pruebas nativas sustituyen la identificación de la placa y el respaldo privado previo.

## Configuración del firmware publicado

Para conectar un ordenador y usar los cuatro botones, la ruta principal es `manual-hold`, perfil 6: sigue [la guía completa](../docs/getting-started.md). `forward-3s` es un ensayo distinto; `commissioning` no es una aplicación ARM completa para grabar directamente.

Los parámetros del perfil 6 se fijan al compilar, no se configuran desde una página web ni editando `profiles/r5-tested.example.json`:

| Archivo | Responsabilidad |
| --- | --- |
| `manual-hold/include/hold.h` | Perfil, canales, máscara de inversión B/D, PWM y plazos de lease/gesto/wake |
| `manual-hold/src/hold.c` | Estados, protocolo, dirección de cada canal y descriptor CAPS |
| `manual-hold/src/main.c` | USART1, temporizadores, GPIO y comprobaciones de la placa V3.7 |
| `manual-hold/build_manifest.py` | Contrato y hashes del build que se va a cargar |
| `../web/serial_client.py` | Contrato que debe verificar el cliente del ordenador |

El build predeterminado conserva las referencias físicas medidas. Para otro montaje, contrastar primero [canales y polaridades](../docs/hardware.md). Cambiar un parámetro que aparece en CAPS o en el manifiesto exige mantener coherentes firmware, generador del manifiesto y cliente; no modificar solo una comprobación para aceptar una imagen distinta. Después hay que pasar las pruebas, reconstruir, generar y revisar un plan nuevo y validar el nuevo montaje. No presentar una modificación como ensayada por los resultados del firmware original.
