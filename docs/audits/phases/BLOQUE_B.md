# Bloque B — FASE 3: Bloqueos constitucionales

Fecha: 2026-08-05
Repositorio canónico: `C:\Dev\AIVO`
Clon de validación: `C:\Dev\AIVO-repro-validation`
Commit inicial: `c2b81a4`

## 1. Estado final

| Fase | Estado | Justificación |
| ---- | ------ | ------------- |
| FASE 3 | **COMPLETADO** | El fallo TOCTOU `test_replaced_file_same_name_same_size_fails` ha sido corregido y `alpha_constitutional_gate` pasa al 100% |

## 2. Bug corregido

### `test_replaced_file_same_name_same_size_fails`

**Archivo afectado:** `sentinel/security/resource_identity.py`

**Causa raíz:**

- `ResourceIdentity.is_same_identity` no utilizaba `content_hash`.
- `capture_resource_identity` solo computaba SHA-256 cuando `hash_level == "strong"`.
- El modo `fast` dejaba una ventana TOCTOU donde un archivo podía reemplazarse con otro de igual nombre y tamaño sin ser detectado.

**Corrección:**

- `capture_resource_identity` ahora computa SHA-256 para archivos <= 250 MB en ambos niveles (`fast` y `strong`).
- `is_same_identity` consulta `content_hash` primero: si ambas identidades tienen hash y difieren, retorna `False` inmediatamente.
- Si el hash coincide, se mantiene la verificación de metadatos (`size`, `mtime_ns`, `ctime_ns`, `file_id`, `volume_id`) para detectar cambios de `touch` u otros reemplazos que conservan contenido.

## 3. Pruebas

### TOCTOU unitario

```text
pytest tests/test_toctou.py -v
14 passed, 5 warnings in 4.39s
```

### Constitutional gate

```text
python -m pytest -m alpha_constitutional_gate -q
217 passed, 2994 deselected, 29 warnings in 23.47s
```

El gate constitucional está verde.

## 4. Commit

- `c2b81a4` — `fix(security): close TOCTOU window in ResourceIdentity`

## 5. Fallo preservado para Bloque C

`test_corrupt_lock_file_removed_not_killed` no pertenece a FASE 3; se conserva para FASE 10 / lifecycle.

## 6. Working tree final

```text
limpio
```

## 7. Siguiente bloque

**Bloque C — Fases 10 y 11: lifecycle y persistencia**. Se inicia con `test_corrupt_lock_file_removed_not_killed`.
