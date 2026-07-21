# FASE 2: GROUNDING ENGINE - ARCHITECTURE IMPACT

**Fecha**: 2025-01-17
**Fase**: 2 - Grounding Engine
**Prioridad**: CRÍTICA
**Duración Estimada**: 3 semanas
**Estado**: Pendiente de aprobación

---

## 1. PROPÓSITO

Implementar una capa de Grounding obligatorio para reducir alucinaciones del modelo usando información real del sistema.

**Objetivo**: Cuando exista una fuente verificable para una pregunta, LA HERRAMIENTA TIENE PRIORIDAD SOBRE EL MODELO.

---

## 2. ARCHITECTURE IMPACT

### 2.1 Nuevo Componente: Grounding Engine

**Archivo**: `sentinel/core/grounding.py` (NUEVO)
**Responsabilidad**: 
- Detectar cuándo una pregunta necesita información real
- Forzar uso de herramientas antes de responder
- Validar frescura de los datos
- Evitar respuestas generadas por memoria del modelo cuando existe una fuente disponible

**Dependencias**:
- ContextEngine (fuente de datos del sistema)
- ToolGateway (ejecución de herramientas)
- CapabilityRegistry (conocimiento de herramientas disponibles)

**Interfaces Públicas**:
```python
class GroundingRequirement:
    category: str  # system_state, file_info, process_info, etc.
    required: bool
    freshness_seconds: float
    source_preference: List[str]  # ['tool', 'cache', 'model']

class GroundingEngine:
    def analyze_requirement(self, intent: Intent) -> List[GroundingRequirement]
    async def enforce_grounding(self, requirement: GroundingRequirement, context: Dict[str, Any]) -> Dict[str, Any]
    def validate_freshness(self, data: Dict[str, Any], requirement: GroundingRequirement) -> bool
```

### 2.2 Modificación: Intent Engine

**Archivo**: `sentinel/core/intent.py`
**Cambio**: Extender estructura `Intent` con campo opcional

**Cambio Específico**:
```python
# ANTES
@dataclass
class Intent:
    action: str
    target: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    raw_input: str = ""

# DESPUÉS
@dataclass
class Intent:
    action: str
    target: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    raw_input: str = ""
    grounding_requirements: List[GroundingRequirement] = field(default_factory=list)  # NUEVO
```

**Integración**:
- Llamar a `GroundingEngine.analyze_requirement()` después de clasificar intent
- Agregar requisitos detectados al intent

### 2.3 Modificación: Tool Gateway

**Archivo**: `sentinel/core/tool_gateway.py`
**Cambio**: Agregar parámetro opcional y validación de grounding

**Cambio Específico**:
```python
# ANTES
async def execute(
    self,
    tool_id: str,
    params: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> ToolResult:

# DESPUÉS
async def execute(
    self,
    tool_id: str,
    params: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    grounding_requirements: Optional[List[GroundingRequirement]] = None,  # NUEVO
) -> ToolResult:
```

**Integración**:
- Validar grounding antes de ejecutar si hay requisitos
- Llamar a `GroundingEngine.enforce_grounding()` si es requerido
- Agregar metadata de grounding al resultado

### 2.4 Modificación: Orchestrator

**Archivo**: `sentinel/core/orchestrator.py`
**Cambio**: Integrar GroundingEngine en el flujo principal

**Cambio Específico**:
```python
# EN __init__
self._grounding_engine = GroundingEngine(
    context_engine=context_engine,
    tool_gateway=tool_gateway,
    capability_registry=capability_registry
)

# EN process()
# Después de IntentEngine.parse()
if self._grounding_engine:
    intent.grounding_requirements = self._grounding_engine.analyze_requirement(intent)

# Antes de ToolGateway.execute()
result = await self._tool_gateway.execute(
    tool_id,
    tool_params,
    context=ctx,
    grounding_requirements=intent.grounding_requirements,  # NUEVO
)
```

---

## 3. FILES AFFECTED

### 3.1 Nuevos Archivos

1. **`sentinel/core/grounding.py`** (NUEVO)
   - ~300 líneas estimadas
   - Componente principal de Grounding Engine
   - Sin dependencias críticas

2. **`sentinel/core/grounding_cache.py`** (NUEVO)
   - ~150 líneas estimadas
   - Caché de datos verificados con TTL
   - Depende de: nada

3. **`tests/test_grounding.py`** (NUEVO)
   - ~200 líneas estimadas
   - Tests exhaustivos de Grounding Engine
   - Depende de: grounding.py

