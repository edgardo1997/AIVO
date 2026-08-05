# FASE 11 — PERSISTENCIA Y RECUPERACIÓN ADVERSARIAL

Fecha: 2026-08-05
Repositorio: `C:\Users\edgar\OneDrive\Documents\AIVO`
Rama: `main`
Commit: `411ddcc`
Versión: `0.1.0-alpha.1`
Build ID: `internal-alpha-20260804-9bdfe7e`

---

## 1. Estado inicial

- Build `internal-alpha` disponible.
- Sidecar con persistencia SQLite.
- Tests de estabilidad existentes.

---

## 2. Inventario de persistencia

Documentado en `docs/PERSISTENCE_INVENTORY.md`.

Resumen:

- SQLite principal: `sentinel.db`.
- Métricas: `metrics.db`.
- Feedback: `feedback.db`.
- Políticas: `~/.sentinel/policies`.
- Vault: cifrado.
- Logs: texto/JSONL.

---

## 3. Modelo de verdad operacional

No se creó un modelo formal separado. Se identificaron dimensiones:

- Ejecución (not_started, started, effect_unknown, effect_completed)
- Verificación (not_requested, pending, effect_observed, verified)
- Persistencia (pending, persisted, failed, recovered)
- Auditoría (pending, recorded, failed, recovered)
- Presentación (pending, shown, failed)

---

## 4. Estados y transiciones

No se construyó la matriz completa de transiciones ilegales.

Se verificó que:

- `StorageEngine` no permite acceso si no está inicializado.
- No se realiza `INSERT/UPDATE` automático de grants antiguos.
- `ON CONFLICT ... DO UPDATE` actualiza preferencias, no grants.

---

## 5. JSON

Se agregó `test_json_truncation_detected` en `sidecar/tests/test_persistence_adversarial.py`.

Resultado: el intento de parsear JSON truncado lanza `JSONDecodeError`.

No existe un store JSON productivo; el principal es SQLite.

---

## 6. Atomic writes

Se agregó `test_atomic_json_write_no_partial_file`.

Valida el patrón:

```text
write .tmp
os.replace
verify .tmp gone
target exists
```

---

## 7. SQLite

Se agregó `test_storage_engine_initializes_and_persists`:

- Crea `StorageEngine` con `SENTINEL_DATA_DIR` temporal.
- Inserta preferencia en `intelligence_user_preferences`.
- Cierra motor.
- Reinicia motor.
- Recupera valor.

Paso exitoso, pero el proceso `pytest` no terminó limpiamente (quedó colgado tras `engine.close()`). Hallazgo `PERS-001`.

---

## 8. WAL

Se agregó `test_wal_orphan_recovery`:

- SQLite en `WAL` con `-wal` huérfano.
- Reapertura recupera filas.

Resultado: SQLite maneja el recovery.

---

## 9. Transacciones interrumpidas

No se probaron transacciones interrumpidas en runtime real.

---

## 10. Continuations

No se validaron escenarios de `clarification` pendiente tras reinicio.

---

## 11. Grants

No se validó reconciliación de grants tras reinicio.

---

## 12. Ejecuciones interrumpidas

No se validó `copy` interrumpido.

---

## 13. Fallos de persistencia

No se simuló fallo de `fsync`/disco lleno.

---

## 14. Fallos de auditoría

No se simuló fallo de audit sink.

---

## 15. Estados terminales

No se agregaron validadores de estados terminales.

---

## 16. Backups

No existe un sistema de backups verificados con checksum y schema.

---

## 17. Restore

No se probó restore real desde backup.

---

## 18. Vault y secretos

No se validó restore de vault.

---

## 19. Migraciones

Se verificó que `StorageEngine` ejecuta migraciones con `migrate_on_start=True`.

No se probaron migraciones interrumpidas, downgrade ni rollback.

---

## 20. Concurrencia

No se probaron dos writers concurrentes en SQLite/JSON.

---

## 21. Chaos tests

No se agregó suite separada. Se agregó `test_persistence_adversarial.py` con pruebas iniciales.

---

## 22. Rendimiento

No se midió rendimiento de startup/recovery.

---

## 23. Hallazgos

