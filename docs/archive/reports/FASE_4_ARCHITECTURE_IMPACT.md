# FASE 4: DECISION ENGINE SEGURO - ARCHITECTURE IMPACT

**Fecha**: 2025-01-17
**Fase**: 4 - Decision Engine Seguro
**Prioridad**: CRÍTICA
**Duración Estimada**: 2 semanas
**Estado**: Pendiente de aprobación

---

## 1. PROPÓSITO

Refactorizar el Decision Engine para eliminar la autoridad del LLM en decisiones de seguridad, convirtiéndolo en un advisor opcional con validación estricta de salidas y fallback seguro a evaluación objetiva.

**Objetivo**: El LLM debe ser solamente un asesor, nunca una autoridad. La decisión final debe basarse en datos objetivos y políticas del sistema.

---

## 2. ARCHITECTURE IMPACT

### 2.1 Nuevo Componente: LLM Decision Advisor

**Archivo**: `sentinel/core/llm_decision_advisor.py` (NUEVO)
**Responsabilidad**: 
- Proporcionar advice del LLM para decisiones de riesgo (SIN autoridad)
- Validar estrictamente la salida del LLM
- Registrar incertidumbre en recommendations
- Ser completamente opcional (el sistema funciona sin él)

**Dependencias**:
- ModelRouter (para llamar al LLM)
- LLMOutputValidator (para validar salidas)

**Interfaces Públicas**:
```python
@dataclass
class LLMAdvice:
    """Advice del LLM sobre decisiones de riesgo"""
    risk_modifier: float  # -0.2 a 0.3
    reason: str
    warnings: List[str]
    confidence: float  # 0.0 a 1.0
    uncertainty_factors: List[str]
    timestamp: str

class LLMDecisionAdvisor:
    def __init__(self, model_router: ModelRouter)
    async def advise(self, plan: Plan, context: Dict[str, Any]) -> Optional[LLMAdvice]
    def is_available(self) -> bool
```

### 2.2 Nuevo Componente: LLM Output Validator

**Archivo**: `sentinel/core/llm_output_validator.py` (NUEVO)
**Responsabilidad**: 
- Validar estrictamente la salida del LLM
- Verificar cumplimiento de JSON schema
- Validar rangos de valores
- Detectar anomalías en la respuesta

**Dependencias**:
- Ninguna (self-contained)

**Interfaces Públicas**:
```python
class LLMOutputValidator:
    def __init__(self)
    def validate_risk_assessment(self, response: Dict[str, Any]) -> Tuple[bool, List[str]]
    def validate_json_schema(self, response: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, List[str]]
    def validate_value_ranges(self, response: Dict[str, Any], constraints: Dict[str, Any]) -> Tuple[bool, List[str]]
```

### 2.3 Nuevo Componente: Objective Risk Assessor

**Archivo**: `sentinel/core/objective_risk_assessor.py` (NUEVO)
**Responsabilidad**: 
- Evaluar riesgo basado en datos objetivos (SIN LLM)
- Usar SimulationEngine, PolicyEngine, ContextEngine
- Priorizar datos verificables sobre opinion del modelo
- Ser la fuente primaria de evaluación de riesgo

**Dependencias**:
- SimulationEngine (para simulación de impacto)
- PolicyEngine (para evaluación de políticas)
- ContextEngine (para estado del sistema)

**Interfaces Públicas**:
```python
@dataclass
class ObjectiveRiskAssessment:
    """Evaluación de riesgo basada en datos objetivos"""
    risk_score: float
    factors: List[str]
    confidence: float
    data_sources: List[str]  # ['simulation', 'policy', 'system_state']
    requires_confirmation: bool
    irreversible: bool

class ObjectiveRiskAssessor:
    def __init__(self, simulation_engine, policy_engine, context_engine)
    async def assess(self, plan: Plan, context: Dict[str, Any]) -> ObjectiveRiskAssessment
```

### 2.4 Nuevo Componente: Uncertainty Tracker

**Archivo**: `sentinel/core/uncertainty_tracker.py` (NUEVO)
**Responsabilidad**: 
- Registrar incertidumbre en decisiones
- Rastrear cuando el LLM no está seguro
- Mantener historial de precisiones del LLM
- Proporcionar métricas de confianza

**Dependencias**:
- Ninguna (self-contained)

**Interfaces Públicas**:
```python
@dataclass
class UncertaintyRecord:
    plan_id: str
    llm_confidence: float
    objective_confidence: float
    discrepancy: float
    timestamp: str
    outcome: str  # 'correct', 'incorrect', 'unknown'

class UncertaintyTracker:
    def __init__(self)
    def record_advice(self, plan_id: str, advice: LLMAdvice, objective: ObjectiveRiskAssessment)
    def record_outcome(self, plan_id: str, outcome: str)
    def get_uncertainty_metrics(self) -> Dict[str, Any]
    def should_trust_llm(self) -> bool
```

### 2.5 Modificación Principal: Decision Engine

**Archivo**: `sentinel/core/decision_engine.py`
**Cambio**: Refactorizar para usar advisor pattern con LLM opcional

