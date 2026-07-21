# FASE 3: PRESENTATION LAYER - ARCHITECTURE IMPACT

**Fecha**: 2025-01-17
**Fase**: 3 - Presentation Layer
**Prioridad**: CRÍTICA
**Duración Estimada**: 2 semanas
**Estado**: Pendiente de aprobación

---

## 1. PROPÓSITO

Implementar una capa de presentación independiente que separe completamente la experiencia de Modo Usuario y Modo Desarrollador, eliminando la exposición de detalles internos del sistema a los usuarios finales.

**Objetivo**: Los usuarios deben ver respuestas claras y simples, mientras los desarrolladores pueden acceder a detalles técnicos completos.

---

## 2. ARCHITECTURE IMPACT

### 2.1 Nuevo Componente: Presentation Layer

**Archivo**: `sentinel/core/presentation.py` (NUEVO)
**Responsabilidad**: 
- Filtrar datos según modo (usuario/desarrollador)
- Formatear errores para usuarios
- Ocultar detalles internos en modo usuario
- Proporcionar datos completos en modo desarrollador

**Dependencias**:
- Ninguna (self-contained)

**Interfaces Públicas**:
```python
class PresentationMode(Enum):
    USER = "user"
    DEVELOPER = "developer"

class VerbosityConfig:
    show_pipeline_stages: bool
    show_risk_scores: bool
    show_performance_metrics: bool
    show_internal_errors: bool
    show_model_details: bool
    show_policy_details: bool
    
    @classmethod
    def for_mode(cls, mode: PresentationMode) -> "VerbosityConfig"

class PresentationLayer:
    def __init__(self, mode: PresentationMode = PresentationMode.USER)
    def filter_execution_result(self, result: ExecutionResult) -> Dict[str, Any]
    def filter_error(self, error: str) -> str
    def filter_pipeline_data(self, pipeline: Dict[str, Any]) -> Dict[str, Any]
    def filter_advisory(self, advisory: AdvisoryReport) -> Dict[str, Any]
    def set_mode(self, mode: PresentationMode) -> None
```

### 2.2 Nuevo Componente: Mode Configuration

**Archivo**: `sentinel/core/mode_config.py` (NUEVO)
**Responsabilidad**: 
- Configuración centralizada de modo de Sentinel
- Persistencia de preferencias de modo
- API para cambiar modo en runtime

**Dependencias**:
- Sistema de configuración existente (opcional)

**Interfaces Públicas**:
```python
class SentinelMode(Enum):
    USER = "user"
    DEVELOPER = "developer"

class ModeConfig:
    def __init__(self)
    def get_mode(self) -> SentinelMode
    def set_mode(self, mode: SentinelMode) -> None
    def _load_from_config(self) -> SentinelMode
    def _save_to_config(self, mode: SentinelMode) -> None
```

### 2.3 Modificación: Sentinel Bridge

**Archivo**: `sidecar/modules/sentinel_bridge.py`
**Cambio**: Envolver respuestas con Presentation Layer

**Cambio Específico**:
```python
# EN __init__ o setup
from sentinel.core.presentation import PresentationLayer, PresentationMode
from sentinel.core.mode_config import ModeConfig, SentinelMode

self._mode_config = ModeConfig()
self._presentation = PresentationLayer(mode=self._mode_config.get_mode())

# EN endpoints que retornan ExecutionResult
@router.post("/sentinel/process")
async def process_conversation(body: dict, request: Request):
    # ... código existente ...
    result = await orchestrator.process(...)
    
    # NUEVO: Filtrar según modo
    filtered_result = {
        "approved": result.approved,
        "summary": self._presentation.generate_user_summary(result),
        "user_facing_error": self._presentation.filter_error(result.error or ""),
        "requires_action": result.tool_result.requires_confirmation if result.tool_result else False,
    }
    
    # En modo desarrollador, incluir detalles completos
    if self._mode_config.get_mode() == SentinelMode.DEVELOPER:
        filtered_result["full_result"] = result.to_dict()
    
    return filtered_result
```

