# Primeros pasos con Sentinel 1.0

## Instalación en Windows

1. Descarga el instalador firmado desde [Releases](https://github.com/edgardo1997/AIVO/releases).
2. Verifica el SHA-256 publicado y ejecuta el instalador.
3. Abre Sentinel desde el menú Inicio. El sidecar se inicia localmente y la aplicación genera una sesión aleatoria.
4. Completa el onboarding y conserva el nivel de permisos **Confirmar** durante la configuración inicial.

El instalador contiene el backend: el usuario final no necesita Python, Node.js ni Rust.

## Primer proveedor

- Para máxima privacidad, instala Ollama y descarga un modelo compatible.
- Para un proveedor remoto, abre **Settings**, selecciona el proveedor y guarda su API key.
- Sentinel solo enrutará a proveedores que estén realmente disponibles.

Las claves del vault se cifran con una llave independiente. Para una instalación administrada puedes definir `SENTINEL_VAULT_KEY` o `SENTINEL_VAULT_KEY_FILE` antes del primer inicio.

## Primera operación

1. Abre **Integraciones** o **Sentinel** y solicita una acción de lectura.
2. Revisa estrategia, permisos y simulación.
3. Confirma únicamente si la herramienta, ruta y efecto coinciden con tu intención.
4. Consulta **Audit** y **Observability** para comprobar la ejecución.

## Actualizaciones

En **Settings → About Sentinel**, pulsa **Buscar actualizaciones**. Sentinel verifica la firma Tauri antes de instalar. Nunca instales un `update.json` con firma vacía ni artefactos de terceros.

## Desarrollo desde código fuente

Ejecuta `setup.bat`, inicia el sidecar en `127.0.0.1:8765` y luego usa `npm run tauri:dev`. Este flujo es solo para desarrollo; producción debe usar el instalador firmado.