**Cambio Específico**:
```python
# ANTES
class DecisionEngine:
    def __init__(self, ...):
        self._model_router = model_router  # LLM tiene autoridad directa
    
    async def evaluate(self, plan: Plan, context: Optional[Dict[str, Any]] = None) -> DecisionResult:
        # ... código existente ...
        # LLM puede modificar risk_score directamente
        if final_risk > auto_max or irreversible_high_risk:
            llm_assessment = self._assess_risk_with_llm(plan, context)
            if llm_assessment:
                modifier = llm_assessment.get("risk_modifier", 0)
                final_risk = min(max(final_risk + modifier, 0.0), 1.0)  # LLM tiene autoridad

# DESPUÉS
class DecisionEngine:
    def __init__(self, ...):
        self._llm_advisor = None  # LLM es advisor opcional, NO autoridad
        self._objective_assessor = ObjectiveRiskAssessor(simulation_engine, policy_engine, context_engine)
        self._uncertainty_tracker = UncertaintyTracker()
    
    def set_llm_advisor(self, advisor: LLMDecisionAdvisor):
        """Configura el advisor LLM (opcional)"""
        self._llm_advisor = advisor
    
    async def evaluate(self, plan: Plan, context: Optional[Dict[str, Any]] = None) -> DecisionResult:
        # 1. Evaluar riesgo basado en datos objetivos (PRIORIDAD)
        objective_assessment = await self._objective_assessor.assess(plan, context)
        
        # 2. Si hay advisor LLM, solicitar advice (NO autoridad)
        llm_advice = None
        if self._llm_advisor and self._llm_advisor.is_available():
            try:
                llm_advice = await self._llm_advisor.advise(plan, context)
                if llm_advice:
                    self._uncertainty_tracker.record_advice(plan.id, llm_advice, objective_assessment)
            except Exception as e:
                logger.warning("LLM advice failed: %s", e)
        
        # 3. Combinar evaluación objetiva con advice LLM (si disponible)
        final_assessment = self._combine_assessments(objective_assessment, llm_advice)
        
        # 4. Generar decisión basada en evaluación final
        return self._generate_decision(final_assessment, plan, context)
    
    def _combine_assessments(self, objective: ObjectiveRiskAssessment, llm: Optional[LLMAdvice]) -> Dict[str, Any]:
        """Combina evaluación objetiva con advice LLM"""
        # La evaluación objetiva SIEMPRE tiene prioridad
        # El LLM solo puede influir si hay alta discrepancia y el tracker indica confianza
        if not llm:
            return {"risk_score": objective.risk_score, "confidence": objective.confidence}
        
        # Si hay alta discrepancia y el LLM no es confiable, ignorar advice
        discrepancy = abs(objective.risk_score - llm.risk_modifier)
        if discrepancy > 0.3 and not self._uncertainty_tracker.should_trust_llm():
            logger.warning("Ignoring LLM advice due to high discrepancy and low trust")
            return {"risk_score": objective.risk_score, "confidence": objective.confidence}
        
        # Aplicar modifier del LLM solo si es pequeño y hay confianza
        if discrepancy < 0.1 and self._uncertainty_tracker.should_trust_llm():
            adjusted_score = min(max(objective.risk_score + llm.risk_modifier, 0.0), 1.0)
            return {
                "risk_score": adjusted_score,
                "confidence": (objective.confidence + llm.confidence) / 2,
                "llm_influenced": True
            }
        
        # Por default, priorizar evaluación objetiva
        return {"risk_score": objective.risk_score, "confidence": objective.confidence}
```

**Integración**:
- El LLM ahora es completamente opcional
- La evaluación objetiva tiene prioridad absoluta
- El sistema funciona correctamente sin LLM
- Validación estricta de cualquier salida del LLM

### 2.6 Modificación: Orchestrator

**Archivo**: `sentinel/core/orchestrator.py`
**Cambio**: Configurar LLM advisor en Decision Engine

**Cambio Específico**:
```python
# EN __init__
if model_router:
    # Crear y configurar LLM advisor (opcional)
    from sentinel.core.llm_decision_advisor import LLMDecisionAdvisor
    llm_advisor = LLMDecisionAdvisor(model_router)
    decision_engine.set_llm_advisor(llm_advisor)
```

**Integración**:
- El advisor se configura pero no es requerido
- Si ModelRouter no está disponible, Decision Engine funciona sin LLM

### 2.7 Modificación: Simulation Engine

**Archivo**: `sentinel/core/simulation.py`
**Cambio**: Mejorar detección de acciones peligrosas