### 3.2 Archivos Modificados

1. **`sentinel/core/intent.py`**
   - Cambio: Agregar campo `grounding_requirements` a `Intent`
   - Líneas afectadas: ~10-15
   - Riesgo: BAJO (campo opcional, código existente ignora)

2. **`sentinel/core/tool_gateway.py`**
   - Cambio: Agregar parámetro `grounding_requirements` a `execute()`
   - Líneas afectadas: ~20-30
   - Riesgo: MEDIO (cambio en interfaz pública, pero parámetro opcional)

3. **`sentinel/core/orchestrator.py`**
   - Cambio: Integrar GroundingEngine en flujo principal
   - Líneas afectadas: ~15-25
   - Riesgo: MEDIO (integración en componente central)

### 3.3 Archivos Sin Cambios

Todos los demás archivos permanecen sin cambios para mantener compatibilidad.

---

## 4. RISK LEVEL

### 4.1 Riesgo General: MEDIO

**Justificación**:
- Componente nuevo (GroundingEngine) no afecta código existente
- Cambios en componentes existentes son aditivos (campos/parámetros opcionales)
- Interfaz pública principal (Orchestrator.process) no cambia
- Puede deshabilitarse mediante configuración

### 4.2 Riesgos Específicos

#### RIESGO 1: Performance Impact
**Severidad**: MEDIA
**Probabilidad**: MEDIA
**Impacto**: Validación de grounding puede agregar latencia
**Mitigación**:
- Implementar caché inteligente
- Validación asíncrona cuando sea posible
- Monitorear métricas de performance
- Configurable TTL para datos cacheados

#### RIESGO 2: False Positives en Grounding
**Severidad**: MEDIA
**Probabilidad**: BAJA
**Impacto**: Puede requerir herramientas innecesariamente
**Mitigación**:
- Heurísticas conservadoras para detección de necesidades de grounding
- Permitir configuración de sensibilidad
- Logging extenso para ajustar heurísticas
- Fallback a comportamiento anterior si hay problemas

#### RIESGO 3: Integración con Orchestrator
**Severidad**: MEDIA
**Probabilidad**: BAJA
**Impacto**: Integración en componente central puede introducir bugs
**Mitigación**:
- Tests exhaustivos de integración
- Comparación con comportamiento anterior
- Feature flag para deshabilitar rápidamente
- Rollback plan preparado

#### RIESGO 4: Compatibilidad con Tests Existentes
**Severidad**: BAJA
**Probabilidad**: BAJA
**Impacto**: Tests existentes pueden fallar por nuevos campos opcionales
**Mitigación**:
- Ejecutar suite de tests existente antes de cambios
- Actualizar tests que dependan de estructura exacta de Intent
- Mantener valores por defecto para nuevos campos

---

## 5. ROLLBACK STRATEGY

### 5.1 Rollback Plan A: Deshabilitar Grounding Engine

**Trigger**: Problemas de performance o falsos positivos
**Acción**:
```python
# En Orchestrator.__init__
self._grounding_engine = None  # Deshabilitar

# O usar configuración
if config.get("enable_grounding", False):
    self._grounding_engine = GroundingEngine(...)
else:
    self._grounding_engine = None
```

**Tiempo**: <5 minutos
**Impacto**: Vuelve a comportamiento anterior
**Riesgo**: Ninguno

### 5.2 Rollback Plan B: Revertir Cambios en Código

**Trigger**: Bugs críticos o incompatibilidad
**Acción**:
- Revertir cambios en `intent.py`
- Revertir cambios en `tool_gateway.py`
- Revertir cambios en `orchestrator.py`
- Mantener archivos nuevos (`grounding.py`, etc.) para futuro uso

**Tiempo**: ~15 minutos
**Impacto**: Vuelve a comportamiento anterior exacto
**Riesgo**: Bajo

### 5.3 Rollback Plan C: Rollback Completo

**Trigger**: Problemas severos que requieren limpieza total
**Acción**:
- Revertir todos los cambios
- Eliminar archivos nuevos
- Restaurar versión anterior de repositorio

**Tiempo**: ~30 minutos
**Impacto**: Vuelve a estado anterior exacto
**Riesgo**: Ninguno

---

## 6. TESTING PLAN

### 6.1 Unit Tests (70%)

