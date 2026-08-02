# Cadena de firma oficial de Sentinel 1.0

La clave pública configurada en `tauri.conf.json` corresponde al par generado
localmente para el lanzamiento oficial de Sentinel 1.0. La clave privada queda
fuera del repositorio y solo se proporciona a la compilación mediante
`TAURI_SIGNING_PRIVATE_KEY_PATH` y `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`.

Las builds previas de desarrollo no pertenecen a esta cadena pública de
actualización. Deben desinstalarse o reinstalarse manualmente; no se deben
publicar como actualizaciones firmadas de Sentinel 1.0 ni alterar sus firmas o
metadatos históricos.