**Cambio Específico**:
```python
# ANTES
def _predict_impact(self, step_id: str, tool_id: str, ...) -> SimulatedImpact:
    base = _TOOL_IMPACT.get(tool_id, {"type": "execute", "level": "medium", "duration": 1000})
    # ... lógica existente ...

# DESPUÉS
def _predict_impact(self, step_id: str, tool_id: str, ...) -> SimulatedImpact:
    base = _TOOL_IMPACT.get(tool_id, {"type": "execute", "level": "medium", "duration": 1000})
    
    # MEJORAR detección de comandos peligrosos
    if tool_id == "executor.command":
        cmd = params.get("command", params.get("cmd", ""))
        danger_patterns = [
            r"rm\s+-rf\s+/?",  # rm -rf /
            r"shutdown", r"reboot", r"halt",
            r"format", r"mkfs", r"dd\s+if=",
            r">\s*/dev/",  # Redirection a /dev/
            r"curl.*\|.*sh", r"wget.*\|.*sh",  # Pipe a shell
            r"chmod\s+777", r"chown\s+.*:",  # Permisos peligrosos
            r"passwd", r"su\s+",  # Comandos de autenticación
        ]
        
        for pattern in danger_patterns:
            if re.search(pattern, cmd, re.IGNORECASE):
                impact_level = "critical"
                warnings.append(f"CRITICAL: Command matches dangerous pattern: {pattern}")
                irreversible = True
                break
    
    # MEJORAR detección de archivos sensibles
    if tool_id in ("filesystem.write", "filesystem.delete"):
        path = params.get("path", params.get("file", ""))
        sensitive_paths = [
            "/etc/", "/sys/", "/proc/", "/boot/",
            "\\.env$", "\\.pem$", "\\.key$", "\\.cert$",
            "shadow", "passwd", "sudoers",
        ]
        
        for sensitive in sensitive_paths:
            if sensitive in path.lower():
                impact_level = "critical"
                warnings.append(f"CRITICAL: Operating on sensitive path: {sensitive}")
                irreversible = True
                break
    
    # ... resto de lógica existente ...
```

**Integración**:
- Mejora significativa en detección de acciones peligrosas
- Proporciona datos objetivos más confiables para Decision Engine

---

## 3. FILES AFFECTED

### 3.1 Nuevos Archivos

1. **`sentinel/core/llm_decision_advisor.py`** (NUEVO)
   - ~200 líneas estimadas
   - Advisor LLM para decisiones de riesgo
   - Depende de: ModelRouter

2. **`sentinel/core/llm_output_validator.py`** (NUEVO)
   - ~250 líneas estimadas
   - Validador estricto de salidas del LLM
   - Sin dependencias críticas

3. **`sentinel/core/objective_risk_assessor.py`** (NUEVO)
   - ~300 líneas estimadas
   - Evaluación objetiva de riesgo
   - Depende de: SimulationEngine, PolicyEngine, ContextEngine

4. **`sentinel/core/uncertainty_tracker.py`** (NUEVO)
   - ~200 líneas estimadas
   - Rastreador de incertidumbre
   - Sin dependencias críticas

5. **`tests/test_llm_decision_advisor.py`** (NUEVO)
   - ~150 líneas estimadas
   - Tests de LLM advisor

6. **`tests/test_llm_output_validator.py`** (NUEVO)
   - ~200 líneas estimadas
   - Tests de validador de salida

7. **`tests/test_objective_risk_assessor.py`** (NUEVO)
   - ~250 líneas estimadas
   - Tests de evaluador objetivo

8. **`tests/test_uncertainty_tracker.py`** (NUEVO)
   - ~150 líneas estimadas
   - Tests de tracker de incertidumbre

### 3.2 Archivos Modificados

1. **`sentinel/core/decision_engine.py`**
   - Cambio: Refactorizar completo para advisor pattern
   - Cambio: LLM ahora es opcional, no autoridad
   - Cambio: Priorizar evaluación objetiva
   - Líneas afectadas: ~100-150
   - Riesgo: ALTO (componente crítico de seguridad)

2. **`sentinel/core/orchestrator.py`**
   - Cambio: Configurar LLM advisor en Decision Engine
   - Líneas afectadas: ~10-15
   - Riesgo: BAJO (cambio de inicialización)

3. **`sentinel/core/simulation.py`**
   - Cambio: Mejorar detección de acciones peligrosas
   - Líneas afectadas: ~50-70
   - Riesgo: MEDIO (mejora en componente existente)

### 3.3 Archivos Sin Cambios

Todos los demás archivos permanecen sin cambios para mantener compatibilidad.

---

## 4. RISK LEVEL

### 4.1 Riesgo General: ALTO

**Justificación**:
- Cambios en componente crítico de seguridad (Decision Engine)
- Refactorización significativa de lógica existente
- Riesgo de regresión en comportamiento de decisiones
- Requiere testing exhaustivo para asegurar seguridad

### 4.2 Riesgos Específicos

#### RIESGO 1: Regresión en Decisiones de Seguridad
**Severidad**: CRÍTICA
**Probabilidad**: MEDIA
**Impacto**: Decisiones incorrectas pueden permitir acciones peligrosas
**Mitigación**:
- Testing exhaustivo de todos los escenarios de decisión
- Comparación sistemática con comportamiento anterior
- Suite de tests de seguridad completa
- Beta testing prolongado
- Feature flag para deshabilitar rápidamente

#### RIESGO 2: LLM Validator Rechaza Respuestas Válidas
**Severidad**: MEDIA
**Probabilidad**: BAJA
**Impacto**: Advisor LLM puede no ser útil si validator es demasiado estricto
**Mitigación**:
- Validator debe ser conservador pero no demasiado estricto
- Logging extenso de validaciones
- Ajuste de umbrales basado en datos reales
- Fallback a evaluación objetiva siempre disponible