**Integración**:
- Envolver todas las respuestas que exponen detalles internos
- Detectar modo desde configuración
- Filtrar campos según VerbosityConfig

### 2.4 Modificación: Workbench (Frontend)

**Archivo**: `src/components/Workbench/Workbench.tsx`
**Cambio**: Agregar selector de modo y UI diferenciada

**Cambio Específico**:
```typescript
// NUEVO: Estado para modo
const [presentationMode, setPresentationMode] = useState<"user" | "developer">("user");

// NUEVO: Selector de modo
<div className="mode-selector">
  <button 
    className={presentationMode === "user" ? "active" : ""}
    onClick={() => setPresentationMode("user")}
  >
    Usuario
  </button>
  <button 
    className={presentationMode === "developer" ? "active" : ""}
    onClick={() => setPresentationMode("developer")}
  >
    Desarrollador
  </button>
</div>

// NUEVO: Renderizado condicional de detalles
{presentationMode === "developer" && (
  <DeveloperDetails 
    pipeline={pipeline} 
    metrics={metrics} 
    riskScores={riskScores} 
  />
)}

// CAMBIO: Llamadas a API con modo
const response = await api.sentinel.process(message, { mode: presentationMode });
```

**Integración**:
- Agregar selector de modo en UI
- Condicionalmente renderizar detalles internos
- Pasar modo a API calls

### 2.5 Modificación: API Client

**Archivo**: `src/api.ts`
**Cambio**: Agregar soporte para modo en llamadas API

**Cambio Específico**:
```typescript
// NUEVO: Campo de modo en llamadas
export const api = {
  sentinel: {
    process: async (message: string, options?: { mode?: "user" | "developer" }) => {
      return postJSON(`${BASE}/sentinel/process`, {
        message,
        mode: options?.mode || "user"
      });
    },
    // ... otros métodos ...
  },
  
  // NUEVO: Endpoint para cambiar modo
  setPresentationMode: async (mode: "user" | "developer") => {
    return postJSON(`${BASE}/sentinel/mode`, { mode });
  },
  
  getPresentationMode: async () => {
    return fetchJSON<{ mode: "user" | "developer" }>(`${BASE}/sentinel/mode`);
  }
};
```

### 2.6 Nuevo Endpoint API

**Archivo**: `sidecar/modules/sentinel_bridge.py`
**Cambio**: Agregar endpoint para gestión de modo

**Cambio Específico**:
```python
# NUEVO: Endpoint para obtener modo actual
@router.get("/sentinel/mode")
async def get_mode(request: Request):
    return {"mode": self._mode_config.get_mode().value}

# NUEVO: Endpoint para cambiar modo
@router.post("/sentinel/mode")
async def set_mode(body: dict, request: Request):
    from modules.auth import require_admin_identity
    
    # Solo admin puede cambiar a modo desarrollador
    identity = request_identity(request)
    if body.get("mode") == "developer" and identity.level != "admin":
        raise HTTPException(status_code=403, detail="Solo admin puede cambiar a modo desarrollador")
    
    mode = SentinelMode(body.get("mode", "user"))
    self._mode_config.set_mode(mode)
    self._presentation.set_mode(mode)
    return {"mode": mode.value, "status": "updated"}
```

---

## 3. FILES AFFECTED

### 3.1 Nuevos Archivos

1. **`sentinel/core/presentation.py`** (NUEVO)
   - ~400 líneas estimadas
   - Componente principal de Presentation Layer
   - Sin dependencias críticas

2. **`sentinel/core/mode_config.py`** (NUEVO)
   - ~150 líneas estimadas
   - Configuración centralizada de modo
   - Depende de: sistema de configuración existente (opcional)

3. **`tests/test_presentation.py`** (NUEVO)
   - ~250 líneas estimadas
   - Tests exhaustivos de Presentation Layer
   - Depende de: presentation.py

4. **`tests/test_mode_config.py`** (NUEVO)
   - ~100 líneas estimadas
   - Tests de configuración de modo
   - Depende de: mode_config.py

### 3.2 Archivos Modificados