#### Tests para GroundingEngine
```python
class TestGroundingEngine:
    def test_system_state_requires_grounding(self):
        """Verifica que queries de sistema requieren grounding"""
        intent = Intent(action="query", target="system.cpu")
        requirements = self.engine.analyze_requirement(intent)
        assert len(requirements) > 0
        assert any(r.category == "system_state" for r in requirements)
    
    def test_file_info_requires_grounding(self):
        """Verifica que queries de archivos requieren grounding"""
        intent = Intent(action="query", target="filesystem.read")
        requirements = self.engine.analyze_requirement(intent)
        assert len(requirements) > 0
        assert any(r.category == "file_info" for r in requirements)
    
    def test_conversation_does_not_require_grounding(self):
        """Verifica que conversación general NO requiere grounding"""
        intent = Intent(action="query", target="general.conversation")
        requirements = self.engine.analyze_requirement(intent)
        assert len(requirements) == 0
    
    def test_freshness_validation_accepts_fresh_data(self):
        """Verifica que datos frescos son aceptados"""
        data = {"timestamp": datetime.now(timezone.utc).isoformat()}
        requirement = GroundingRequirement(category="system_state", required=True, freshness_seconds=10)
        assert self.engine.validate_freshness(data, requirement)
    
    def test_freshness_validation_rejects_stale_data(self):
        """Verifica que datos obsoletos son rechazados"""
        old_time = datetime.now(timezone.utc) - timedelta(seconds=100)
        data = {"timestamp": old_time.isoformat()}
        requirement = GroundingRequirement(category="system_state", required=True, freshness_seconds=10)
        assert not self.engine.validate_freshness(data, requirement)
    
    def test_enforce_grounding_calls_tool(self):
        """Verifica que enforce_grounding llama a la herramienta correcta"""
        requirement = GroundingRequirement(category="system_state", required=True, freshness_seconds=5)
        result = await self.engine.enforce_grounding(requirement, {})
        assert "system" in result
        assert result.get("timestamp") is not None
```

#### Tests para GroundingCache
```python
class TestGroundingCache:
    def test_cache_stores_data(self):
        """Verifica que el caché almacena datos correctamente"""
        self.cache.set("cpu_usage", {"percent": 50}, ttl=10)
        data = self.cache.get("cpu_usage")
        assert data is not None
        assert data["percent"] == 50
    
    def test_cache_expires_after_ttl(self):
        """Verifica que el caché expira después del TTL"""
        self.cache.set("cpu_usage", {"percent": 50}, ttl=1)
        time.sleep(2)
        data = self.cache.get("cpu_usage")
        assert data is None
    
    def test_cache_invalidate_works(self):
        """Verifica que la invalidación de caché funciona"""
        self.cache.set("cpu_usage", {"percent": 50}, ttl=10)
        self.cache.invalidate("cpu_usage")
        data = self.cache.get("cpu_usage")
        assert data is None
```

### 6.2 Integration Tests (20%)

#### Tests de Integración con IntentEngine
```python
class TestIntentEngineGroundingIntegration:
    def test_intent_includes_grounding_requirements(self):
        """Verifica que IntentEngine incluye requisitos de grounding"""
        engine = IntentEngine(grounding_engine=GroundingEngine())
        intent = engine.parse("¿Cuánta CPU tengo?")
        assert len(intent.grounding_requirements) > 0
    
    def test_intent_without_grounding_for_conversation(self):
        """Verifica que conversación general no requiere grounding"""
        engine = IntentEngine(grounding_engine=GroundingEngine())
        intent = engine.parse("¿Qué tiempo hace hoy?")
        assert len(intent.grounding_requirements) == 0
```

#### Tests de Integración con ToolGateway
```python
class TestToolGatewayGroundingIntegration:
    async def test_tool_gateway_validates_grounding(self):
        """Verifica que ToolGateway valida grounding antes de ejecutar"""
        gateway = ToolGateway(grounding_engine=GroundingEngine())
        requirement = GroundingRequirement(category="system_state", required=True, freshness_seconds=5)
        result = await gateway.execute("system.cpu", {}, grounding_requirements=[requirement])
        assert result.success
        assert "grounding_metadata" in result.__dict__
    
    async def test_tool_gateway_executes_without_grounding_if_not_required(self):
        """Verifica que ToolGateway ejecuta sin grounding si no es requerido"""
        gateway = ToolGateway(grounding_engine=GroundingEngine())
        result = await gateway.execute("system.cpu", {}, grounding_requirements=[])
        assert result.success
```