#### RIESGO 3: Objective Risk Assessor Insuficiente
**Severidad**: ALTA
**Probabilidad**: MEDIA
**Impacto**: Evaluación objetiva puede no capturar todos los riesgos
**Mitigación**:
- Mejorar SimulationEngine significativamente
- Integrar múltiples fuentes de datos objetivos
- Validación con expertos en seguridad
- Umbral conservador por defecto

#### RIESGO 4: Performance Impact por Evaluación Objetiva
**Severidad**: MEDIA
**Probabilidad**: BAJA
**Impacto**: Evaluación objetiva puede ser más lenta que LLM
**Mitigación**:
- Optimizar SimulationEngine
- Caché de evaluaciones repetitivas
- Paralelizar cuando sea posible
- Métricas de performance en tests

#### RIESGO 5: Compatibilidad con Tests Existentes
**Severidad**: MEDIA
**Probabilidad**: MEDIA
**Impacto**: Tests existentes pueden fallar por cambios en Decision Engine
**Mitigación**:
- Ejecutar suite de tests existente antes de cambios
- Actualizar tests que dependen de comportamiento exacto
- Mantener interfaz pública de Decision Engine

---

## 5. ROLLBACK STRATEGY

### 5.1 Rollback Plan A: Deshabilitar LLM Advisor

**Trigger**: Problemas con advisor LLM o validación
**Acción**:
```python
# En Orchestrator.__init__
if config.get("enable_llm_advisor", False):  # Default False
    llm_advisor = LLMDecisionAdvisor(model_router)
    decision_engine.set_llm_advisor(llm_advisor)
else:
    decision_engine.set_llm_advisor(None)
```

**Tiempo**: <5 minutos
**Impacto**: Sistema funciona con evaluación objetiva solamente
**Riesgo**: Ninguno (evaluación objetiva es más segura que LLM)

### 5.2 Rollback Plan B: Revertir Decision Engine

**Trigger**: Regresión crítica en decisiones de seguridad
**Acción**:
- Revertir cambios en `decision_engine.py` a versión anterior
- Mantener nuevos componentes (para futuro uso)
- Deshabilitar integración en Orchestrator

**Tiempo**: ~15 minutos
**Impacto**: Vuelve a comportamiento anterior exacto
**Riesgo: Bajo

### 5.3 Rollback Plan C: Rollback Completo

**Trigger**: Problemas severos que requieren limpieza total
**Acción**:
- Revertir todos los cambios en decision_engine.py
- Revertir cambios en orchestrator.py
- Revertir cambios en simulation.py
- Eliminar archivos nuevos
- Restaurar versión anterior de repositorio

**Tiempo**: ~30 minutos
**Impacto**: Vuelve a estado anterior exacto
**Riesgo**: Ninguno

---

## 6. TESTING PLAN

### 6.1 Unit Tests (70%)

#### Tests para LLMDecisionAdvisor
```python
class TestLLMDecisionAdvisor:
    async def test_advisor_provides_valid_advice(self):
        """Verifica que advisor proporciona advice válido"""
        advisor = LLMDecisionAdvisor(model_router)
        plan = create_test_plan()
        
        advice = await advisor.advise(plan, {})
        
        assert advice is not None
        assert -0.2 <= advice.risk_modifier <= 0.3
        assert 0.0 <= advice.confidence <= 1.0
        assert advice.timestamp is not None
    
    async def test_advisor_handles_llm_failure(self):
        """Verifica que advisor maneja fallos del LLM"""
        advisor = LLMDecisionAdvisor(failing_model_router)
        plan = create_test_plan()
        
        advice = await advisor.advise(plan, {})
        
        # Debe retornar None en caso de fallo
        assert advice is None
    
    def test_advisor_is_available(self):
        """Verifica que advisor reporta disponibilidad correctamente"""
        advisor = LLMDecisionAdvisor(model_router)
        assert advisor.is_available() == True
        
        advisor_no_router = LLMDecisionAdvisor(None)
        assert advisor_no_router.is_available() == False
```

#### Tests para LLMOutputValidator
```python
class TestLLMOutputValidator:
    def test_validator_accepts_valid_json(self):
        """Verifica que validator acepta JSON válido"""
        validator = LLMOutputValidator()
        response = {
            "risk_modifier": 0.1,
            "reason": "Low risk",
            "warnings": []
        }
        
        valid, errors = validator.validate_risk_assessment(response)
        assert valid == True
        assert len(errors) == 0
    
    def test_validator_rejects_invalid_risk_modifier(self):
        """Verifica que validator rechaza modifier fuera de rango"""
        validator = LLMOutputValidator()
        response = {
            "risk_modifier": 0.5,  # Fuera de rango (-0.2 a 0.3)
            "reason": "Test",
            "warnings": []
        }
        
        valid, errors = validator.validate_risk_assessment(response)
        assert valid == False
        assert any("risk_modifier" in error for error in errors)
    
    def test_validator_rejects_missing_fields(self):
        """Verifica que validator rechaza campos faltantes"""
        validator = LLMOutputValidator()
        response = {
            "risk_modifier": 0.1,
            # Falta "reason" y "warnings"
        }
        
        valid, errors = validator.validate_risk_assessment(response)
        assert valid == False
        assert len(errors) > 0
    
    def test_validator_detects_anomalies(self):
        """Verifica que validator detecta anomalías"""
        validator = LLMOutputValidator()
        response = {
            "risk_modifier": 0.1,
            "reason": "Very long " * 100,  # Anomalía: texto excesivamente largo
            "warnings": []
        }
        
        valid, errors = validator.validate_risk_assessment(response)
        assert valid == False
```

