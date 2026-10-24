# Camino hacia conducción autónoma

El montaje ya tiene correspondencia de canales, cuentas de encoder adoptadas y cuatro sentidos de avance comprobados. La aplicación actual sigue siendo un ensayo de banco fijo; no recibe objetivos de navegación ni regula velocidad.

1. **Control de velocidad por rueda.** Definir una interfaz USB con unidades explícitas, secuencias, límites, armado, STOP y caducidad de órdenes. Mantener el control inmediato en el STM32. Ajustar ganancias y límites con el chasis elevado, sin inventar parámetros para habilitar un build.
2. **Movimiento del chasis y odometría.** Medir diámetro efectivo, distancia entre lados y comportamiento de deslizamiento del R5 de cuatro ruedas. Validar traslación y giro a baja velocidad en una zona despejada. La geometría nominal no sustituye la calibración.
3. **Sensores y estimación.** Validar montaje/ejes de IMU y lectura de tensión; fusionar encoders y sensores según el sistema de navegación elegido.
4. **Autonomía en el ordenador.** Elegir integración ROS 2 u otra aplicación según el ordenador y los sensores disponibles. Una consigna del planificador debe caducar si se pierde la conexión; el ordenador no debe ser el único mecanismo de parada.

El proyecto no presupone mando de juegos, teleoperación web ni una Raspberry Pi concreta. Esos componentes no son requisitos del trabajo con la H60.
