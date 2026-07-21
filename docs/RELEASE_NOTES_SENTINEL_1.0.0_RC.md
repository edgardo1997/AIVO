# Sentinel 1.0.0 — Notas del candidato interno

Sentinel 1.0.0 consolida la plataforma local de coordinación alrededor del flujo
Intención → Plan → Validación → Políticas → Autorización → Ejecución → Auditoría.
La IA continúa siendo consultiva: no concede permisos ni ejecuta herramientas por
fuera de ese flujo.

## Incluido

- Decision Engine seguro y explicable.
- Grounding con evidencia, procedencia, confianza y frescura.
- Presentation Layer coherente para conversación y acciones.
- Memoria persistente aislada, recuperable y borrable.
- Catálogo de aplicaciones e inteligencia de hardware.
- Aprendizaje ambiental privado y consultivo.
- Streaming progresivo con persistencia de conversaciones.
- Enrutamiento local/remoto con trazas y compatibilidad del equipo.
- Auditoría, permisos, recuperación, observabilidad y metadatos de release.
- Mejoras de rendimiento y regresión de la Fase 8.

## Cambios visibles de la Fase 8

- Respuestas progresivas más fluidas en conversaciones largas.
- Menos trabajo repetido al consultar CPU y estado del equipo.
- Reintentos reales cuando falla la sesión local.
- Recuperación visual ante errores de renderizado.
- Menor exposición automática de procesos y conexiones activas.

## Estado de distribución

Este documento describe un **candidato interno**, no una autorización de
publicación general. Antes de distribuirlo a usuarios externos se requiere:

1. checklist final de build y regresión completamente verde;
2. pentest independiente aprobado y hallazgos corregidos;
3. entorno `release-signing` protegido y revisado;
4. verificación E2E del instalador y actualización en Windows limpio;
5. verificación criptográfica completa de los metadatos y artefactos updater.

## Límites conocidos

- El tiempo hasta el primer token depende del proveedor/modelo seleccionado.
- Modelos gratuitos pueden aplicar cuotas, colas y límites externos.
- El timeout total nativo del stream Tauri continúa limitado a 75 segundos hasta
  sustituirlo por presupuestos separados de conexión e inactividad.
- Docker no forma parte de la plataforma soportada para Sentinel 1.0.0.