#### Tests para ObjectiveRiskAssessor
```python
class TestObjectiveRiskAssessor:
    async def test_assessor_uses_simulation(self):
        """Verifica que assessor usa SimulationEngine"""
        simulation = MockSimulationEngine()
        policy = MockPolicyEngine()
        context = MockContextEngine()
        assessor = ObjectiveRiskAssessor(simulation, policy, context)
        
        plan = create_test_plan()
        assessment = await assessor.assess(plan, {})
        
        assert "simulation" in assessment.data_sources
        assert simulation.was_called()
    
    async def test_assessor_detects_irreversible_actions(self):
        """Verifica que assessor detecta acciones irreversibles"""
        simulation = MockSimulationEngine(irreversible=True)
        policy = MockPolicyEngine()
        context = MockContextEngine()
        assessor = ObjectiveRiskAssessor(simulation, policy, context)
        
        plan = create_test_plan(irreversible=True)
        assessment = await assessor.assess(plan, {})
        
        assert assessment.irreversible == True
        assert assessment.requires_confirmation == True
    
    async def test_assessor_prioritizes_objective_data(self):
        """Verifica que assessor prioriza datos objetivos"""
        simulation = MockSimulationEngine()
        policy = MockPolicyEngine()
        context = MockContextEngine()
        assessor = ObjectiveRiskAssessor(simulation, policy, context)
        
        plan = create_test_plan()
        assessment = await assessor.assess(plan, {})
        
        assert len(assessment.data_sources) > 0
        assert all(source in ["simulation", "policy", "system_state"] for source in assessment.data_sources)
```

#### Tests para UncertaintyTracker
```python
class TestUncertaintyTracker:
    def test_tracker_records_advice(self):
        """Verifica que tracker registra advice del LLM"""
        tracker = UncertaintyTracker()
        llm_advice = LLMAdvice(risk_modifier=0.1, confidence=0.8, ...)
        objective = ObjectiveRiskAssessment(risk_score=0.3, confidence=0.9, ...)
        
        tracker.record_advice("plan_123", llm_advice, objective)
        
        metrics = tracker.get_uncertainty_metrics()
        assert metrics["total_advices"] == 1
    
    def test_tracker_calculates_discrepancy(self):
        """Verifica que tracker calcula discrepancia correctamente"""
        tracker = UncertaintyTracker()
        llm_advice = LLMAdvice(risk_modifier=0.3, confidence=0.8, ...)
        objective = ObjectiveRiskAssessment(risk_score=0.5, confidence=0.9, ...)
        
        tracker.record_advice("plan_123", llm_advice, objective)
        
        metrics = tracker.get_uncertainty_metrics()
        assert metrics["average_discrepancy"] == 0.2  # |0.5 - 0.3|
    
    def test_tracker_determines_trust(self):
        """Verifica que tracker determina confianza correctamente"""
        tracker = UncertaintyTracker()
        
        # Registrar varios advices con alta discrepancia
        for i in range(10):
            llm_advice = LLMAdvice(risk_modifier=0.3, confidence=0.8, ...)
            objective = ObjectiveRiskAssessment(risk_score=0.0, confidence=0.9, ...)  # Alta discrepancia
            tracker.record_advice(f"plan_{i}", llm_advice, objective)
        
        assert tracker.should_trust_llm() == False
    
    def test_tracker_learns_from_outcomes(self):
        """Verifica que tracker aprende de resultados"""
        tracker = UncertaintyTracker()
        
        # Registrar advice correcto
        tracker.record_advice("plan_1", LLMAdvice(risk_modifier=0.1, ...), ObjectiveRiskAssessment(risk_score=0.15, ...))
        tracker.record_outcome("plan_1", "correct")
        
        # Registrar advice incorrecto
        tracker.record_advice("plan_2", LLMAdvice(risk_modifier=0.3, ...), ObjectiveRiskAssessment(risk_score=0.0, ...))
        tracker.record_outcome("plan_2", "incorrect")
        
        metrics = tracker.get_uncertainty_metrics()
        assert metrics["accuracy"] == 0.5
```

### 6.2 Integration Tests (20%)

