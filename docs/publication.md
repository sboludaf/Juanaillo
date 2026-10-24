# Preparar una publicación pública

Trabaja en un árbol limpio. Los ZIP, importaciones del fabricante, entornos Python, builds, backups y ejecuciones reales se quedan fuera de Git. Guarda resultados nuevos en `.local/`.

Antes del commit público:

```bash
python scripts/check_public_tree.py
# Revisar el contenido que se va a incluir:
git diff --cached --stat
git diff --cached
```

El comprobador es una ayuda, no una garantía de ausencia de secretos. Revisa credenciales, tokens, claves privadas, URLs autenticadas, UID del micro, puertos con serial personal, rutas del equipo, direcciones de red y capturas con datos personales. Los hashes de fuentes y las características públicas del chip no son credenciales. No publiques dumps ni registros completos para demostrar un resultado: exporta solo la tabla numérica y el método.

Si un secreto ya entró en el historial, borrarlo del último archivo no lo elimina de Git. Revócalo y limpia el historial antes de publicar. No hagas ese cambio sobre un remoto compartido sin tener en cuenta a sus colaboradores.

La autenticación de GitHub se realiza mediante un conector autorizado o un flujo oficial en el navegador/CLI. No pegues contraseñas ni tokens en el chat, en el código, en una URL de remoto ni en `AGENTS.md`. Configura tu autor público o correo noreply antes de tus propios commits.

La creación local de este repositorio no publica nada por sí misma. Antes de crear el remoto decide cuenta, nombre y visibilidad; después sube únicamente el historial revisado.