#### Tests de Integración con Orchestrator
```python
class TestOrchestratorGroundingIntegration:
    async def test_orchestrator_uses_grounding_engine(self):
        """Verifica que Orchestrator usa GroundingEngine"""
        orchestrator = create_test_orchestrator(with_grounding=True)
        result = await orchestrator.process("¿Cuánta RAM tengo?")
        assert result.tool_result.success
        # Verificar que se usó grounding
    
    async def test_orchestrator_works_without_grounding_engine(self):
        """Verifica que Orchestrator funciona sin GroundingEngine (compatibilidad)"""
        orchestrator = create_test_orchestrator(with_grounding=False)
        result = await orchestrator.process("¿Cuánta RAM tengo?")
        assert result.tool_result.success
```

### 6.3 E2E Tests (10%)

#### Tests de Flujo Completo
```python
class TestGroundingE2E:
    async def test_user_query_system_state_gets_grounding(self):
        """Verifica que query de estado del sistema usa grounding"""
        # Simular usuario preguntando por CPU
        response = await api_sentinel_process("¿Cuánta CPU tengo?")
        assert response["tool_result"]["success"]
        # Verificar que los datos son frescos (no cacheados por mucho tiempo)
    
    async def test_user_query_general_conversation_no_grounding(self):
        """Verifica que conversación general no usa grounding"""
        response = await api_sentinel_process("Explíname qué es Python")
        assert response["tool_result"]["success"]
        # Verificar que no se forzó grounding innecesario
```

### 6.4 Performance Tests

```python
class TestGroundingPerformance:
    async def test_grounding_adds_acceptable_latency(self):
        """Verifica que grounding agrega latencia aceptable"""
        engine = GroundingEngine()
        start = time.perf_counter()
        await engine.enforce_grounding(
            GroundingRequirement(category="system_state", required=True, freshness_seconds=5),
            {}
        )
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5  # Menos de 500ms
    
    async def test_cache_reduces_latency(self):
        """Verifica que el caché reduce latencia"""
        engine = GroundingEngine()
        # Primera llamada (sin caché)
        start = time.perf_counter()
        await engine.enforce_grounding(
            GroundingRequirement(category="system_state", required=True, freshness_seconds=5),
            {}
        )
        first_call = time.perf_counter() - start
        
        # Segunda llamada (con caché)
        start = time.perf_counter()
        await engine.enforce_grounding(
            GroundingRequirement(category="system_state", required=True, freshness_seconds=5),
            {}
        )
        second_call = time.perf_counter() - start
        
        assert second_call < first_call  # Caché debe ser más rápido
```

### 6.5 Coverage Goal

- **GroundingEngine**: >90% coverage (componente crítico nuevo)
- **GroundingCache**: >85% coverage
- **Integración**: >80% coverage
- **Total FASE 2**: >80% coverage

---

## 7. IMPLEMENTACIÓN DETALLADA

### 7.1 Semana 1: Core Grounding Engine

**Objetivo**: Implementar funcionalidad básica de Grounding Engine

**Tareas**:
1. Crear `sentinel/core/grounding.py` con estructura básica
2. Implementar `GroundingRequirement` dataclass
3. Implementar `GroundingEngine.analyze_requirement()`
4. Implementar heurísticas para detectar necesidades de grounding
5. Unit tests básicos

**Entregables**:
- `sentinel/core/grounding.py` funcional
- Tests unitarios pasando
- Documentación básica

### 7.2 Semana 2: Integración y Caché

**Objetivo**: Integrar con componentes existentes y agregar caché

**Tareas**:
1. Crear `sentinel/core/grounding_cache.py`
2. Implementar `GroundingEngine.enforce_grounding()`
3. Implementar `GroundingEngine.validate_freshness()`
4. Extender `Intent` con `grounding_requirements`
5. Integrar en `IntentEngine`
6. Integration tests

**Entregables**:
- `sentinel/core/grounding_cache.py` funcional
- `Intent` extendido
- `IntentEngine` integrado
- Tests de integración pasando

### 7.3 Semana 3: Tool Gateway y Orchestrator

**Objetivo**: Integrar en flujo principal y pruebas finales

**Tareas**:
1. Integrar en `ToolGateway`
2. Integrar en `Orchestrator`
3. E2E tests
4. Performance tests
5. Documentación completa
6. Code review

**Entregables**:
- Integración completa en pipeline
- Todos los tests pasando
- Documentación completa
- Listo para beta testing

---

## 8. DEPENDENCIAS Y REQUISITOS