#### Tests de Integración con Decision Engine
```python
class TestDecisionEngineIntegration:
    async def test_decision_engine_works_without_llm(self):
        """Verifica que Decision Engine funciona sin LLM advisor"""
        engine = DecisionEngine()  # Sin LLM advisor
        plan = create_test_plan()
        
        result = engine.evaluate(plan, {})
        
        assert result.decision in [Decision.APPROVE, Decision.REJECT, Decision.REQUIRE_CONFIRM]
        # Debe basarse en evaluación objetiva
    
    async def test_decision_engine_uses_llm_when_available(self):
        """Verifica que Decision Engine usa LLM cuando está disponible"""
        llm_advisor = MockLLMAdvisor(advice=LLMAdvice(risk_modifier=0.1, ...))
        engine = DecisionEngine()
        engine.set_llm_advisor(llm_advisor)
        
        plan = create_test_plan()
        result = engine.evaluate(plan, {})
        
        # Debe considerar advice del LLM
        assert llm_advisor.was_called()
    
    async def test_decision_engine_ignores_unreliable_llm(self):
        """Verifica que Decision Engine ignora LLM no confiable"""
        llm_advisor = MockLLMAdvisor(advice=LLMAdvice(risk_modifier=0.5, ...))  # Alta discrepancia
        tracker = UncertaintyTracker()
        tracker.record_many_discrepancies()  # Hacer que LLM no sea confiable
        
        engine = DecisionEngine()
        engine.set_llm_advisor(llm_advisor)
        engine._uncertainty_tracker = tracker
        
        plan = create_test_plan()
        result = engine.evaluate(plan, {})
        
        # Debe ignorar advice del LLM
        assert not result.context_factors.get("llm_influenced", False)
    
    async def test_decision_engine_prioritizes_objective_over_llm(self):
        """Verifica que evaluación objetiva tiene prioridad"""
        objective_assessor = MockObjectiveAssessor(risk_score=0.8)  # Alto riesgo objetivo
        llm_advisor = MockLLMAdvisor(advice=LLMAdvice(risk_modifier=-0.2, ...))  # Bajo riesgo según LLM
        
        engine = DecisionEngine()
        engine._objective_assessor = objective_assessor
        engine.set_llm_advisor(llm_advisor)
        
        plan = create_test_plan()
        result = engine.evaluate(plan, {})
        
        # Debe priorizar riesgo objetivo alto
        assert result.final_risk_score > 0.5
```

#### Tests de Regresión
```python
class TestDecisionEngineRegression:
    async def test_critical_actions_still_require_confirmation(self):
        """Verifica que acciones críticas aún requieren confirmación"""
        engine = DecisionEngine()
        
        # Acción destructiva
        plan = create_destructive_plan()
        result = engine.evaluate(plan, {})
        
        assert result.decision == Decision.REQUIRE_CONFIRM
    
    async def test_safe_actions_still_auto_approve(self):
        """Verifica que acciones seguras aún se auto-aprueban"""
        engine = DecisionEngine()
        
        # Acción segura
        plan = create_safe_plan()
        result = engine.evaluate(plan, {})
        
        assert result.decision == Decision.APPROVE
    
    async def test_irreversible_actions_still_blocked_or_confirm(self):
        """Verifica que acciones irreversibles se bloquean o requieren confirmación"""
        engine = DecisionEngine()
        
        # Acción irreversible
        plan = create_irreversible_plan()
        result = engine.evaluate(plan, {})
        
        assert result.decision in [Decision.REJECT, Decision.REQUIRE_CONFIRM]
```

### 6.3 Security Tests (10%)

```python
class TestDecisionEngineSecurity:
    async def test_llm_cannot_bypass_policies(self):
        """Verifica que LLM no puede bypass políticas"""
        # Crear plan que viola política
        plan = create_policy_violating_plan()
        
        # LLM advisor intenta aprobar
        llm_advisor = MockLLMAdvisor(advice=LLMAdvice(risk_modifier=-0.2, ...))  # Reduce riesgo
        
        engine = DecisionEngine()
        engine.set_llm_advisor(llm_advisor)
        
        result = engine.evaluate(plan, {})
        
        # Debe ser rechazado o requerir confirmación (política tiene prioridad)
        assert result.decision in [Decision.REJECT, Decision.REQUIRE_CONFIRM]
    
    async def test_llm_cannot_reduce_critical_risk(self):
        """Verifica que LLM no puede reducir riesgo crítico"""
        plan = create_critical_risk_plan()
        
        # LLM advisor intenta reducir riesgo drásticamente
        llm_advisor = MockLLMAdvisor(advice=LLMAdvice(risk_modifier=-0.5, ...))  # Reduce mucho
        
        engine = DecisionEngine()
        engine.set_llm_advisor(llm_advisor)
        
        result = engine.evaluate(plan, {})
        
        # Debe mantener alto riesgo o requerir confirmación
        assert result.final_risk_score > 0.7 or result.decision == Decision.REQUIRE_CONFIRM
    
    async def test_invalid_llm_output_is_ignored(self):
        """Verifica que salida inválida del LLM es ignorada"""
        plan = create_test_plan()
        
        # LLM advisor retorna respuesta inválida
        llm_advisor = MockLLMAdvisor(advice=None)  # Simula validación fallida
        
        engine = DecisionEngine()
        engine.set_llm_advisor(llm_advisor)
        
        result = engine.evaluate(plan, {})
        
        # Debe funcionar correctamente sin LLM
        assert result.decision in [Decision.APPROVE, Decision.REJECT, Decision.REQUIRE_CONFIRM]
```

### 6.4 Performance Tests

