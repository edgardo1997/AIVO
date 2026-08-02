# FASE 10 — Business Strategy

**Estado:** Aprobada (canonical)
**Fecha:** 2026-07-31
**Objetivo:** Transformar Sentinel desde un producto tecnológico avanzado en una empresa sostenible con una estrategia comercial clara.

```
Sentinel = Producto + Mercado + Modelo económico
```

---

## 1. Principio fundamental

Sentinel **NO** compite como otro chatbot IA. Ese mercado ya está lleno de
asistentes que conversan mucho y hacen poco.

**Posición oficial:** Sentinel es la capa inteligente entre el usuario y su
computadora.

## 2. Posicionamiento

- **Categoría:** Personal Computer Intelligence Platform
- **Mensaje principal:** *"Sentinel convierte tu computadora en un sistema
  inteligente que entiende tus objetivos, coordina herramientas y ejecuta
  acciones de forma segura."*

### Diferenciadores competitivos

1. **Local-first** — Los datos y la ejecución viven en la máquina del usuario;
   los modelos en la nube son opcionales. Ventajas: privacidad, menor
   dependencia, control del usuario, menor costo operativo.
2. **Model Independent** — Sentinel no vende un modelo, coordina modelos
   (OpenAI, Anthropic, Google, Ollama, LM Studio, futuros) bajo una única capa
   de inteligencia.
3. **Computer Agent** — No es pregunta → respuesta. Es objetivo → comprensión →
   planificación → permisos → acción → aprendizaje.

## 3. Modelo de negocio

### Tier 1 — Sentinel Community (gratis)

Objetivo: adopción masiva.

- Local Models, Basic Chat, System Awareness, Basic Memory, Basic Plugins,
  Local Automation.
- **Sin:** modelos premium, sincronización, funciones empresariales.
- Métricas: downloads, active users, plugin installs, community contributions.

### Tier 2 — Sentinel Pro ($15–$25/mes)

Público: developers, power users, creators, AI enthusiasts.

- Cloud Model Access, Advanced Intelligence, Multi-model reasoning, Premium
  Automation, Advanced Memory, Cross-device Sync, Priority Updates, Premium
  Plugins.
- **Valor:** no se venden tokens; se vende productividad y tiempo ahorrado.
- Comparación correcta: contra el tiempo perdido en tareas repetitivas, no
  contra ChatGPT.

### Tier 3 — Sentinel Enterprise ($99+/usuario/mes o contratos)

Público: empresas, equipos técnicos, instituciones.

- Private Deployment, Local AI Infrastructure, Organization Management,
  Security Policies, Audit Logs, Compliance Reports, Plugin Governance,
  Role Management.
- Modelo: empresa → Sentinel Server → usuarios → políticas corporativas.

### Servicios adicionales — Sentinel Marketplace

- Modelo: 70% creator / 30% Sentinel.
- Ejemplos: Advanced Gaming Optimizer, Developer Toolkit, Security Suite,
  Enterprise Connectors.

## 4. Estrategia de lanzamiento

| Fase | Objetivo | Usuarios | Métrica principal |
| ---- | -------- | -------- | ----------------- |
| A — Developer Preview | Crear comunidad técnica | Developers, AI researchers, power users | Usuarios activos semanales |
| B — Consumer Beta | Validar producto | Gamers, creators, professionals | Retention, daily usage, automation created, time saved |
| C — Commercial Launch | Ingresos | Canal: web, YouTube, communities, Product Hunt, blogs | Conversión Free→Pro |

## 5. Estrategia de crecimiento

- **Community Driven:** Sentinel Community (plugin developers, templates,
  automations sharing, model configurations).
- **Open Core:** abierto (core local runtime, Plugin SDK, basic tools);
  privado (enterprise features, premium intelligence, cloud services,
  marketplace).

## 6. Métricas de empresa

- **Producto:** DAU, MAU, retention, automation usage, plugin adoption.
- **Negocio:** Free→Pro conversion, MRR, CAC, LTV.
- **Tecnología:** average latency, model cost/user, execution success rate,
  security incidents.

## 7. Roadmap empresarial

| Año | Objetivo | Metas |
| --- | -------- | ----- |
| 1 — Validación | Encontrar usuarios ideales | 10.000 usuarios, 500 Pro |
| 2 — Escalamiento | Producto establecido | 100.000 usuarios, 10.000 Pro, primeros Enterprise |
| 3 — Plataforma | Ecosistema Sentinel | Marketplace, partners, enterprise deployments |

## 8. Ventaja estratégica final

Los modelos cambian; los proveedores cambian. La capa de coordinación permanece.
Sentinel construye la capa de inteligencia encima de cualquier modelo.

---

## 9. Criterio de finalización — verificación

| Criterio | Estado | Evidencia |
| -------- | ------ | --------- |
| Definición clara del mercado | ✅ | Sección 1–2 |
| Segmentación de usuarios | ✅ | Secciones 3 (tiers) y 4 (fases) |
| Modelo Free/Pro/Enterprise | ✅ | Sección 3 |
| Estrategia de monetización | ✅ | Sección 3 (Marketplace, Open Core) |
| Métricas empresariales | ✅ | Sección 6 |
| Plan de lanzamiento | ✅ | Sección 4 |
| Estrategia de comunidad | ✅ | Sección 5 |
| Posicionamiento diferencial | ✅ | Sección 2 |

## 10. Evaluación de readiness (basada en capacidades reales del código)

| Dimensión | Objetivo | Real | Nota |
| --------- | -------- | ---- | ---- |
| Product-Market Strategy | 9/10 | 9/10 | Posicionamiento diferencial sólido; tecnología ya implementada (local-first, model-independent, computer agent, plugin SDK). |
| Business Readiness | 8/10 | **6.5/10** | No existe sistema de tiers/entitlement, licencias ni billing. Las métricas de producto existen pero `session` y `first_action` nunca se emiten en producción, impidiendo DAU/MAU/retention reales. |
| Commercial Potential | 9/10 | 8.5/10 | Open Core + Marketplace son rutas creíbles; depende del cierre de telemetría de negocio y del sistema de licencias. |

### Gaps detectados contra el código actual

1. **Telemetría de negocio incompleta.** `sentinel/product/metrics.py` define
   `EVENT_SESSION` y `EVENT_FIRST_ACTION` y las tablas los soportan, pero
   ningún código de producción emite esos eventos
   (`sidecar/modules/product_experience.py` solo registra `mode_used` y
   `action_completed`). Sin ellos no hay DAU/MAU/retention ni TTFA medible.
2. **Sin sistema de tiers/entitlement.** Solo existen tieres de rate-limit
   (`free`/`premium` en `sentinel/core/rate_limiter.py:36`); no hay licencias,
   feature flags por plan ni billing.
3. **Identidad single-user por defecto.** No hay registro de cuentas ni tabla de
   sesiones por usuario que permita convertir a Pro/Enterprise.
4. **Falta telemetría de conversión y MRR.** No existe instrumentación para
   Free→Pro conversion, CAC, LTV ni MRR.

### Acciones recomendadas para cerrar los gaps

1. Emitir `session` y `first_action` desde el sidecar (login/session + primera
   acción por sesión) para habilitar DAU/MAU/retention reales.
2. Añadir un modelo de entitlement (plan: community/pro/enterprise) como
   feature-flag sobre capacidades ya existentes (Plugin Manager, modo premium,
   sync).
3. Instrumentar la conversión Free→Pro y el MRR sobre la identidad del usuario.