### 8.1 Dependencias Existentes (Nuevas)

**Ninguna** - Grounding Engine usa solo dependencias existentes:
- `datetime` (standard library)
- `typing` (standard library)
- `dataclasses` (standard library)
- `asyncio` (standard library)

### 8.2 Dependencias de Componentes

**GroundingEngine depende de**:
- `ContextEngine` (inyectado, opcional)
- `ToolGateway` (inyectado, opcional)
- `CapabilityRegistry` (inyectado, opcional)

**GroundingCache depende de**:
- Ninguna (self-contained)

### 8.3 Requisitos de Sistema

**CPU**: Sin impacto adicional
**RAM**: ~50MB adicional para caché
**Disco**: ~1MB para código nuevo
**Red**: Sin impacto adicional

---

## 9. MÉTRICAS DE ÉXITO

### 9.1 Métricas Técnicas

- **Coverage**: >80% para código nuevo
- **Performance**: <500ms para operaciones de grounding
- **Cache Hit Rate**: >70% para queries repetitivas
- **False Positive Rate**: <5% (grounding cuando no es necesario)

### 9.2 Métricas de Funcionalidad

- **Grounding Detection Rate**: >95% para queries que requieren grounding
- **Freshness Validation**: 100% de datos obsoletos rechazados
- **Integration Success**: 100% de integraciones con componentes existentes funcionando

### 9.3 Métricas de Calidad

- **Bug Rate**: <3 bugs críticos durante fase 2
- **Test Pass Rate**: 100% de tests pasando al final de fase 2
- **Documentation Coverage**: 100% de funciones públicas documentadas

---

## 10. PLAN DE COMUNICACIÓN

### 10.1 Stakeholders

**Desarrolladores**:
- Comunicar cambios en interfaces de `Intent` y `ToolGateway`
- Proporcionar ejemplos de migración
- Documentar backward compatibility

**Usuarios**:
- Comunicar mejora en precisión de respuestas
- Explicar posible latencia adicional
- Proporcionar opción de deshabilitar si hay problemas

**QA**:
- Proporcionar plan de testing detallado
- Comunicar criterios de aceptación
- Documentar casos de prueba

### 10.2 Documentación Requerida

1. **Documentación de API**:
   - Nuevas interfaces en `grounding.py`
   - Cambios en `Intent` y `ToolGateway`
   - Ejemplos de uso

2. **Documentación de Arquitectura**:
   - Diagrama de flujo con Grounding Engine
   - Integración con componentes existentes
   - Patrones de uso

3. **Documentación de Usuario**:
   - Explicación de mejora en precisión
   - Configuración de opciones
   - Solución de problemas

---

## 11. CRITERIOS DE ACEPTACIÓN

### 11.1 Criterios Técnicos

- [ ] Todos los unit tests pasan (>80% coverage)
- [ ] Todos los integration tests pasan
- [ ] Todos los E2E tests pasan
- [ ] Performance tests cumplen objetivos (<500ms)
- [ ] Code review completado y aprobado
- [ ] Sin dependencias nuevas agregadas

### 11.2 Criterios Funcionales

- [ ] Grounding Engine detecta >95% de queries que requieren grounding
- [ ] Validación de frescura funciona correctamente
- [ ] Caché reduce latencia en >70% de casos repetitivos
- [ ] Integración con IntentEngine funciona sin problemas
- [ ] Integración con ToolGateway funciona sin problemas
- [ ] Integración con Orchestrator funciona sin problemas

### 11.3 Criterios de Calidad

- [ ] Documentación completa y precisa
- [ ] Código sigue convenciones del proyecto
- [ ] Sin warnings de linter
- [ ] Sin vulnerabilidades de seguridad introducidas
- [ ] Compatible con versiones existentes

---

## 12. CONFIRMACIÓN REQUERIDA

Antes de proceder con la implementación de FASE 2, confirmar:

1. **¿Aprobar el plan de implementación propuesto?**
2. **¿Están de acuerdo con la estrategia de testing?**
3. **¿¿Los criterios de aceptación son apropiados?**
4. **¿¿Algún ajuste requerido antes de comenzar la implementación?**

---

**DOCUMENTO FASE_2_ARCHITECTURE_IMPACT.md COMPLETADO**

Este documento detalla el impacto arquitectónico de implementar el Grounding Engine en FASE 2, incluyendo archivos afectados, nivel de riesgo, estrategia de rollback y plan de testing.

**ESTADO**: Pendiente de aprobación antes de implementación.
