# Sentinel Alpha Scope

## Propósito

Este documento delimita el alcance mínimo de Sentinel para la Alpha interna. Define lo que está incluido, lo que está excluido y las reglas del Feature Freeze.

## Funciones incluidas en la Alpha

- Instalación y desinstalación controladas.
- Onboarding de cuatro decisiones: local, cloud, carpetas, resumen.
- Chat con modelo local y fallback cloud con consentimiento.
- Historial de conversaciones.
- Settings esenciales: idioma, permisos, modo usuario/desarrollador.
- Cloud Authority: desautorizado por defecto, aprobación explícita.
- Clarificación de solicitudes ambiguas.
- Consentimiento gobernado para acciones sobre archivos.
- Ejecución gobernada de filesystem e integraciones.
- Demo PDF: buscar más reciente, crear `Reviewed`, copiar, abrir, auditar.
- Auditoría comprensible con vista simple y técnica.
- Cierre limpio: apagar sidecar, liberar puertos y procesos.
- Diagnóstico mínimo exportable con redacción de secretos.
- Restablecimiento de configuración e interfaz.

## Funciones excluidas (postergadas para Beta)

- Nuevos proveedores de IA.
- Nuevas herramientas de integración.
- Agentes autónomos.
- Memoria a largo plazo.
- Automatizaciones y plugins comunitarios.
- Paneles analíticos avanzados.
- Integraciones externas (Git, correo, calendario, etc.).
- Marketplace.
- Rediseño visual.
- Funciones experimentales.

## Reglas del Feature Freeze

- Solo se aceptan correcciones de: seguridad, bugs, lifecycle, persistencia, build, instalación, rendimiento, mensajes, diagnóstico, soporte, rollback, documentación.
- No se agregan funciones, proveedores, tools, paneles, agentes, memorias ni rediseños.
- Toda propuesta nueva fuera del alcance se registra como `POSTPONER PARA BETA`.

## Release Gates

- `uv sync --frozen`
- `npm ci`
- `pytest -m alpha_constitutional_gate -q`
- `npm test`
- `npm run build`
- `cargo test --locked`
- `cargo clippy`
- `scripts/build-sidecar.ps1`
- `cargo build --locked --release --manifest-path src-tauri/Cargo.toml`
- `scripts/build-alpha.ps1`

## Canales

- `internal-alpha`: build local para Alpha interna, updater deshabilitado, firma opcional.
- `external-alpha`: build firmada, updater habilitado, requiere certificados.
- `stable`: no activo durante Alpha.