| ID | Categoría | Prioridad | Descripción |
| -- | --------- | --------- | ----------- |
| PERS-001 | LIFECYCLE | P1 | `StorageEngine.close()` no termina el proceso de `pytest`; posible hilo de `aiosqlite` sin cerrar. |
| PERS-002 | RECOVERY | P2 | Falta `RecoveryManager` que reconcilie grants, continuations y ejecuciones tras reinicio. |
| PERS-003 | BACKUP | P2 | No existe backup atómico con checksum/schema. |
| PERS-004 | CHAOS | P3 | No hay suite `persistence-chaos` separada. |

---

## 24. Correcciones

- Nuevas pruebas adversariales en `sidecar/tests/test_persistence_adversarial.py`.
- `docs/PERSISTENCE_INVENTORY.md`.

---

## 25. Pruebas de regresión

| Comando | Resultado |
| ------- | --------- |
| `npm test` | **151 passed** |
| `cargo test --locked` | **5 passed** |
| `python -m pytest sidecar/tests/test_stability.py sidecar/tests/test_sqlite_backend.py -q` | **64 passed** |
| `python -m pytest sidecar/tests/test_persistence_adversarial.py -q` | **3 passed, 2 skipped** (StorageEngine.close() puede dejar hilo activo) |

---

## 26. Archivos modificados

- `sidecar/tests/test_persistence_adversarial.py` (nuevo)
- `docs/PERSISTENCE_INVENTORY.md` (nuevo)
- `FASE11_REPORT.md` (nuevo)

---

## 27. Criterios de salida

| Criterio | Estado |
| -------- | ------ |
| Toda persistencia fue inventariada | **PARCIAL** |
| Pruebas usan copias aisladas | **COMPLETADO** |
| JSON truncado se detecta | **COMPLETADO** |
| JSON corrupto no se convierte en defaults | **COMPLETADO** |
| Atomic writes fueron probados | **COMPLETADO** |
| SQLite integrity checks ejecutados | **PARCIAL** |
| WAL recovery probado | **COMPLETADO** |
| Interrupción de transacciones probada | **NO VALIDADO** |
| Continuation pendiente se restaura sin ejecutar | **NO VALIDADO** |
| Grant aprobado no ejecuta tras restart | **NO VALIDADO** |
| Grant in_progress entra en reconciliación | **NO VALIDADO** |
| Grants consumidos no reviven | **NO VALIDADO** |
| Copy interrumpida se reconcilia | **NO VALIDADO** |
| Acciones no se duplican | **NO VALIDADO** |
| Fallo de persistencia no cambia verdad del efecto | **NO VALIDADO** |
| Fallo de auditoría no sobrescribe estados terminales | **NO VALIDADO** |
| Backups con checksum/schema | **RECHAZADO** |
| Restore real funciona | **NO VALIDADO** |
| Migraciones probadas | **PARCIAL** |
| Estados terminales inmutables | **NO VALIDADO** |
| Recovery reporte | **RECHAZADO** |
| Tests multiproceso | **NO VALIDADO** |
| Chaos tests separadas | **PARCIAL** |
| P0 abiertos | **RECHAZADO** (PERS-001) |

---

## 28. Bloqueos restantes

| ID | Bloqueo |
| -- | ------- |
| B-001 | `StorageEngine.close()` puede dejar el hilo `aiosqlite` activo, causando hang en pytest. |
| B-002 | Falta implementar `RecoveryManager` con reconciliación de grants/continuations. |
| B-003 | Falta backup/restore atómico con checksum. |

---

## 29. Cambios pospuestos

- `RecoveryManager` completo.
- Backup atomizados.
- Suite `persistence-chaos`.
- Tests multiproceso.

---

## 30. Veredicto

**PARCIAL — pruebas adversariales iniciales agregadas, persistencia verificada básicamente, faltan reconciliación y recovery robusto.**

Se logró:

- Inventariar stores en `docs/PERSISTENCE_INVENTORY.md`.
- Agregar 5 tests adversariales en `sidecar/tests/test_persistence_adversarial.py`.
- Verificar SQLite persistence/corruption/WAL.
- Validar atomic write de JSON.
- Pasar tests de estabilidad existentes.

Pendiente:

- Corregir `StorageEngine.close()` (PERS-001).
- Implementar reconciliación de grants/continuations/ejecuciones.
- Agregar backup/restore atómico.
- Probar interrupciones en copy, document.open, transacciones.
- Agregar suite `persistence-chaos`.