1. **`sidecar/modules/sentinel_bridge.py`**
   - Cambio: Envolver respuestas con Presentation Layer
   - Cambio: Agregar endpoint para gestión de modo
   - Líneas afectadas: ~50-70
   - Riesgo: MEDIO (cambios en capa de API)

2. **`src/components/Workbench/Workbench.tsx`**
   - Cambio: Agregar selector de modo
   - Cambio: Renderizado condicional de detalles
   - Cambio: Llamadas a API con modo
   - Líneas afectadas: ~30-50
   - Riesgo: MEDIO (cambios en UI)

3. **`src/api.ts`**
   - Cambio: Agregar soporte para modo en llamadas API
   - Cambio: Agregar endpoints para gestión de modo
   - Líneas afectadas: ~20-30
   - Riesgo: BAJO (cambios aditivos en cliente API)

### 3.3 Archivos Sin Cambios

Todos los demás archivos permanecen sin cambios para mantener compatibilidad con el backend de Sentinel.

---

## 4. RISK LEVEL

### 4.1 Riesgo General: MEDIO

**Justificación**:
- Componente nuevo (PresentationLayer) no afecta lógica de negocio
- Cambios en UI son principalmente aditivos
- Modo usuario es el default (comportamiento conservador)
- Puede deshabilitarse mediante configuración
- No cambia interfaces principales de Orchestrator

### 4.2 Riesgos Específicos

#### RIESGO 1: Información Importante Oculta en Modo Usuario
**Severidad**: MEDIA
**Probabilidad**: BAJA
**Impacto**: Usuarios pueden no ver información crítica
**Mitigación**:
- VerbosityConfig conservadora por defecto
- Incluir siempre información crítica (errores, confirmaciones requeridas)
- Permitir override por usuario
- Logging extenso para validar qué se filtra

#### RIESGO 2: Inconsistencia entre Modos
**Severidad**: MEDIA
**Probabilidad**: BAJA
**Impacto**: Comportamiento diferente puede confundir usuarios
**Mitigación**:
- Documentación clara de diferencias entre modos
- Indicador visual claro del modo actual
- Tests para asegurar consistencia de lógica subyacente
- Transición suave entre modos

#### RIESGO 3: Performance Impact por Filtrado
**Severidad**: BAJA
**Probabilidad**: BAJA
**Impacto**: Filtrado puede agregar latencia
**Mitigación**:
- Filtrado es operación ligera (manipulación de dicts)
- No hay llamadas a sistema en filtrado
- Métricas de performance en tests
- Optimización si es necesario

#### RIESGO 4: UI Changes Afectan Usabilidad
**Severidad**: MEDIA
**Probabilidad**: MEDIA
**Impacto**: Cambios en Workbench pueden afectar UX
**Mitigación**:
- Mantener layout existente como default
- Selector de modo no intrusivo
- Beta testing con usuarios reales
- Rollback fácil de cambios UI

#### RIESGO 5: Seguridad de Modo Desarrollador
**Severidad**: MEDIA
**Probabilidad**: BAJA
**Impacto**: Modo desarrollador puede exponer información sensible
**Mitigación**:
- Requerir permisos de admin para modo desarrollador
- Logging de accesos a modo desarrollador
- Documentación clara de riesgos
- Auditoría de cambios de modo

---

## 5. ROLLBACK STRATEGY

### 5.1 Rollback Plan A: Forzar Modo Usuario

**Trigger**: Problemas con filtrado o inconsistencias
**Acción**:
```python
# En configuración
SENTINEL_DEFAULT_MODE = "user"
SENTINEL_FORCE_USER_MODE = True  # Forzar modo usuario

# En ModeConfig
def get_mode(self) -> SentinelMode:
    if self._config.get("force_user_mode", False):
        return SentinelMode.USER
    return self._load_from_config()
```

**Tiempo**: <5 minutos
**Impacto**: Todos los usuarios ven modo usuario
**Riesgo**: Ninguno

### 5.2 Rollback Plan B: Deshabilitar Presentation Layer