```python
class TestDecisionEnginePerformance:
    async def test_objective_assessment_performance(self):
        """Verifica que evaluación objetiva tiene performance aceptable"""
        assessor = ObjectiveRiskAssessor(simulation, policy, context)
        plan = create_test_plan()
        
        start = time.perf_counter()
        assessment = await assessor.assess(plan, {})
        elapsed = time.perf_counter() - start
        
        assert elapsed < 1.0  # Menos de 1 segundo
    
    async def test_decision_engine_with_llm_performance(self):
        """Verifica que Decision Engine con LLM tiene performance aceptable"""
        engine = DecisionEngine()
        engine.set_llm_advisor(llm_advisor)
        plan = create_test_plan()
        
        start = time.perf_counter()
        result = engine.evaluate(plan, {})
        elapsed = time.perf_counter() - start
        
        assert elapsed < 2.0  # Menos de 2 segundos con LLM
    
    async def test_decision_engine_without_llm_performance(self):
        """Verifica que Decision Engine sin LLM es más rápido"""
        engine = DecisionEngine()
        # Sin LLM advisor
        plan = create_test_plan()
        
        start = time.perf_counter()
        result = engine.evaluate(plan, {})
        elapsed = time.perf_counter() - start
        
        assert elapsed < 0.5  # Menos de 500ms sin LLM
```

### 6.5 Coverage Goal

- **LLMDecisionAdvisor**: >85% coverage
- **LLMOutputValidator**: >90% coverage (componente crítico)
- **ObjectiveRiskAssessor**: >90% coverage (componente crítico)
- **UncertaintyTracker**: >85% coverage
- **DecisionEngine**: >85% coverage (componente modificado)
- **Total FASE 4**: >85% coverage (más alto por ser componente crítico)

---

## 7. IMPLEMENTACIÓN DETALLADA

### 7.1 Semana 1: Componentes de Validación y Evaluación Objetiva

**Objetivo**: Implementar componentes de validación y evaluación objetiva

**Tareas**:
1. Crear `sentinel/core/llm_output_validator.py`
2. Crear `sentinel/core/objective_risk_assessor.py`
3. Crear `sentinel/core/uncertainty_tracker.py`
4. Mejorar `sentinel/core/simulation.py` (detección de acciones peligrosas)
5. Unit tests para todos los componentes nuevos
6. Integration tests con SimulationEngine

**Entregables**:
- Componentes de validación funcionales
- Evaluación objetiva mejorada
- Tests unitarios pasando
- Documentación básica

### 7.2 Semana 2: LLM Advisor y Refactorización de Decision Engine

**Objetivo**: Implementar advisor LLM y refactorizar Decision Engine

**Tareas**:
1. Crear `sentinel/core/llm_decision_advisor.py`
2. Refactorizar `sentinel/core/decision_engine.py` (advisor pattern)
3. Integrar en `sentinel/core/orchestrator.py`
4. Integration tests completos
5. Security tests
6. Performance tests
7. Tests de regresión exhaustivos
8. Documentación completa
9. Code review

**Entregables**:
- Decision Engine refactorizado con advisor pattern
- LLM advisor opcional funcionando
- Todos los tests pasando
- Documentación completa
- Listo para beta testing prolongado

---

## 8. DEPENDENCIAS Y REQUISITOS

### 8.1 Dependencias Existentes (Nuevas)

**Ninguna** - Todos los componentes nuevos usan solo dependencias existentes:
- `asyncio` (standard library)
- `typing` (standard library)
- `dataclasses` (standard library)
- `re` (standard library)
- Componentes existentes de Sentinel

### 8.2 Dependencias de Componentes

**LLMDecisionAdvisor depende de**:
- ModelRouter (inyectado, opcional)

**LLMOutputValidator depende de**:
- Ninguna (self-contained)

**ObjectiveRiskAssessor depende de**:
- SimulationEngine (inyectado)
- PolicyEngine (inyectado)
- ContextEngine (inyectado)

**UncertaintyTracker depende de**:
- Ninguna (self-contained)

### 8.3 Requisitos de Sistema

**CPU**: Sin impacto adicional significativo
**RAM**: ~20MB adicional para nuevos componentes
**Disco**: ~3MB para código nuevo
**Red**: Sin impacto adicional

---

## 9. MÉTRICAS DE ÉXITO

### 9.1 Métricas Técnicas

- **Coverage**: >85% para código nuevo (más alto por ser crítico)
- **Performance**: <500ms para Decision Engine sin LLM
- **Performance**: <2s para Decision Engine con LLM
- **LLM Validation Rate**: 100% de salidas del LLM validadas
- **Objective Assessment Success**: >95% de evaluaciones objetivas exitosas

### 9.2 Métricas de Seguridad

- **LLM Authority Removal**: 100% (LLM no tiene autoridad)
- **Policy Compliance**: 100% (políticas siempre respetadas)
- **Regression Rate**: 0% de regresiones en decisiones de seguridad
- **Critical Action Protection**: 100% (acciones críticas protegidas)

### 9.3 Métricas de Confianza

- **LLM Trust Accuracy**: >80% (tracker determina confianza correctamente)
- **Objective Priority**: 100% (evaluación objetiva siempre priorizada)
- **Uncertainty Detection**: >90% (incertidumbre detectada correctamente)

### 9.4 Métricas de Calidad

- **Bug Rate**: <2 bugs críticos durante fase 4
- **Test Pass Rate**: 100% de tests pasando al final
- **Documentation Coverage**: 100% de funciones públicas documentadas

---

## 10. PLAN DE COMUNICACIÓN

### 10.1 Stakeholders

**Equipo de Seguridad**:
- Comunicar remoción de autoridad del LLM
- Explicar nueva arquitectura de advisor pattern
- Documentar validación estricta de salidas
- Proporcionar evidencia de seguridad mejorada

