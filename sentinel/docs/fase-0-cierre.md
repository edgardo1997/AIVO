# Fase 0: Cierre

## Objetivo
Preparar el repositorio para la transicion arquitectonica sin perder funcionalidad actual.

## Cambios realizados

### README.md
- Renombrado de \"AIVO\" a \"Sentinel\" (nombre temporal)
- Agregada nota sobre identidad comercial no definitiva
- Simplificado para reflejar el estado de transicion
- Agregada referencia a sentinel/docs/identidad.md

### sentinel/ (nuevo directorio)
- sentinel/core/       - Motores centrales (vacio, para Fase 1+)
- sentinel/adapters/   - Adaptadores a sistemas externos (vacio)
- sentinel/docs/       - Documentacion tecnica
  - identidad.md       - Filosofia, principios, roadmap del proyecto
- sentinel/README.md   - Estado de progreso por fase
- sentinel/__init__.py  - Paquete Python

### No modificado
- sidecar/            - Runtime legacy intacto
- src/                - Frontend React intacto
- src-tauri/          - Tauri shell intacta
- HTML wallpaper      - No tocado
- .gitignore          - No modificado
- package.json        - No modificado
- Cualquier runtime, DB, log, proceso activo

## Estado del repositorio
- sidecar/ (legacy) + sentinel/ (nueva arquitectura) coexistiendo
- Sin dependencias entre ellos
- Cada fase futura trabajara unicamente en sentinel/
- Las fases que requieran cambios en sidecar/ se especificaran en su momento

## Proxima fase
Fase 1: Tool Gateway + Adapter Interface
- Crear interfaz Tool abstracta en sentinel/core/tool.py
- Crear ToolGateway en sentinel/core/tool_gateway.py
- Primer adapter concreto (System Adapter sobre psutil)