**Trigger**: Problemas severos con filtrado
**Acción**:
```python
# En SentinelBridge
self._presentation = None  # Deshabilitar

# En endpoints
if self._presentation:
    filtered_result = self._presentation.filter_execution_result(result)
else:
    filtered_result = result.to_dict()  # Comportamiento anterior
```

**Tiempo**: ~10 minutos
**Impacto**: Vuelve a comportamiento anterior (exposición completa)
**Riesgo**: Bajo

### 5.3 Rollback Plan C: Revertir Cambios en UI

**Trigger**: Problemas severos de UX
**Acción**:
- Revertir cambios en `Workbench.tsx`
- Revertir cambios en `api.ts`
- Mantener backend con Presentation Layer (puede ser útil futuro)

**Tiempo**: ~20 minutos
**Impacto**: UI vuelve a comportamiento anterior
**Riesgo**: Bajo

### 5.4 Rollback Plan D: Rollback Completo

**Trigger**: Problemas críticos que requieren limpieza total
**Acción**:
- Revertir todos los cambios en frontend
- Revertir todos los cambios en backend
- Eliminar archivos nuevos
- Restaurar versión anterior de repositorio

**Tiempo**: ~30 minutos
**Impacto**: Vuelve a estado anterior exacto
**Riesgo**: Ninguno

---

## 6. TESTING PLAN

### 6.1 Unit Tests (70%)

#### Tests para PresentationLayer
```python
class TestPresentationLayer:
    def test_user_mode_hides_pipeline_stages(self):
        """Verifica que modo usuario oculta etapas del pipeline"""
        layer = PresentationLayer(mode=PresentationMode.USER)
        result = ExecutionResult(...)  # resultado completo con detalles
        
        filtered = layer.filter_execution_result(result)
        
        assert "pipeline_stages" not in filtered
        assert "risk_score" not in filtered
        assert "internal_metrics" not in filtered
    
    def test_user_mode_shows_user_facing_info(self):
        """Verifica que modo usuario muestra información relevante"""
        layer = PresentationLayer(mode=PresentationMode.USER)
        result = ExecutionResult(approved=True, error=None)
        
        filtered = layer.filter_execution_result(result)
        
        assert filtered["approved"] == True
        assert "summary" in filtered
        assert "user_facing_error" in filtered
    
    def test_developer_mode_shows_all_details(self):
        """Verifica que modo desarrollador muestra todo"""
        layer = PresentationLayer(mode=PresentationMode.DEVELOPER)
        result = ExecutionResult(...)  # resultado completo
        
        filtered = layer.filter_execution_result(result)
        
        assert "pipeline_stages" in filtered
        assert "risk_score" in filtered
        assert "internal_metrics" in filtered
    
    def test_error_messages_are_user_friendly(self):
        """Verifica que errores son amigables para usuarios"""
        layer = PresentationLayer(mode=PresentationMode.USER)
        
        technical_error = "ConnectionError: Failed to connect to model router: timeout after 30s"
        user_error = layer.filter_error(technical_error)
        
        assert "ConnectionError" not in user_error
        assert "timeout" not in user_error.lower()
        assert len(user_error) < 200  # Mensaje conciso
    
    def test_developer_mode_preserves_technical_errors(self):
        """Verifica que modo desarrollador preserva errores técnicos"""
        layer = PresentationLayer(mode=PresentationMode.DEVELOPER)
        
        technical_error = "ConnectionError: Failed to connect to model router: timeout after 30s"
        dev_error = layer.filter_error(technical_error)
        
        assert technical_error in dev_error
    
    def test_mode_switching_works(self):
        """Verifica que cambio de modo funciona"""
        layer = PresentationLayer(mode=PresentationMode.USER)
        
        layer.set_mode(PresentationMode.DEVELOPER)
        assert layer._mode == PresentationMode.DEVELOPER
        
        layer.set_mode(PresentationMode.USER)
        assert layer._mode == PresentationMode.USER
```

