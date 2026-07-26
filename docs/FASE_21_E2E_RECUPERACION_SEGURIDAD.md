# Fase 21 — E2E, recuperación y seguridad

Fecha de validación local: 2026-07-26

Estado: **VALIDACIÓN LOCAL COMPLETADA; CIERRE EXTERNO BLOQUEADO**

## Alcance validado

- Arranque del binario Windows compilado en un puerto de prueba aislado.
- Health, información de versión, catálogo de capacidades y autenticación.
- Configuración mediante la API vigente.
- Procesamiento de solicitudes seguras y flujo gobernado.
- Creación y descubrimiento de plugins sin cargar código ejecutable de prueba.
- Persistencia después de reiniciar el sidecar.
- Migración transaccional de una base legacy conservando datos.
- Rechazo seguro de una base SQLite corrupta.
- Recreación limpia de la base y versión de esquema mediante `PRAGMA user_version`.
- Controles adversariales, ACL, confirmación, evidencia, pentest gate y memoria
  operacional.

## Correcciones aplicadas

- El sidecar compilado acepta `SENTINEL_HOST` y `SENTINEL_PORT`, manteniendo
  `127.0.0.1:8765` como valores predeterminados.
- Las pruebas E2E reservan puertos libres por proceso y no interfieren con una
  instancia normal de Sentinel.
- La salida del proceso de prueba ya no puede bloquear el arranque por llenar
  un pipe no consumido.
- El teardown cierra el árbol completo del binario PyInstaller; la comprobación
  final encontró cero sidecars de prueba escuchando en puertos altos.
- Los contratos de prueba usan los endpoints y respuestas públicas actuales.
- El esquema SQLite se consolidó en la versión 6:
  - se reconoce la migración 5 ya existente;
  - se repara `config.updated_at` en bases legacy;
  - cada migración sincroniza `PRAGMA user_version`.

## Evidencia de pruebas

- E2E real:
  `13 passed, 1 warning in 284.56s`.
- Regresión de seguridad, recuperación, evidencia y autorización:
  `235 passed, 1 warning in 13.39s`.
- Migraciones de base de datos:
  incluidas en la regresión anterior; ejecución aislada previa:
  `12 passed, 1 warning in 6.45s`.
- Ruff focalizado: aprobado.
- Verificación adicional del teardown: `2 passed`; listeners residuales: `0`.

La advertencia corresponde a una deprecación de Starlette/httpx. Al terminar
Pytest, Windows también reportó un `PermissionError` al limpiar
`pytest-current`; ocurrió después de completar las suites y no fue un fallo de
producto ni de prueba.

## Gates pendientes

1. **VM Windows limpia**: ejecutar instalación, actualización, reinicio,
   recuperación y desinstalación en una VM nueva con evidencia reproducible.
2. **Pérdida de energía real**: la recuperación actual cubre terminación abrupta
   y corrupción; falta una prueba de corte de energía/VM a nivel de sistema.
3. **Pentest independiente**: el gate permanece cerrado hasta recibir una
   atestación Ed25519 de un evaluador registrado, ligada a la versión, commit y
   alcance requeridos.
4. **Cierre de vulnerabilidades**: cualquier hallazgo crítico debe ser cero y
   todo hallazgo alto debe corregirse o bloquear el lanzamiento.

## Decisión

No realizar cutover ni declarar Fase 21 terminada hasta cerrar los gates
externos. La evidencia local permite avanzar a preparar la VM y contratar el
pentest, pero no sustituye esas validaciones.
