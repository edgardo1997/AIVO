# Bloque C — Fases 10 y 11: Lifecycle y persistencia

Fecha: 2026-08-05
Repositorio canónico: `C:\Dev\AIVO`
Commit inicial: `b6e138b`
Commit final: `488f44d`

## 1. Estado final

| Fase | Estado | Justificación |
| ---- | ------ | ------------- |
| FASE 10 | **COMPLETADO** | `verified_orphan_cleanup` ya no mata `sidecar.exe` de otras instalaciones; `alpha_constitutional_gate` verde |
| FASE 11 | **COMPLETADO** | `test_fase11_closure.py` 17/17 pasa |

## 2. Bug corregido

### `test_corrupt_lock_file_removed_not_killed`

**Archivo afectado:** `sidecar/modules/sidecar_supervision.py`

**Causa raíz:**

- El "safety net" de `verified_orphan_cleanup` consideraba un proceso huérfano válido cualquier `sidecar.exe` cuyo `name` coincidiera con el esperado.
- Durante las pruebas podía existir otro `sidecar.exe` (p. ej. del build anterior) con padre muerto y el test terminaba matándolo.

**Corrección:**

- El match por ruta ahora requiere la ruta completa exacta (`real == expected`).
- Se eliminó la comparación por `name`, que permitía falsos positivos entre instalaciones o clones.

## 3. Pruebas

### Sidecar supervision

```text
pytest tests/test_sidecar_supervision.py -v
5 passed, 3 warnings in 6.86s
```

### Fase 11 persistencia

```text
pytest tests/test_fase11_closure.py -v
17 passed, 5 warnings in 16.69s
```

### Constitutional gate

```text
python -m pytest -m alpha_constitutional_gate -q
217 passed, 2994 deselected, 29 warnings in 21.89s
```

## 4. Commits

- `488f44d` — `fix(lifecycle): prevent verified_orphan_cleanup from killing foreign sidecar.exe`

## 5. Working tree final

```text
limpio
```

## 6. Siguiente bloque

**Bloque D — Fase 4: suite de pruebas**. Revisar cobertura, marcas `legacy` y gates de integración.