#### Tests para ModeConfig
```python
class TestModeConfig:
    def test_default_mode_is_user(self):
        """Verifica que modo default es usuario"""
        config = ModeConfig()
        assert config.get_mode() == SentinelMode.USER
    
    def test_set_mode_persists(self):
        """Verifica que cambio de modo persiste"""
        config = ModeConfig()
        config.set_mode(SentinelMode.DEVELOPER)
        
        config2 = ModeConfig()
        assert config2.get_mode() == SentinelMode.DEVELOPER
    
    def test_invalid_mode_defaults_to_user(self):
        """Verifica que modo inválido default a usuario"""
        config = ModeConfig()
        config._config = {"mode": "invalid"}
        
        assert config.get_mode() == SentinelMode.USER
    
    def test_mode_validation(self):
        """Verifica validación de modo"""
        config = ModeConfig()
        
        # Debe aceptar modos válidos
        config.set_mode(SentinelMode.USER)
        config.set_mode(SentinelMode.DEVELOPER)
        
        # No debe lanzar excepción con modos válidos
```

#### Tests para VerbosityConfig
```python
class TestVerbosityConfig:
    def test_user_mode_disables_internal_details(self):
        """Verifica que modo usuario deshabilita detalles internos"""
        config = VerbosityConfig.for_mode(PresentationMode.USER)
        
        assert config.show_pipeline_stages == False
        assert config.show_risk_scores == False
        assert config.show_performance_metrics == False
        assert config.show_internal_errors == False
    
    def test_developer_mode_enables_internal_details(self):
        """Verifica que modo desarrollador habilita detalles internos"""
        config = VerbosityConfig.for_mode(PresentationMode.DEVELOPER)
        
        assert config.show_pipeline_stages == True
        assert config.show_risk_scores == True
        assert config.show_performance_metrics == True
        assert config.show_internal_errors == True
```

### 6.2 Integration Tests (20%)

#### Tests de Integración con SentinelBridge
```python
class TestSentinelBridgePresentationIntegration:
    async def test_bridge_filters_user_responses(self):
        """Verifica que SentinelBridge filtra respuestas en modo usuario"""
        bridge = create_test_bridge(mode=PresentationMode.USER)
        result = await bridge.process({"message": "test"})
        
        assert "pipeline_stages" not in result
        assert "risk_score" not in result
    
    async def test_bridge_shows_developer_details(self):
        """Verifica que SentinelBridge muestra detalles en modo desarrollador"""
        bridge = create_test_bridge(mode=PresentationMode.DEVELOPER)
        result = await bridge.process({"message": "test"})
        
        assert "full_result" in result
        assert "pipeline_stages" in result["full_result"]
    
    async def test_mode_endpoint_works(self):
        """Verifica que endpoint de modo funciona"""
        bridge = create_test_bridge()
        
        # Obtener modo actual
        response = await client.get("/sentinel/mode")
        assert response["mode"] == "user"
        
        # Cambiar a desarrollador (como admin)
        await client.post("/sentinel/mode", {"mode": "developer"}, admin=True)
        
        # Verificar cambio
        response = await client.get("/sentinel/mode")
        assert response["mode"] == "developer"
    
    async def test_non_admin_cannot_switch_to_developer(self):
        """Verifica que no-admin no puede cambiar a modo desarrollador"""
        bridge = create_test_bridge()
        
        response = await client.post("/sentinel/mode", {"mode": "developer"}, admin=False)
        assert response.status_code == 403
```

#### Tests de Integración con Frontend
```python
class TestWorkbenchPresentationIntegration:
    def test_mode_selector_renders(self):
        """Verifica que selector de modo se renderiza"""
        render(<Workbench />)
        assert screen.getByRole("button", { name: "Usuario" }).exists()
        assert screen.getByRole("button", { name: "Desarrollador" }).exists()
    
    def test_user_mode_hides_developer_details(self):
        """Verifica que modo usuario oculta detalles en UI"""
        render(<Workbench mode="user" />)
        
        assert screen.queryByTestId("developer-details") == null
        assert screen.queryByTestId("pipeline-stages") == null
    
    def test_developer_mode_shows_details(self):
        """Verifica que modo desarrollador muestra detalles en UI"""
        render(<Workbench mode="developer" />)
        
        assert screen.getByTestId("developer-details").exists()
        assert screen.getByTestId("pipeline-stages").exists()
    
    def test_mode_switching_updates_ui(self):
        """Verifica que cambio de modo actualiza UI"""
        const { rerender } = render(<Workbench mode="user" />)
        
        assert screen.queryByTestId("developer-details") == null
        
        rerender(<Workbench mode="developer" />)
        
        assert screen.getByTestId("developer-details").exists()
```

