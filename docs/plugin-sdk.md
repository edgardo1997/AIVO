# Sentinel Plugin SDK — Guía para creadores

La FASE 9 introduce un ecosistema de plugins seguro y controlado. Este documento
explica cómo funciona el SDK y cómo crear, instalar, activar y verificar plugins
sin tocar el núcleo de Sentinel.

## Arquitectura

```
sentinel/plugin_sdk/        SDK (lo que importa el plugin)
sentinel/core/plugin_manager.py   PluginManager (autoridad)
sentinel/plugins/official/  Plugins de confianza oficiales
~/.aivo/plugins/            Plugins de usuario (SENTINEL_PLUGIN_DIR)
```

El **PluginManager** descubre, valida, carga y ejecuta plugins. El núcleo de
Sentinel nunca se modifica: los plugins solo actúan dentro de los permisos que
les concede el usuario.

## Principios

1. **Permisos estrictos.** Todo permiso solicitado en `manifest.json` debe ser
   aprobado por el usuario. Los de riesgo `medium`, `high` o `critical` exigen un
   token de aprobación (TTL 6 horas). Nunca se conceden implícitamente.
2. **Sandbox por diseño.** El validador rechaza imports directos del núcleo
   (`orchestrator`, `execution_pipeline`, `decision_engine`, `memory`,
   `tool_gateway`, `planner`, `model_router`, `intent`, `policy_engine`).
3. **Lifecycle explícito.** Cada plugin pasa por estados verificables.
4. **Confianza y certificación.** Los plugins oficiales y de confianza se
   distinguen por su `trust_score`.

## Estados del ciclo de vida

`installed → validated → permission_review → active → executing → deactivated`
(+ `error`).

## Estructura de un plugin

```
mi_plugin/
├── manifest.json
├── plugin.py
├── tests/test_plugin.py
└── README.md
```

### manifest.json

| Campo          | Requerido | Descripción                                  |
| -------------- | --------- | -------------------------------------------- |
| `id`           | sí        | Identificador único (snake_case)             |
| `name`         | sí        | Nombre visible                               |
| `version`      | sí        | SemVer                                        |
| `author`       | sí        | Autor                                         |
| `description`  | sí        | Qué hace el plugin                            |
| `entrypoint`   | no        | Archivo principal (por defecto `plugin.py`)  |
| `capabilities` | no        | Capacidades (commands, events, tools, media) |
| `permissions`  | no        | Permisos que solicita (lista del catálogo)   |
| `events`       | no        | Eventos a los que se suscribe                |
| `license`      | no        | Licencia                                      |

### plugin.py (SDK)

```python
from sentinel.plugin_sdk import SentinelPlugin


class MiPlugin(SentinelPlugin):
    def on_ready(self):
        return {"status": "ready"}

    def on_command(self, command, **kwargs):
        if "saludo" in str(command).lower():
            self.require("system.read")  # verifica que el permiso fue aprobado
            return {"handled": True, "message": "hola desde el plugin"}
        return {"handled": False}

    def on_event(self, event):
        if event.type == "task.completed":
            self.emit("automation.triggered", {"task": event.payload.get("task")})
            return {"handled": True}
        return {"handled": False}
```

## Catálogo de permisos

Los permisos se agrupan en `system`, `files`, `app`, `network` y `ai`, con nivel
de riesgo `low` / `medium` / `high` / `critical`.

| Permiso              | Riesgo   | Descripción                          |
| -------------------- | -------- | ------------------------------------ |
| `system.read`        | low      | Lectura de estado del sistema        |
| `filesystem.read`    | low      | Leer archivos                        |
| `application.control`| medium   | Controlar aplicaciones              |
| `application.launch` | medium   | Lanzar aplicaciones                 |
| `network.request`    | medium   | Peticiones de red                   |
| `filesystem.write`   | high     | Escribir archivos                   |
| `process.manage`     | critical | Gestionar procesos                  |
| `network.control`    | critical | Configurar red                      |

Consulta `PERMISSION_CATALOG` en `sentinel/plugin_sdk/permission.py` para la
lista completa.

## CLI

```bash
sentinel plugin create mi_plugin        # scaffolding completo
sentinel plugin list                    # lista plugins instalados
sentinel plugin install ./mi_plugin     # instala un plugin
sentinel plugin inspect mi_plugin       # manifiesto + validación + registro
sentinel plugin verify mi_plugin        # integridad y confianza
sentinel plugin remove mi_plugin        # desinstala
```

## API HTTP (sidecar)

| Método | Ruta                                    | Descripción                         |
| ------ | --------------------------------------- | ----------------------------------- |
| GET    | `/api/sentinel/plugins`                 | Lista plugins                       |
| GET    | `/api/sentinel/plugins/metrics`         | Métricas agregadas                  |
| GET    | `/api/sentinel/plugins/{id}`            | Inspección                          |
| POST   | `/api/sentinel/plugins/{id}/approve`    | Aprueba permisos (token)            |
| POST   | `/api/sentinel/plugins/{id}/activate`   | Activa (bloqueado sin token)        |
| POST   | `/api/sentinel/plugins/{id}/deactivate` | Desactiva                          |
| POST   | `/api/sentinel/plugins/{id}/dispatch`   | Envía un comando al plugin          |
| POST   | `/api/sentinel/plugins/{id}/remove`     | Elimina                            |
| POST   | `/api/sentinel/plugins/emit`            | Emite un evento de producto         |

## Plugins oficiales

| Plugin       | Capacidades                    | Permisos                          |
| ------------ | ------------------------------ | --------------------------------- |
| `spotify`    | media, commands                | `application.control`             |
| `vscode`     | tools, commands                | `application.launch`, `filesystem.read` |
| `games`      | events, games                  | `system.read`                     |
| `automation` | automation, events             | `filesystem.read`                 |
| `security`   | security, tools                | `system.read`, `network.request`  |

## Tests

```bash
cd sidecar && python -m pytest tests/test_plugin_sdk.py tests/test_plugin_manager.py
```
