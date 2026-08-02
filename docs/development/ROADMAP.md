# Sentinel — Roadmap de features candidatas

Fecha: 2026-08-02
Estado: documento de planificación (no implementación). Ninguna feature aquí se
implementa durante la estabilización del release; se registran para priorizar
en iteraciones posteriores (candidatas a 1.1.0+).

---

## FEAT-1: Inferencia local gestionada — correr modelos locales sin aplicaciones externas

**Prioridad propuesta:** alta (diferenciador de producto: privacidad local y
funcionamiento sin internet). **No se implementa en 1.0.0.**

### Visión de producto
- Al instalar/ejecutar Sentinel por primera vez, el sistema escanea el hardware
  completo del usuario (RAM total/disponible, CPU, GPU/VRAM, disco) y analiza.
- Según el análisis, **recomienda el tipo de modelo por uso**, con justificación:
  "Este modelo corre bien en tu PC por estas razones — recomendamos usarlo para
  cuando no tengas internet y no dependas de proveedores externos".
- **Sección de descarga** de todos los modelos gratuitos posibles; la
  recomendación al usuario depende de su tipo de RAM/hardware.

### Estado actual del código (lo que ya existe)
- Proveedor `sentinel_local` **declarado pero no cableado**:
  - `sentinel/core/router_types.py:86` — `ProviderSpec(id="sentinel_local", ...,
    default_model="Qwen3-1.7B-Q8_0.gguf", requires_key=False, is_local=True,
    priority=50)`, endpoint `http://127.0.0.1:11435/v1` (`router_types.py:73`).
- Requisitos de hardware por tamaño de modelo:
  - `sentinel/core/resource_intelligence.py:72-78` — `MODEL_HARDWARE_REQUIREMENTS`
    (70b→64GB RAM/48GB VRAM … 1b→2GB RAM/1GB VRAM).
- Escaneo/evaluación de hardware ya implementados:
  - `sentinel/core/resource_intelligence.py` — `SystemSnapshot` (RAM, CPU, GPU,
    batería, presupuesto), `ResourceIntelligence.evaluate()`,
    `evaluate_all()`, `filter_candidates()`, `_get_hardware_requirement()`.
- Modelo base elegido en el catálogo:
  - `sentinel/models/default_registry.py:36` — `Qwen3-1.7B-Q8_0.gguf`
    (provider `sentinel_local`).
  - `sentinel/core/context_window.py:40` — ctx window 4096 para ese modelo.
- UI existente: `src/components/Product/ModelCenterView.tsx`,
  `src/components/Product/ControlCenterView.tsx` (vistas de modelo/control).

### Lo que falta (gap)
1. **Dependencia de inferencia**: agregar `llama-cpp-python` (o embeber
   `llama.cpp`). Hoy el único client de modelos es `openai`
   (`sidecar/requirements.txt:26`).
2. **Descarga y gestión del modelo**: descargar el `.gguf` al primer uso,
   verificar integridad, y gestionar el ciclo de vida.
3. **Ciclo de vida del server**: iniciar/parar el proceso en `127.0.0.1:11435`
   con el app, healthcheck y fallback.
4. **Catálogo de modelos gratuitos descargables** + sección de descarga en UI.
5. **Flujo de recomendación al usuario** (onboarding/Model Center) con la
   justificación "por estas razones".

### Dimensionamiento estimado
- Fase A (2–3 días): `llama-cpp-python` + arranque de `sentinel_local` +
  descarga del Qwen3-1.7B → desbloquea "corre sin internet".
- Fase B (1–2 días): flujo de recomendación + sección de descarga de modelos.

### Hardware de referencia (validado)
- Intel Core Ultra 7 256V, 15.5GB RAM, iGPU Intel Arc 140V (8GB). Qwen3-1.7B
  Q8 corre holgado en CPU (~15–20 tok/s). Modelos 7B+ no recomendados aquí.

### Decisión (2026-08-02)
- **NO implementar en 1.0.0.** Razones: congelación de release, riesgo de
  romper el bundle PyInstaller / ModelRouter / fallbacks verificados, y la
  feature no es gate de 1.0.0 (ya hay providers gratuitos sin key: DeepSeek v4
  Flash free y NVIDIA Nemotron free, con fallback a local).
- **Implementar como Sentinel 1.1.0**, en iteración propia (Fases A y B).

### Referencias
- `docs/cto/09_REFACTOR_AND_DELETION_POLICY.md`
- `docs/cto/10_IMPLEMENTATION_REJECTION_RULES.md`
- `docs/development/CURRENT_STABILIZATION_STATE.md`
