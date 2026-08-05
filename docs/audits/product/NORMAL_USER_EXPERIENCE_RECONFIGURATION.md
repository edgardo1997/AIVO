# Normal User Experience Reconfiguration — Sentinel

Fecha: 2026-08-05
Rama: `feature/normal-user-experience`
Commit base: `5eeb0b3` (main)
Estado: **EN PROGRESO**

---

## 1. Estado inicial

Sentinel se inicia directamente en un `Workbench` técnico con un sidebar que expone:

- Producto: Modos, Modelos, Control, Métricas
- Sistema: Panel, Live, Monitor, Consola, Ejecutor, Observabilidad
- Datos: Archivos, Conocimiento, Bóveda, Memoria, Reportes
- Administración: Admin, Agentes, Flota, Plugins, Disparadores, Políticas, Perfil
- Seguridad: Permisos, Auditoría, Alertas, Proactivo
- IA: Sentinel, Retroalimentación
- Ayuda: Ayuda, Soporte

Problemas:

- Exposición de arquitectura interna.
- Menú plano con ~30 opciones.
- Sin ruta visible de `Configuración` (aparece como modal de modelos).
- `Soporte` y diagnóstico (Fase 14) oculto en menú de ayuda.
- Login solo permite sesión local.
- No hay onboarding guiado de 4 pasos.
- No hay separación entre identidad, IA e integraciones.
- Modo desarrollador (`Ctrl/Cmd + Shift + D`) solo filtra vistas, no agrupa opciones avanzadas.
- Admin es una opción visible sin guard de rol.

---

## 2. Inventario y matriz de migración

| Opción actual | Componente | Ruta/Tab actual | Nueva ubicación | Visible por defecto | Justificación |
|---------------|------------|-----------------|-----------------|---------------------|---------------|
| Panel | `Dashboard` | `dashboard` | `Inicio` | Sí | Pantalla principal con estado, IA activa y acciones sugeridas. |
| Sentinel | `Sentinel` | `sentinel` | `Chat` | Sí | Conversación e orquestación. |
| Chat | `Workbench` (chat) | `chat` | `Chat` | Sí | Conversación. |
| Modos | `ModesView` | `modes` | `Configuración → IA y modelos → Modos` (developer) | No | Configuración avanzada. |
| Modelos | `ModelCenterView` | `modelcenter` | `Configuración → IA y modelos` | Sí | Modelos, pero simplificado. |
| Control | `ControlCenterView` | `controlcenter` | `Developer → Gobernanza` | No | Técnico. |
| Métricas | `MetricsView` | `metrics` | `Developer → Observabilidad` | No | Técnico. |
| Panel/Live | `LiveDashboard` | `livedashboard` | `Developer → Observabilidad` | No | Técnico. |
| Monitor | `Monitor` | `monitor` | `Inicio → Estado del sistema` (resumen) / `Developer → Observabilidad` | Resumen | Evitar paneles de RAM en primer nivel. |
| Consola | `Console` | `console` | `Developer → Desarrollo` | No | Técnico. |
| Ejecutor | `Execute` | `execute` | `Developer → Desarrollo` | No | Técnico. |
| Observabilidad | `Observability` | `observability` | `Developer → Observabilidad` | No | Técnico. |
| Archivos | `Files` | `files` | `Archivos` | Sí | Exploración de archivos. |
| Conocimiento | `KnowledgeBase` | `knowledge` | `Archivos → Conocimiento` / `Developer → Inteligencia` | Sí | Base documental. |
| Bóveda | `Vault` | `vault` | `Configuración → Privacidad y permisos → Bóveda` | No | Secretos. |
| Memoria | `Memory` | `memory` | `Configuración → Datos → Memoria` / `Developer → Inteligencia` | No | Contexto histórico. |
| Reportes | `Reports` | `reports` | `Configuración → Datos → Exportar` | No | Exportación. |
| Admin | `Admin` | `admin` | `Admin` (protegido) | No | Rol real requerido. |
| Agentes | `Agents` | `agents` | `Developer → Desarrollo` | No | Técnico. |
| Flota | `Fleet` | `fleet` | `Developer → Sistema` | No | Técnico. |
| Plugins | `Plugins` | `plugins` | `Developer → Desarrollo` | No | Técnico. |
| Disparadores | `Triggers` | `triggers` | `Developer → Desarrollo` | No | Técnico. |
| Políticas | `Policies` | `policies` | `Configuración → Privacidad y permisos → Políticas` / `Developer → Gobernanza` | No | Técnico. |
| Permisos | `Permissions` | `permissions` | `Permisos` | Sí | Control de acceso. |
| Auditoría | `Audit` | `audit` | `Actividad` (resumen) / `Developer → Gobernanza` (detalle) | Sí | Actividad reciente. |
| Alertas | `Alertas` | `alertas` | `Actividad → Alertas` | Sí | Notificaciones. |
| Proactivo | `Proactive` | `proactive` | `Actividad → Sugerencias` / `Developer → Inteligencia` | Sí | Sugerencias. |
| Retroalimentación | `FeedbackCosts` | `feedback` | `Ayuda → Retroalimentación` | No | Costos y calidad. |
| Ayuda | `Help` | `help` | `Ayuda` | Sí | Documentación. |
| Soporte | `Support` | `support` | `Configuración → Soporte y diagnóstico` | Sí | Diagnóstico. |
| Perfil | `Profile` | `profile` | `Configuración → Cuenta` | No | Perfil de usuario. |

