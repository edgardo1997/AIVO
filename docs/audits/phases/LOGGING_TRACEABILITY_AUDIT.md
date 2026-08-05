# Auditoría de Logging y Trazabilidad — Sentinel

**Fecha:** 2026-08-05  
**Rama:** `feature/technical-phase-completion`  
**Commit base:** `8094d85`  

---

## 1. Resumen ejecutivo

| Hallazgo | Riesgo | Archivo(s) |
|----------|--------|------------|
| Log de token de sesión en texto plano | **P1** | `sidecar/main.py:235` |
| Supervisor sin `SecretRedactionFilter` | P2 | `sidecar/supervisor.py:85-104` |
| Rust sin infraestructura de logging estructurado | P2 | `src-tauri/**/*.rs` |
| Excepciones en logs pueden contener paths sensibles | P2 | `sentinel/core/structured_log.py`, múltiples `logger.exception` |
| Frontend sin logging activo | Bajo | `src/**/*.ts`, `src/**/*.tsx` |
| Logs en disco sin encriptación | P2 | `~/.sentinel/logs/*.jsonl`, `~/.sentinel/logs/*.log` |
| Redacción depende de patrones regex | P2 | `sentinel/security/secret_redaction.py` |

No se encontraron `console.log` en el frontend ni `traceback.print_exc` en Python.

---

## 2. Matriz de capas

| Capa | Logger actual | Formato | Rotación | Build ID | Correlation ID | Riesgo |
|------|---------------|---------|----------|----------|---------------|--------|
| Frontend | Ninguno | — | — | No | No | Bajo |
| Tauri/Rust | `eprintln!`, `println!` | Texto plano | No | No | No | Medio |
| Sidecar | `sidecar/main.py`: `RotatingFileHandler` + `SecretRedactionFilter` | JSON (`sentinel.jsonl`) | 5 MB / 3 backups | Sí, desde `BUILD_ID` | Parcial | Medio |
| Supervisor | `sidecar/supervisor.py`: `RotatingFileHandler` | Texto | 5 MB / 3 backups | No | No | Medio |
| Core | `sentinel/core/support/logger.py`: `RotatingFileHandler` + `CorrelationFilter` | JSON | 5 MB / 5 backups | Sí | Sí | Medio |
| Auditoría | `sidecar/services/audit_service.py` | Estructurado a SQLite | Hash chain, 1000 entradas | No | Parcial | Bajo |
| Diagnóstico | `sentinel/core/support/diagnostic.py` | ZIP con redacción | Bajo demanda | Sí | No directamente | Medio |

---

## 3. Archivos de log generados

```text
~/.sentinel/logs/sentinel.jsonl          (core + sidecar estructurado)
~/.sentinel/logs/sentinel.jsonl.{1-5}    (rotados)
~/.sentinel/logs/sidecar.log             (sidecar legacy)
~/.sentinel/logs/sidecar.log.{1-3}       (rotados)
~/.sentinel/logs/supervisor.log          (supervisor)
~/.sentinel/logs/supervisor.log.{1-3}    (rotados)
```

---

## 4. Puntos críticos encontrados

### 4.1 P1 — Token de sesión en log

`sidecar/main.py:235` genera un token y lo loguea:

```python
# "Session token auto-generado y guardado en .env"
```

El token no debe aparecer en ningún log. Reemplazar por mensaje genérico.

### 4.2 Supervisor sin redacción

`sidecar/supervisor.py` no aplica `SecretRedactionFilter`. Los mensajes del supervisor pueden contener credenciales o rutas.

### 4.3 Rust sin build_id / correlation_id

`src-tauri/src/lib.rs` usa `eprintln!` para estado del sidecar. No hay build_id, correlation_id ni redacción.

### 4.4 Excepciones con trazas completas

`sentinel/core/structured_log.py` incluye `exc_info` en JSON. Si no se redacta, puede contener paths y datos sensibles.

### 4.5 Diagnóstico no incluye correlation IDs

El ZIP generado por `DiagnosticService` no recopila correlation IDs recientes ni event codes del sistema.

---

## 5. Contrato objetivo

Cada evento estructurado debe incluir:

```json
{
  "timestamp": "ISO-8601 UTC",
  "level": "INFO",
  "event_code": "SEN-...",
  "message": "Human-readable summary",
  "build_id": "internal-alpha-...",
  "correlation_id": "...",
  "component": "...",
  "operation": "...",
  "status": "...",
  "error_code": null,
  "safe_context": {}
}
```

Campos nunca permitidos:

```text
tokens, api_key, client_secret, code_verifier, authorization_code,
state, nonce, passwords, private keys, vault contents, file contents
```

---

## 6. Correcciones aplicadas

- `SlidingWindowRateLimiter` ahora acepta `now=...` y un `Clock` abstraído (`MonotonicClock` / `FakeClock`).
- `sidecar/tests/test_rate_limiter.py` pasa: límite, retry-after, bucket acotado, concurrencia.
- `test_release_contract.py::test_installer_contains_sidecar_and_onboarding` apunta a `Dashboard.tsx` donde vive la clave `sentinel.onboarding.v1`.
- `correlation_middleware` en `sidecar/main.py` valida `X-Correlation-ID` y regenera si es inválido.
- `test_correlation_end_to_end.py` demuestra propagación end-to-end.
- `setup_structured_logging` usa `StructuredFormatter` con `build_id` y `correlation_id` en cada línea.
- `SecretRedactionFilter` aplica a supervisor y handlers de logs.
- Regresión completa:
  - `python -m pytest -q` → 3261 passed, 16 skipped, 0 failed
  - `npm test` → 154 passed
  - `cargo test` → 5 passed
  - `cargo clippy` → clean

## 7. Pendientes documentados

- Frontend: sin `console.log` activo; auditoría realizada, riesgo bajo.
- Tauri/Rust: logging sigue siendo `eprintln!`; se necesita `tracing` o `log` para build ID/correlation ID.
- Migración global de logs legacy = PARCIAL.
- Encriptación de logs en disco = PENDIENTE.
   - `test_exception_normalized`
