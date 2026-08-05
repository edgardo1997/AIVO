# Sentinel Testing Contract

This document defines how to run, classify, and trust the Sentinel test suite.

## Environment

- Python 3.12.10
- Node 20+ (24.18.0 validated)
- Rust 1.96.1
- Windows 11 x64 (primary target for Alpha)

## Commands oficiales

```powershell
# Python — suite completa (puede tardar varios minutos)
python -m uv run python -m pytest

# Subconjuntos por marker
python -m uv run python -m pytest -m unit -q
python -m uv run python -m pytest -m contract -q
python -m uv run python -m pytest -m integration -q
python -m uv run python -m pytest -m security -q
python -m uv run python -m pytest -m adversarial -q
python -m uv run python -m pytest -m e2e -q
python -m uv run python -m pytest -m alpha_constitutional_gate -q

# JavaScript
npm ci
npm test
npm run build

# Rust
cargo test --locked --manifest-path src-tauri/Cargo.toml
cargo clippy --locked --manifest-path src-tauri/Cargo.toml -- -D warnings
cargo fmt --manifest-path src-tauri/Cargo.toml -- --check

# Sidecar build
python -m uv run pyinstaller sidecar.spec --noconfirm
```

## Markers

| Marker | Significado |
| ------ | ----------- |
| `unit` | Componente aislado, sin red, sin procesos, sin filesystem real salvo `tmp_path` |
| `contract` | Validación de schemas y compatibilidad entre capas |
| `integration` | Varios componentes reales en el mismo proceso o servicio |
| `security` | Autenticación, grants, policy, paths, fail-closed |
| `adversarial` | Inputs maliciosos o estados inesperados |
| `e2e` | Flujos completos de usuario u orquestación |
| `e2e_real` | Contra `sidecar.exe` compilado |
| `performance` | Benchmarks; excluidos por defecto (`-m "not performance"`) |
| `stability` | Repeticiones, races, leaks |
| `smoke` | Artefacto compilado arranca y responde |
| `alpha_constitutional_gate` | Gates constitucionales de Alpha |
| `legacy` | Tests sin clasificación; el `conftest.py` los asigna automáticamente |

## Aislamiento de datos

`sidecar/tests/conftest.py` redirige antes de importar `main`:

- `SENTINEL_DB_PATH`
- `SENTINEL_DATA_DIR`
- `SENTINEL_CACHE_DIR`
- `SENTINEL_CONFIG_DIR`
- `SENTINEL_MODEL_DIR`
- `SENTINEL_PRODUCT_DIR`
- `LOCALAPPDATA`
- `APPDATA`
- `HOME`
- `USERPROFILE`
- `TEMP`
- `TMP`

Ningún test debe escribir en `C:\Users\<user>\.sentinel` o `%LOCALAPPDATA%\Sentinel`.

## Verificar clasificación

```powershell
$env:SENTINEL_FAIL_UNMARKED = "1"
python -m uv run python -m pytest --collect-only -q
```

## Benchmarks

Los benchmarks y scripts de latencia deben residir en `benchmarks/` y no comenzar con `test_` para no ser descubiertos por pytest.

## CI

El workflow principal está en `.github/workflows/ci.yml`. Debe ejecutar:

1. lint
2. unit
3. contract
4. alpha_constitutional_gate
5. integration
6. security
7. cargo test + clippy + fmt
8. npm test + build
9. PyInstaller
10. smoke del sidecar (pendiente)