---

## 3. Árbol de decisiones de inicio

```text
Aplicación inicia
│
├── ¿Existe sesión válida?
│   ├── No
│   │   └── Pantalla de bienvenida
│   │       ├── Continuar con Google
│   │       ├── Continuar con Microsoft
│   │       ├── Usar Sentinel localmente
│   │       └── Ayuda / Privacidad / Términos
│   │
│   └── Sí
│       └── ¿Sesión expirada?
│           ├── Sí
│           │   └── Renovar o volver a login
│           └── No
│               └── ¿Onboarding completado?
│                   ├── No → Onboarding (4 pasos)
│                   └── Sí → Inicio
```

---

## 4. Navegación objetivo

### Modo usuario

```text
Inicio
Chat
Actividad
Archivos
Permisos
Configuración
Ayuda
```

### Configuración

```text
Cuenta
IA y modelos
Privacidad y permisos
Aplicación
Datos
Avanzado
Soporte y diagnóstico
Acerca de
```

### Modo desarrollador

```text
Configuración → Avanzado → Activar modo desarrollador
```

Navegación expandida:

```text
Desarrollo
├── Consola
├── Plugins
└── Agentes

Observabilidad
├── Métricas
├── Monitor
├── Live
└── Alertas

Inteligencia
├── Modelos avanzados
├── Memoria
├── Conocimiento
└── Proactivo

Gobernanza
├── Permisos avanzados
├── Auditoría
├── Bóveda
└── Control

Sistema
├── Admin
├── Flota
└── Diagnóstico técnico
```

---

## 5. Seguridad y gobernanza

La navegación cambia. La gobernanza no.

### Reglas no negociables

- Las confirmaciones permanecen.
- Los permisos no se otorgan implícitamente.
- El cloud no se autoriza silenciosamente.
- El inicio de sesión no es consentimiento para herramientas.
- No se ejecutan herramientas desde la GUI directamente.
- No se salta ExecutionPipeline, ToolExecutionGuard, ToolGateway.
- No se reutilizan grants.
- No se oculta proveedor, modelo, costo ni actividad.
- No se exponen secretos.
- No se muestra chain of thought.
- No se modifica la autoridad del usuario.
- Modo desarrollador cambia visibilidad, no permisos.
- Admin requiere rol real y guard backend/frontend.

---

## 6. Autenticación

### Cuenta local

Existe a través de `auth.connectLocal()`. Se usa identidad/sesión del sidecar. No requiere contraseña inventada. Permite offline.

### Google / Microsoft

Frontend: **no implementado todavía**. Pendiente construir flujo OAuth/OIDC con PKCE, state, nonce y callback seguro. Se mantendrá separado de Drive/Gmail/Calendar.

### Integraciones

Pendiente: `Configuración → Integraciones` con consentimiento separado.

---

## 7. Progreso

### Completado

- Rama `feature/normal-user-experience` creada desde `main`.
- Inventario y matriz de migración documentados.

### En progreso

- Nuevos layouts y shell de aplicación.
- Navegación simplificada.
- Configuración unificada.
- Soporte visible en modo usuario.
- Modo desarrollador con grupos.

### Pendiente

- Autenticación Google/Microsoft.
- Onboarding guiado de 4 pasos.
- Guards de rutas.
- Tests UX/OAuth.
- Build limpio.
- Validación GUI.

---

## 8. Estado de implementación

| Componente | Estado |
|------------|--------|
| SettingsShell | IMPLEMENTADO |
| Support en Settings | IMPLEMENTADO |
| Sesión canónica | IMPLEMENTADO (backend `/auth/session`) |
| Route guards | IMPLEMENTADOS |
| Developer mode | IMPLEMENTADO (preferencia UI) |
| Admin guard | IMPLEMENTADO (rol backend) |
| Perfil local durable | IMPLEMENTADO (`LocalProfileRepository` SQLite) |
| Onboarding durable | IMPLEMENTADO EN MEMORIA; persistencia real pendiente |
| Home | IMPLEMENTADO |
| OAuth architecture | DISEÑADA |
| Google / Microsoft | CONFIGURATION_REQUIRED |

## 9. Deuda técnica explícita

- `Onboarding backend` usa `LocalProfileRepository` con tabla `user_profiles` y `user_preferences_v2`, lo que es persistente; la clasificación provisional en memoria se refiere a la primera iteración de `session.py`. La implementación actual ya es durable.
- `SENTINEL_SESSION_TOKEN` sigue siendo el bootstrap efímero del sidecar. No es el store durable de sesión; la sesión canónica se consulta a `/auth/session`.
- `Google` y `Microsoft` no funcionan hasta contar con client IDs y redirect URIs reales.

## 10. Commits planificados restantes

```text
feat(identity): persist durable local profile
feat(home): add normal-user home screen
feat(auth): implement OAuth transaction store
feat(auth): add identity provider contracts
test(identity): validate restart and corruption recovery
test(auth): reject OAuth replay and token exposure
```
