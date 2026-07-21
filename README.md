# Sentinel

Sentinel es una plataforma local de coordinación inteligente para Windows. Interpreta una solicitud, construye un plan, evalúa políticas y permisos, ejecuta herramientas autorizadas y conserva una auditoría de lo ocurrido.

Sentinel no es un modelo de IA ni un chatbot independiente. Los modelos y herramientas son recursos que el runtime selecciona y controla.

## Estado del producto

La versión 1.0 está en estabilización. El repositorio contiene componentes experimentales que no forman parte del flujo comercial actual. La interfaz entregada se concentra en el Workbench de Sentinel.

No existe todavía una imagen Docker soportada ni un despliegue servidor multiusuario. El objetivo actual es una aplicación local de escritorio para Windows.

## Flujo de confianza

Toda operación debe seguir este recorrido:

```text
Identidad → Contexto → Intención → Plan → Validación → Políticas
          → Autorización → Ejecución → Calidad → Auditoría
```

Una herramienta no debe ejecutarse fuera del gateway controlado.

## Ejecutar el entorno de desarrollo

Requisitos:

- Windows 10 u 11.
- Node.js 22.
- Python 3.12.
- Rust estable para ejecutar Tauri.

Desde la raíz del repositorio:

```powershell
npm ci
python -m pip install -r sidecar/requirements-dev.txt
npm run tauri:dev
```

El comando debe ejecutarse dentro del directorio del proyecto, no desde `C:\Windows\System32`.

## Validación

```powershell
npm run build
npm test -- --run
python -m ruff check sentinel sidecar
python -m pytest
cargo check --manifest-path src-tauri/Cargo.toml
```

## Datos y privacidad

Sentinel guarda estado local dentro de los directorios de aplicación del usuario y protege sus directorios sensibles con ACL de Windows. Las claves de proveedores no deben colocarse en archivos versionados.

El modelo local es opcional y sólo debe instalarse mediante una acción explícita del usuario. No se descarga automáticamente al iniciar Sentinel.

## Publicación

Los instaladores destinados a usuarios deben construirse exclusivamente desde el workflow de release, firmarse y acompañarse de hashes, SBOM y procedencia verificable. Los artefactos creados manualmente son sólo para desarrollo.

## Documentación

- [Inicio](docs/getting-started.md)
- [Políticas](docs/policies-guide.md)
- [API](docs/api-reference.md)
- [Despliegue](docs/deployment.md)
- [Seguridad](SECURITY.md)