**Desarrolladores**:
- Comunicar cambios en Decision Engine
- Explicar nueva interfaz (backward compatible)
- Documentar patrones de uso
- Proporcionar ejemplos de migración

**QA**:
- Comunicar importancia de tests de regresión
- Proporcionar criterios de aceptación de seguridad
- Documentar casos de prueba críticos
- Explicar procedimientos de rollback

### 10.2 Documentación Requerida

1. **Documentación de Arquitectura**:
   - Nuevo diagrama de Decision Engine con advisor pattern
   - Flujo de evaluación objetiva vs. LLM advice
   - Integración con componentes existentes

2. **Documentación de Seguridad**:
   - Análisis de riesgo del cambio
   - Evidencia de seguridad mejorada
   - Procedimientos de validación

3. **Documentación de API**:
   - Cambios en Decision Engine (backward compatible)
   - Nuevas interfaces para advisor pattern
   - Ejemplos de uso

4. **Documentación de Operaciones**:
   - Cómo monitorear desempeño del LLM advisor
   - Cómo interpretar métricas de incertidumbre
   - Procedimientos de troubleshooting

---

## 11. CRITERIOS DE ACEPTACIÓN

### 11.1 Criterios Técnicos

- [ ] Todos los unit tests pasan (>85% coverage)
- [ ] Todos los integration tests pasan
- [ ] Todos los security tests pasan
- [ ] Todos los performance tests pasan
- [ ] Todos los tests de regresión pasan
- [ ] Code review completado y aprobado por equipo de seguridad
- [ ] Sin dependencias nuevas agregadas

### 11.2 Criterios de Seguridad (CRÍTICOS)

- [ ] LLM no tiene autoridad en decisiones (100%)
- [ ] Evaluación objetiva siempre tiene prioridad (100%)
- [ ] Políticas siempre respetadas (100%)
- [ ] Acciones críticas protegidas (100%)
- [ ] Validación de salidas del LLM funciona (100%)
- [ ] Fallback a evaluación objetiva funciona (100%)

### 11.3 Criterios Funcionales

- [ ] Decision Engine funciona sin LLM advisor (100%)
- [ ] Decision Engine funciona con LLM advisor (100%)
- [ ] Objective Risk Assessor proporciona evaluaciones precisas (>95%)
- [ ] Uncertainty Tracker detecta discrepancias correctamente (>90%)
- [ ] LLM Output Validator valida correctamente (100%)

### 11.4 Criterios de Performance

- [ ] Decision Engine sin LLM <500ms (100%)
- [ ] Decision Engine con LLM <2s (100%)
- [ ] Objective Risk Assessor <1s (100%)
- [ ] No degradación significativa de performance (<10%)

### 11.5 Criterios de Calidad

- [ ] Documentación completa y precisa
- [ ] Código sigue convenciones del proyecto
- [ ] Sin warnings de linter
- [ ] Sin vulnerabilidades de seguridad introducidas
- [ ] Compatible con versiones existentes (backward compatible)

---

## 12. CONFIRMACIÓN REQUERIDA

Antes de proceder con la implementación de FASE 4, confirmar:

1. **¿Aprobar el plan de implementación propuesto?**
2. **¿Están de acuerdo con la estrategia de security testing?**
3. **¿Los criterios de aceptación de seguridad son apropiados?**
4. **¿Algún ajuste requerido antes de comenzar la implementación?**

---

## 13. CONSIDERACIONES ESPECIALES

### 13.1 Seguridad Adicional

**Consideración**: Validación continua de seguridad
- Implementar monitoreo continuo de decisiones del Decision Engine
- Alertas automáticas si se detectan patrones anómalos
- Auditoría enhanced de todas las decisiones críticas
- Revisión periódica de métricas de incertidumbre

### 13.2 Compatibilidad con FASE 2 y FASE 3

**Consideración**: Integración con cambios anteriores
- Decision Engine debe trabajar con datos de grounding de FASE 2
- Presentation Layer de FASE 3 debe filtrar detalles de incertidumbre apropiadamente
- Consistencia en mostrar información de objective vs. LLM assessment

### 13.3 Validación con Expertos

**Consideración**: Revisión por expertos en seguridad
- Hacer que expertos en seguridad revisen la lógica de ObjectiveRiskAssessor
- Validar heurísticas de detección de acciones peligrosas
- Revisar umbrales de riesgo y confirmación
- Aprobar criterios de seguridad antes de rollout

### 13.4 Beta Testing Prolongado

**Consideración**: Testing extendido por ser componente crítico
- Beta testing de 4 semanas (doble que otras fases)
- Monitoreo intensivo de decisiones en producción
- Análisis de cualquier discrepancia o anomalía
- Rollback inmediato si se detectan problemas

---

**DOCUMENTO FASE_4_ARCHITECTURE_IMPACT.md COMPLETADO**

Este documento detalla el impacto arquitectónico de implementar el Decision Engine Seguro en FASE 4, incluyendo archivos afectados, nivel de riesgo ALTO, estrategia de rollback y plan de testing con énfasis en seguridad y regresión.

**ESTADO**: Pendiente de aprobación antes de implementación.