### 6.3 E2E Tests (10%)

#### Tests de Flujo Completo
```python
class TestPresentationE2E:
    async def test_user_sees_clean_interface(self):
        """Verifica que usuario ve interfaz limpia"""
        # Iniciar aplicación en modo usuario
        await launch_app(mode="user")
        
        # Enviar query
        await send_message("¿Cuánta CPU tengo?")
        
        # Verificar que no se muestran detalles técnicos
        assert not await is_visible("pipeline-stages")
        assert not await is_visible("risk-score")
        assert not await is_visible("internal-metrics")
        
        # Verificar que se muestra información útil
        assert await is_visible("cpu-usage")
        assert await is_visible("user-summary")
    
    async def test_developer_sees_full_details(self):
        """Verifica que desarrollador ve detalles completos"""
        # Iniciar aplicación en modo desarrollador
        await launch_app(mode="developer")
        
        # Enviar query
        await send_message("¿Cuánta CPU tengo?")
        
        # Verificar que se muestran detalles técnicos
        assert await is_visible("pipeline-stages")
        assert await is_visible("risk-score")
        assert await is_visible("internal-metrics")
    
    async def test_mode_persistence(self):
        """Verifica que modo persiste entre sesiones"""
        # Cambiar a modo desarrollador
        await set_mode("developer")
        
        # Reiniciar aplicación
        await restart_app()
        
        # Verificar que modo se mantuvo
        assert await get_current_mode() == "developer"
```

### 6.4 Usability Tests

```python
class TestPresentationUsability:
    async def test_user_mode_is_intuitive(self):
        """Verifica que modo usuario es intuitivo"""
        # Test con usuarios reales
        feedback = await user_test(group="novice_users", mode="user")
        
        assert feedback["confusion_rate"] < 0.1
        assert feedback["task_completion_rate"] > 0.9
    
    async def test_developer_mode_is_useful(self):
        """Verifica que modo desarrollador es útil"""
        # Test con desarrolladores
        feedback = await user_test(group="developers", mode="developer")
        
        assert feedback["information_sufficiency"] > 0.9
        assert feedback["debugging_helpfulness"] > 0.8
```

### 6.5 Security Tests

```python
class TestPresentationSecurity:
    async def test_non_admin_cannot_access_developer_mode(self):
        """Verifica que no-admin no puede acceder a modo desarrollador"""
        user = create_test_user(role="user")
        
        response = await api.set_presentation_mode("developer", auth=user)
        assert response.status_code == 403
        
        # Verificar que modo no cambió
        current_mode = await api.get_presentation_mode(auth=user)
        assert current_mode["mode"] == "user"
    
    async def test_developer_mode_access_is_logged(self):
        """Verifica que acceso a modo desarrollador se loguea"""
        admin = create_test_user(role="admin")
        
        await api.set_presentation_mode("developer", auth=admin)
        
        # Verificar que se registró en auditoría
        audit_log = await get_audit_log()
        assert any(
            entry["action"] == "mode_change" and 
            entry["details"]["new_mode"] == "developer" and
            entry["user"] == admin.id
            for entry in audit_log
        )
```

### 6.6 Coverage Goal

- **PresentationLayer**: >90% coverage (componente crítico nuevo)
- **ModeConfig**: >85% coverage
- **VerbosityConfig**: >85% coverage
- **Integración**: >80% coverage
- **Total FASE 3**: >80% coverage

---

## 7. IMPLEMENTACIÓN DETALLADA

### 7.1 Semana 1: Core Presentation Layer

**Objetivo**: Implementar funcionalidad básica de Presentation Layer

**Tareas**:
1. Crear `sentinel/core/presentation.py` con estructura básica
2. Implementar `PresentationMode` enum
3. Implementar `VerbosityConfig` con configuraciones por modo
4. Implementar `PresentationLayer.filter_execution_result()`
5. Implementar `PresentationLayer.filter_error()`
6. Unit tests básicos

**Entregables**:
- `sentinel/core/presentation.py` funcional
- Tests unitarios pasando
- Documentación básica

### 7.2 Semana 2: Modo Configuración e Integración

**Objetivo**: Implementar configuración de modo e integración completa

**Tareas**:
1. Crear `sentinel/core/mode_config.py`
2. Implementar persistencia de modo
3. Integrar en `SentinelBridge`
4. Agregar endpoints API para gestión de modo
5. Modificar `Workbench.tsx` para selector de modo
6. Modificar `api.ts` para soporte de modo
7. Integration tests
8. E2E tests
9. Security tests
10. Documentación completa

**Entregables**:
- `sentinel/core/mode_config.py` funcional
- Integración completa en backend y frontend
- Todos los tests pasando
- Documentación completa
- Listo para beta testing

---

## 8. DEPENDENCIAS Y REQUISITOS

### 8.1 Dependencias Existentes (Nuevas)

**Ninguna** - Presentation Layer usa solo dependencias existentes:
- `enum` (standard library)
- `typing` (standard library)
- `dataclasses` (standard library)
- Sistema de configuración existente (opcional)

### 8.2 Dependencias de Componentes

**PresentationLayer depende de**:
- Ninguna (self-contained)

**ModeConfig depende de**:
- Sistema de configuración existente (opcional, puede usar JSON local)

### 8.3 Requisitos de Sistema

**CPU**: Sin impacto adicional
**RAM**: ~10MB adicional para configuración
**Disco**: ~2MB para código nuevo
**Red**: Sin impacto adicional

### 8.4 Requisitos de Frontend

**React**: Versión existente (sin cambios)
**TypeScript**: Versión existente (sin cambios)
**Dependencies**: Ninguna nueva requerida

---

## 9. MÉTRICAS DE ÉXITO

### 9.1 Métricas Técnicas

- **Coverage**: >80% para código nuevo
- **Performance**: <50ms para operaciones de filtrado
- **Mode Switch Time**: <100ms para cambio de modo
- **API Latency Impact**: <10% incremento en latencia de API

### 9.2 Métricas de Funcionalidad

- **Filtering Accuracy**: 100% de detalles internos ocultos en modo usuario
- **Information Preservation**: 100% de información crítica visible en modo usuario
- **Developer Mode Completeness**: 100% de detalles disponibles en modo desarrollador
- **Mode Persistence**: 100% de cambios de modo persisten correctamente

### 9.3 Métricas de UX

- **User Confusion Rate**: <10% (usuarios confundidos por modo)
- **Task Completion Rate**: >90% (tareas completadas exitosamente)
- **Developer Satisfaction**: >4/5 (satisfacción de desarrolladores)
- **Switch Success Rate**: >95% (cambios de modo exitosos)

### 9.4 Métricas de Seguridad

- **Unauthorized Access Attempts**: 0 intentos no autorizados exitosos
- **Audit Log Completeness**: 100% de cambios de modo registrados
- **Permission Enforcement**: 100% de restricciones de modo aplicadas

---

## 10. PLAN DE COMUNICACIÓN

### 10.1 Stakeholders

**Usuarios Finales**:
- Comunicar nueva interfaz simplificada
- Explicar beneficios de modo usuario
- Documentar cómo acceder a modo desarrollador si es necesario

**Desarrolladores**:
- Comunicar disponibilidad de modo desarrollador
- Documentar detalles técnicos disponibles
- Explicar requisitos de permisos

**QA**:
- Proporcionar criterios de aceptación UX
- Comunicar casos de prueba de usabilidad
- Documentar escenarios de seguridad

### 10.2 Documentación Requerida

1. **Documentación de Usuario**:
   - Guía de modo usuario vs. desarrollador
   - Cómo cambiar entre modos
   - Qué información está disponible en cada modo
   - Solución de problemas

2. **Documentación de Desarrollador**:
   - Detalles técnicos disponibles en modo desarrollador
   - Cómo usar modo desarrollador para debugging
   - Requisitos de permisos
   - API para gestión de modo

3. **Documentación de API**:
   - Nuevos endpoints para modo
   - Cambios en respuestas existentes
   - Ejemplos de uso

4. **Documentación de Arquitectura**:
   - Diagrama de Presentation Layer
   - Flujo de filtrado de datos
   - Integración con componentes existentes

---

## 11. CRITERIOS DE ACEPTACIÓN

### 11.1 Criterios Técnicos

- [ ] Todos los unit tests pasan (>80% coverage)
- [ ] Todos los integration tests pasan
- [ ] Todos los E2E tests pasan
- [ ] Todos los security tests pasan
- [ ] Performance tests cumplen objetivos (<50ms filtrado)
- [ ] Code review completado y aprobado
- [ ] Sin dependencias nuevas agregadas

### 11.2 Criterios Funcionales

- [ ] Modo usuario oculta 100% de detalles internos
- [ ] Modo usuario muestra 100% de información crítica
- [ ] Modo desarrollador muestra 100% de detalles técnicos
- [ ] Cambio de modo funciona correctamente
- [ ] Persistencia de modo funciona correctamente
- [ ] Restricciones de permisos funcionan correctamente

### 11.3 Criterios de UX

- [ ] Selector de modo es intuitivo
- [ ] Modo usuario es más simple que interfaz actual
- [ ] Modo desarrollador proporciona información útil
- [ ] Transición entre modos es suave
- [ ] Indicador visual de modo es claro

### 11.4 Criterios de Seguridad

- [ ] Solo admin puede cambiar a modo desarrollador
- [ ] Todos los cambios de modo se auditan
- [ ] No hay exposición de información sensible en modo usuario
- [ ] No hay escalación de privilegios posible

### 11.5 Criterios de Calidad

- [ ] Documentación completa y precisa
- [ ] Código sigue convenciones del proyecto
- [ ] Sin warnings de linter
- [ ] Sin vulnerabilidades de seguridad introducidas
- [ ] Compatible con versiones existentes

---

## 12. CONFIRMACIÓN REQUERIDA

Antes de proceder con la implementación de FASE 3, confirmar:

1. **¿Aprobar el plan de implementación propuesto?**
2. **¿Están de acuerdo con la estrategia de testing UX?**
3. **¿Los criterios de aceptación son apropiados?**
4. **¿Algún ajuste requerido antes de comenzar la implementación?**

---

## 13. CONSIDERACIONES ESPECIALES

### 13.1 Accesibilidad

**Consideración**: Asegurar que selector de modo es accesible
- Implementar soporte para lectores de pantalla
- Usar colores con alto contraste
- Proporcionar atajos de teclado para cambio de modo

### 13.1.1 Internacionalización

**Consideración**: Soportar múltiples idiomas
- Etiquetas de modo en múltiples idiomas
- Mensajes de error localizados
- Documentación en múltiples idiomas

### 13.1.2 Performance

**Consideración**: Minimizar impacto de filtrado
- Filtrado debe ser <50ms
- No debe haber llamadas bloqueantes
- Caché de configuración de modo

### 13.1.3 Compatibilidad con FASE 2

**Consideración**: Integrar con Grounding Engine de FASE 2
- Presentation Layer debe trabajar con datos de grounding
- Filtrado no debe interferir con metadata de grounding
- Consistencia en mostrar información de grounded vs. non-grounded

---

**DOCUMENTO FASE_3_ARCHITECTURE_IMPACT.md COMPLETADO**

Este documento detalla el impacto arquitectónico de implementar el Presentation Layer en FASE 3, incluyendo archivos afectados, nivel de riesgo, estrategia de rollback y plan de testing con énfasis en UX y seguridad.

**ESTADO**: Pendiente de aprobación antes de implementación.
