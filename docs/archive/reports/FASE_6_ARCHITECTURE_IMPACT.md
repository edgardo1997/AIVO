# FASE 6: HARDWARE INTELLIGENCE - ARCHITECTURE IMPACT

**Fecha**: 2025-01-17
**Fase**: 6 - Hardware Intelligence
**Prioridad**: ALTA
**Duración Estimada**: 2 semanas
**Estado**: Pendiente de aprobación

---

## 1. PROPÓSITO

Implementar un sistema de análisis de hardware y gestión de capacidades de modelos que permita a Sentinel adaptarse automáticamente a las capacidades del dispositivo, seleccionando modelos óptimos según CPU, GPU, RAM, VRAM, NPU y otros recursos disponibles.

**Objetivo**: Sentinel debe conocer el hardware del dispositivo y decidir "Este modelo es adecuado para esta máquina" en lugar de usar siempre el mismo modelo sin considerar capacidad.

---

## 2. ARCHITECTURE IMPACT

### 2.1 Nuevo Componente: Hardware Profiler

**Archivo**: `sentinel/core/hardware_profiler.py` (NUEVO)
**Responsabilidad**: 
- Analizar hardware del dispositivo
- Generar perfil de capacidad del dispositivo
- Detectar CPU, GPU, NPU, RAM, VRAM
- Analizar almacenamiento y batería
- Mantener caché de perfil por sesión

**Dependencias**:
- Ninguna (usa sistema operativo directamente)

**Interfaces Públicas**:
```python
@dataclass
class HardwareProfile:
    """Perfil de hardware del dispositivo"""
    cpu_cores: int
    cpu_threads: int
    cpu_frequency_mhz: Optional[float]
    cpu_architecture: str
    ram_gb: float
    ram_available_gb: float
    gpu_available: bool
    gpu_name: Optional[str]
    gpu_vram_gb: Optional[float]
    gpu_architecture: Optional[str]
    npu_available: bool
    npu_name: Optional[str]
    npu_capability: Optional[str]
    disk_available_gb: float
    disk_total_gb: float
    os_name: str
    os_version: str
    os_architecture: str
    battery_available: bool
    battery_percent: Optional[int]
    profile_date: str
    confidence: float

class HardwareProfiler:
    def __init__(self)
    async def profile(self) -> HardwareProfile
    def get_cached_profile(self) -> Optional[HardwareProfile]
    def invalidate_cache(self) -> None
    def _detect_cpu(self) -> Dict[str, Any]
    def _detect_ram(self) -> Dict[str, Any]
    def _detect_gpu(self) -> Dict[str, Any]
    def _detect_npu(self) -> Dict[str, Any]
    def _detect_storage(self) -> Dict[str, Any]
    def _detect_battery(self) -> Dict[str, Any]
    def _detect_os(self) -> Dict[str, Any]
```

### 2.2 Nuevo Componente: Model Capability Manager

**Archivo**: `sentinel/core/model_capability.py` (NUEVO)
**Responsabilidad**: 
- Gestionar capacidades de modelos según hardware
- Recomendar modelo óptimo según hardware y tarea
- Optimizar configuración de modelos según recursos
- Mantener base de datos de capacidades de modelos

**Dependencias**:
- HardwareProfiler (para análisis de hardware)
- ModelRouter (para interacción con modelos)

**Interfaces Públicas**:
```python
@dataclass
class ModelCapability:
    """Capacidad de un modelo específico"""
    model_id: str
    provider_id: str
    model_name: str
    min_ram_gb: float
    min_vram_gb: Optional[float]
    recommended_hardware: List[str]  # ['cpu', 'gpu', 'npu']
    context_window: int
    acceleration_support: List[str]  # ['cpu', 'gpu', 'npu']
    optimal_task_types: List[TaskType]
    estimated_tokens_per_second: Dict[str, float]  # {'cpu': 10, 'gpu': 100}
    quantization_support: List[str]  # ['fp32', 'fp16', 'int8', 'int4']
    size_gb: Optional[float]
    description: str

@dataclass
class ModelRecommendation:
    """Recomendación de modelo para una tarea"""
    model_capability: ModelCapability
    hardware_suitable: bool
    confidence: float
    reasoning: str
    optimization_config: Dict[str, Any]
    fallback_models: List[ModelCapability]

class ModelCapabilityManager:
    def __init__(self, hardware: HardwareProfile)
    async def recommend_model(self, task_type: TaskType, requirements: Dict[str, Any]) -> Optional[ModelRecommendation]
    async def optimize_model_config(self, model: ModelCapability) -> Dict[str, Any]
    def can_run_model(self, model: ModelCapability) -> bool
    def get_compatible_models(self, task_type: TaskType) -> List[ModelCapability]
    def load_model_capabilities(self) -> None
    def _validate_hardware_match(self, hardware: HardwareProfile, model: ModelCapability) -> bool
    def _calculate_confidence(self, hardware: HardwareProfile, model: ModelCapability) -> float
```

### 2.3 Modificación: Model Router

**Archivo**: `sentinel/core/model_router.py`
**Cambio**: Integrar con Model Capability Manager para selección inteligente

**Cambio Específico**:
```python
# ANTES
class ModelRouter:
    def __init__(self, ...):
        self._providers: Dict[str, ProviderSpec] = {}
        self._strategy: str = "priority"
        # ... código existente ...
    
    def select(self, task_type: TaskType, context: Optional[Dict[str, Any]] = None) -> RouterDecision:
        candidates = [p for p in self._providers.values() if task_type in p.task_types]
        # ... lógica de selección existente ...

# DESPUÉS
class ModelRouter:
    def __init__(self, ...):
        self._providers: Dict[str, ProviderSpec] = {}
        self._strategy: str = "priority"
        self._capability_manager = None  # NUEVO
        self._hardware_profile = None  # NUEVO
        # ... código existente ...
    
    def set_capability_manager(self, manager: ModelCapabilityManager) -> None:
        """Configura el manager de capacidades"""
        self._capability_manager = manager
    
    def set_hardware_profile(self, profile: HardwareProfile) -> None:
        """Configura el perfil de hardware"""
        self._hardware_profile = profile
    
    def select(self, task_type: TaskType, context: Optional[Dict[str, Any]] = None) -> RouterDecision:
        # NUEVO: Si hay capability manager, usar selección inteligente
        if self._capability_manager and self._hardware_profile:
            try:
                recommendation = await self._capability_manager.recommend_model(
                    task_type, 
                    context or {}
                )
                if recommendation and recommendation.hardware_suitable:
                    # Usar modelo recomendado
                    provider = self._providers.get(recommendation.model_capability.provider_id)
                    if provider:
                        return RouterDecision(
                            provider_id=provider.id,
                            model=provider.default_model,
                            task_type=task_type,
                            strategy="hardware_aware",
                            reason=recommendation.reasoning,
                            selection_trace={
                                "hardware_profile": self._hardware_profile.to_dict(),
                                "recommendation": recommendation.to_dict(),
                            }
                        )
            except Exception as e:
                logger.warning("Hardware-aware selection failed, falling back to default: %s", e)
        
        # FALLBACK: Usar lógica existente
        candidates = [p for p in self._providers.values() if task_type in p.task_types]
        # ... lógica de selección existente ...
```

**Integración**:
- ModelRouter puede usar selección inteligente cuando está disponible
- Fallback a comportamiento existente si capability manager falla
- No rompe compatibilidad con lógica existente

### 2.4 Modificación: Provider Spec

**Archivo**: `sentinel/core/model_router.py`
**Cambio**: Extender ProviderSpec con requisitos de hardware

**Cambio Específico**:
```python
# ANTES
@dataclass
class ProviderSpec:
    id: str
    name: str
    task_types: List[TaskType]
    requires_key: bool = True
    is_local: bool = False
    default_model: str = ""
    priority: int = 10
    config: Dict[str, Any] = field(default_factory=dict)
    fallback_chain: List[str] = field(default_factory=list)

# DESPUÉS
@dataclass
class ProviderSpec:
    id: str
    name: str
    task_types: List[TaskType]
    requires_key: bool = True
    is_local: bool = False
    default_model: str = ""
    priority: int = 10
    config: Dict[str, Any] = field(default_factory=dict)
    fallback_chain: List[str] = field(default_factory=list)
    # NUEVOS CAMPOS
    min_ram_gb: Optional[float] = None
    min_vram_gb: Optional[float] = None
    recommended_hardware: List[str] = field(default_factory=list)
    context_window: Optional[int] = None
    acceleration_support: List[str] = field(default_factory=list)
    quantization_support: List[str] = field(default_factory=list)
    size_gb: Optional[float] = None
```

**Integración**:
- Campos nuevos son opcionales (default None/list vacío)
- Compatibilidad con providers existentes
- Información adicional para Model Capability Manager

### 2.5 Modificación: Orchestrator

**Archivo**: `sentinel/core/orchestrator.py`
**Cambio**: Inicializar Hardware Profiler y configurar Model Router

**Cambio Específico**:
```python
# EN __init__
def __init__(self, ...):
    # ... código existente ...
    
    # NUEVO: Inicializar Hardware Profiler
    self._hardware_profiler = HardwareProfiler()
    
    # NUEVO: Perfilar hardware al iniciar
    try:
        self._hardware_profile = asyncio.create_task(self._profile_hardware_on_startup())
    except Exception as e:
        logger.warning("Hardware profiling failed: %s", e)
        self._hardware_profile = None

async def _profile_hardware_on_startup(self) -> None:
    """Perfila hardware en background al iniciar"""
    try:
        profile = await self._hardware_profiler.profile()
        self._hardware_profile = profile
        logger.info("Hardware profiled: CPU=%d cores, RAM=%.1fGB, GPU=%s", 
                   profile.cpu_cores, profile.ram_gb, 
                   profile.gpu_name or "none")
        
        # Configurar Model Router con perfil
        if self._model_router:
            self._model_router.set_hardware_profile(profile)
            
            # Crear y configurar Model Capability Manager
            from sentinel.core.model_capability import ModelCapabilityManager
            capability_manager = ModelCapabilityManager(profile)
            await capability_manager.load_model_capabilities()
            self._model_router.set_capability_manager(capability_manager)
    except Exception as e:
        logger.warning("Hardware-aware configuration failed: %s", e)
```

**Integración**:
- Perfilado de hardware al iniciar (en background)
- Configuración automática de Model Router
- No bloquea inicio de aplicación

### 2.6 Nuevo Endpoint API

**Archivo**: `sidecar/modules/sentinel_bridge.py`
**Cambio**: Agregar endpoints para gestión de hardware y capacidades

**Cambio Específico**:
```python
# NUEVO: Endpoint para obtener perfil de hardware
@router.get("/sentinel/hardware/profile")
async def get_hardware_profile(request: Request):
    """Retorna el perfil de hardware del dispositivo"""
    from modules import get_hardware_profiler
    
    profiler = get_hardware_profiler()
    profile = profiler.get_cached_profile()
    
    if not profile:
        # Si no hay caché, perfilar ahora
        profile = await profiler.profile()
    
    return profile.to_dict()

# NUEVO: Endpoint para reprofilado de hardware
@router.post("/sentinel/hardware/reprofile")
async def reprofile_hardware(request: Request):
    """Reperfila hardware y actualiza caché"""
    from modules import get_hardware_profiler
    
    profiler = get_hardware_profiler()
    profiler.invalidate_cache()
    profile = await profiler.profile()
    
    # Actualizar Model Router
    from modules import get_sentinel_orchestrator
    orchestrator = get_sentinel_orchestrator()
    if orchestrator._model_router:
        orchestrator._model_router.set_hardware_profile(profile)
    
    return profile.to_dict()

# NUEVO: Endpoint para obtener modelos recomendados
@router.get("/sentinel/models/recommended")
async def get_recommended_models(task_type: str = Query(...)):
    """Retorna modelos recomendados según hardware"""
    from modules import get_model_capability_manager
    
    manager = get_model_capability_manager()
    if not manager:
        return {"error": "Model capability manager not available"}
    
    task_type_enum = TaskType(task_type) if task_type else TaskType.QUICK
    recommendation = await manager.recommend_model(task_type_enum, {})
    
    if recommendation:
        return {
            "recommended": recommendation.model_capability.to_dict(),
            "confidence": recommendation.confidence,
            "reasoning": recommendation.reasoning,
            "optimization_config": recommendation.optimization_config,
            "fallback_models": [m.to_dict() for m in recommendation.fallback_models]
        }
    else:
        return {"error": "No suitable model found"}
```

---

## 3. FILES AFFECTED

### 3.1 Nuevos Archivos

1. **`sentinel/core/hardware_profiler.py`** (NUEVO)
   - ~400 líneas estimadas
   - Analizador de hardware del dispositivo
   - Sin dependencias críticas

2. **`sentinel/core/model_capability.py`** (NUEVO)
   - ~450 líneas estimadas
   - Gestor de capacidades de modelos
   - Depende de: HardwareProfiler, ModelRouter

3. **`tests/test_hardware_profiler.py`** (NUEVO)
   - ~300 líneas estimadas
   - Tests de perfilado de hardware

4. **`tests/test_model_capability.py`** (NUEVO)
   - ~350 líneas estimadas
   - Tests de gestión de capacidades

### 3.2 Archivos Modificados

1. **`sentinel/core/model_router.py`**
   - Cambio: Integrar con Model Capability Manager
   - Cambio: Extender ProviderSpec con requisitos hardware
   - Líneas afectadas: ~80-100
   - Riesgo: MEDIO (integración en componente central)

2. **`sentinel/core/orchestrator.py`**
   - Cambio: Inicializar Hardware Profiler
   - Cambio: Configurar Model Router con perfil
   - Líneas afectadas: ~30-50
   - Riesgo: BAJO (inicialización en background)

### 3.3 Archivos Sin Cambios

Todos los demás archivos permanecen sin cambios para mantener compatibilidad.

---

## 4. RISK LEVEL

### 4.1 Riesgo General: MEDIO

**Justificación**:
- Componentes nuevos sin dependencias críticas
- Cambios en ModelRouter son integrativos (fallback a comportamiento existente)
- Perfilado de hardware es no invasivo y opcional
- Puede deshabilitarse mediante configuración
- No cambia interfaces principales de ejecución

### 4.2 Riesgos Específicos

#### RIESGO 1: Hardware Profiling Impact on Startup
**Severidad**: BAJA
**Probabilidad**: MEDIA
**Impacto**: Perfilado puede agregar tiempo al inicio
**Mitigación**:
- Perfilado en background (no bloquea inicio)
- Caché de perfil por sesión
- Timeout para perfilado
- Fallback a comportamiento sin profiling

#### RIESGO 2: Incorrect Hardware Detection
**Severidad**: MEDIA
**Probabilidad**: BAJA
**Impacto: Detección incorrecta puede llevar a selección subóptima de modelos
**Mitigación**:
- Validación de detección con datos conocidos
- Fallback a comportamiento existente si detección falla
- Logging extenso para debugging
- Confianza score en perfil

#### RIESGO 3: Model Recommendation Errors
**Severidad**: MEDIA
**Probabilidad**: BAJA
**Impacto: Recomendación incorrecta puede afectar performance
**Mitigación**:
- Validación de recomendaciones
- Múltiples fallback models
- Usuario puede sobrescribir selección
- Métricas de performance para aprendizaje

#### RIESGO 4: Integration with Model Router
**Severidad**: MEDIA
**Probabilidad**: BAJA
**Impacto: Integración puede afectar selección de modelos
**Mitigación**:
- Fallback a comportamiento existente si integración falla
- Tests exhaustivos de integración
- Feature flag para deshabilitar rápidamente
- Comparación con comportamiento anterior

#### RIESGO 5: Hardware Changes Not Detected
**Severidad**: BAJA
**Probabilidad**: BAJA
**Impacto: Cambios de hardware no detectados pueden causar problemas
**Mitigación**:
- Opción de reprofilado manual
- Detección periódica en background
- Alertas cuando rendimiento degrada significativamente
- Cache con TTL relativamente corto

---

## 5. ROLLBACK STRATEGY

### 5.1 Rollback Plan A: Deshabilitar Hardware Profiling

**Trigger**: Problemas con perfilado o detección incorrecta
**Acción**:
```python
# En Orchestrator.__init__
if config.get("enable_hardware_profiling", False):  # Default False
    self._hardware_profiler = HardwareProfiler()
else:
    self._hardware_profiler = None

# En ModelRouter
if config.get("enable_hardware_aware_selection", False):
    self._capability_manager = capability_manager
else:
    self._capability_manager = None
```

**Tiempo**: <5 minutos
**Impacto**: Sistema funciona sin hardware profiling
**Riesgo**: Ninguno

### 5.2 Rollback Plan B: Deshabilitar Model Capability Manager

**Trigger**: Problemas con recomendaciones de modelos
**Acción**:
```python
# En ModelRouter
self._capability_manager = None
self._hardware_profile = None
```

**Tiempo**: <5 minutos
**Impacto**: Sistema usa selección de modelos tradicional
**Riesgo**: Ninguno

### 5.3 Rollback Plan C: Revertir Model Router Changes

**Trigger**: Problemas de integración con Model Router
**Acción**:
- Revertir cambios en model_router.py
- Mantener nuevos componentes para futuro uso
- Deshabilitar integración en Orchestrator

**Tiempo**: ~15 minutos
**Impacto**: Vuelve a comportamiento anterior exacto
**Riesgo**: Bajo

### 5.4 Rollback Plan D: Rollback Completo

**Trigger**: Problemas severos que requieren limpieza total
**Acción**:
- Revertir todos los cambios en model_router.py
- Revertir cambios en orchestrator.py
- Eliminar archivos nuevos
- Restaurar versión anterior de repositorio

**Tiempo**: ~30 minutos
**Impacto**: Vuelve a estado anterior exacto
**Riesgo**: Ninguno

---

## 6. TESTING PLAN

### 6.1 Unit Tests (70%)

#### Tests para HardwareProfiler
```python
class TestHardwareProfiler:
    async def test_profiles_cpu_correctly(self):
        """Verifica que profiler detecta CPU correctamente"""
        profiler = HardwareProfiler()
        profile = await profiler.profile()
        
        assert profile.cpu_cores > 0
        assert profile.cpu_threads > 0
        assert profile.cpu_architecture in ["x86_64", "ARM64", "x86"]
    
    async def test_profiles_ram_correctly(self):
        """Verifica que profiler detecta RAM correctamente"""
        profiler = HardwareProfiler()
        profile = await profiler.profile()
        
        assert profile.ram_gb > 0
        assert profile.ram_available_gb > 0
        assert profile.ram_available_gb <= profile.ram_gb
    
    async def test_detects_gpu_when_available(self):
        """Verifica que profiler detecta GPU cuando está disponible"""
        profiler = HardwareProfiler()
        profile = await profiler.profile()
        
        # Si hay GPU, debe ser detectada
        if profile.gpu_available:
            assert profile.gpu_name is not None
            assert profile.gpu_vram_gb is not None
    
    async def test_detects_npu_when_available(self):
        """Verifica que profiler detecta NPU cuando está disponible"""
        profiler = HardwareProfiler()
        profile = await profiler.profile()
        
        # Si hay NPU, debe ser detectada
        if profile.npu_available:
            assert profile.npu_name is not None
            assert profile.npu_capability is not None
    
    async def test_detects_battery_when_available(self):
        """Verifica que profiler detecta batería cuando está disponible"""
        profiler = HardwareProfiler()
        profile = await profiler.profile()
        
        # Si hay batería, debe ser detectada
        if profile.battery_available:
            assert profile.battery_percent is not None
            assert 0 <= profile.battery_percent <= 100
    
    def test_cache_works(self):
        """Verifica que caché de perfil funciona"""
        profiler = HardwareProfiler()
        
        # Primera llamada: sin caché
        profile1 = await profiler.profile()
        assert profiler.get_cached_profile() is None
        
        # Segunda llamada: con caché
        profile2 = profiler.get_cached_profile()
        assert profile2 is not None
        assert profile2.cpu_cores == profile1.cpu_cores
        
        # Invalidar caché
        profiler.invalidate_cache()
        assert profiler.get_cached_profile() is None
```

#### Tests para ModelCapabilityManager
```python
class TestModelCapabilityManager:
    def test_can_run_model_with_sufficient_hardware(self):
        """Verifica que modelo se puede ejecutar con hardware suficiente"""
        hardware = HardwareProfile(
            cpu_cores=8, ram_gb=16, gpu_available=True, 
            gpu_vram_gb=8, gpu_name="RTX 3080"
        )
        manager = ModelCapabilityManager(hardware)
        
        model = ModelCapability(
            model_id="llama-3-70b",
            min_ram_gb=8,
            min_vram_gb=4,
            recommended_hardware=["gpu"],
            context_window=4096
        )
        
        assert manager.can_run_model(model) == True
    
    def test_cannot_run_model_with_insufficient_hardware(self):
        """Verifica que modelo NO se puede ejecutar con hardware insuficiente"""
        hardware = HardwareProfile(
            cpu_cores=4, ram_gb=8, gpu_available=False
        )
        manager = ModelCapabilityManager(hardware)
        
        model = ModelCapability(
            model_id="llama-3-70b",
            min_ram_gb=16,  # Requiere más RAM de lo disponible
            min_vram_gb=8,
            recommended_hardware=["gpu"],
            context_window=4096
        )
        
        assert manager.can_run_model(model) == False
    
    async def test_recommends_optimal_model(self):
        """Verifica que manager recomienda modelo óptimo"""
        hardware = HardwareProfile(
            cpu_cores=8, ram_gb=16, gpu_available=True, 
            gpu_vram_gb=8, gpu_name="RTX 3080"
        )
        manager = ModelCapabilityManager(hardware)
        
        # Simular carga de capacidades
        manager._model_capabilities = [
            ModelCapability(
                model_id="llama-3-8b",
                min_ram_gb=4,
                min_vram_gb=0,
                recommended_hardware=["cpu"],
                context_window=2048,
                estimated_tokens_per_second={'cpu': 15}
            ),
            ModelCapability(
                model_id="llama-3-70b",
                min_ram_gb=8,
                min_varam_gb=4,
                recommended_hardware=["gpu"],
                context_window=4096,
                estimated_tokens_per_second={'gpu': 50}
            ),
        ]
        
        recommendation = await manager.recommend_model(TaskType.REASONING, {})
        
        assert recommendation is not None
        assert recommendation.model_capability.model_id == "llama-3-70b"  # GPU más potente
        assert recommendation.hardware_suitable == True
    
    async def test_falls_back_to_cpu_when_gpu_unavailable(self):
        """Verifica que manager fallback a CPU cuando GPU no disponible"""
        hardware = HardwareProfile(
            cpu_cores=8, ram_gb=16, gpu_available=False
        )
        manager = ModelCapabilityManager(hardware)
        
        recommendation = await manager.recommend_model(TaskType.REASONING, {})
        
        # Debe recomendar modelo CPU en lugar de GPU
        assert recommendation.model_capability.recommended_hardware == ["cpu"]
        assert "cpu" in recommendation.model_capability.acceleration_support
    
    async def test_optimizes_model_config(self):
        """Verifica que manager optimiza configuración de modelo"""
        hardware = HardwareProfile(
            cpu_cores=8, ram_gb=16, gpu_available=True, 
            gpu_vram_gb=8, gpu_name="RTX 3080"
        )
        manager = ModelCapabilityManager(hardware)
        
        model = ModelCapability(
            model_id="llama-3-70b",
            min_ram_gb=8,
            min_vram_gb=4,
            recommended_hardware=["gpu"],
            context_window=4096,
            quantization_support=["fp16", "int8"]
        )
        
        config = await manager.optimize_model_config(model)
        
        assert "gpu" in config["acceleration"]
        assert config["context_window"] == 4096
        # Puede sugerir cuantización basada en VRAM disponible
```

### 6.2 Integration Tests (20%)

#### Tests de Integración con Model Router
```python
class TestModelRouterIntegration:
    async def test_router_uses_hardware_aware_selection(self):
        """Verifica que Model Router usa selección inteligente con hardware"""
        hardware = HardwareProfile(
            cpu_cores=8, ram_gb=16, gpu_available=True
        )
        capability_manager = ModelCapabilityManager(hardware)
        
        router = ModelRouter()
        router.set_hardware_profile(hardware)
        router.set_capability_manager(capability_manager)
        
        decision = router.select(TaskType.REASONING, {})
        
        # Debe usar estrategia hardware_aware si hay recommendation
        assert decision.strategy == "hardware_aware"
        assert "selection_trace" in decision.to_dict()
    
    async def test_router_fallback_without_capability_manager(self):
        """Verifica que Router fallback sin capability manager"""
        router = ModelRouter()
        # Sin capability manager configurado
        
        decision = router.select(TaskType.REASONING, {})
        
        # Debe usar estrategia tradicional
        assert decision.strategy in ["priority", "cost", "local_first"]
    
    async def test_router_handles_capability_manager_failure(self):
        """Verifica que Router maneja fallos de capability manager"""
        hardware = HardwareProfile(cpu_cores=8, ram_gb=16)
        failing_manager = FailingModelCapabilityManager()
        
        router = ModelRouter()
        router.set_hardware_profile(hardware)
        router.set_capability_manager(failing_manager)
        
        decision = router.select(TaskType.REASONING, {})
        
        # Debe fallback a comportamiento tradicional
        assert decision.strategy != "hardware_aware"
```

#### Tests de Integración con Orchestrator
```python
class TestOrchestratorIntegration:
    async def test_orchestrator_profiles_hardware_on_startup(self):
        """Verifica que Orchestrator perfila hardware al iniciar"""
        orchestrator = create_test_orchestrator()
        
        # Esperar a que perfilado en background complete
        await asyncio.sleep(2)
        
        assert orchestrator._hardware_profile is not None
        assert orchestrator._hardware_profile.cpu_cores > 0
    
    async def test_orchestrator_configures_model_router(self):
        """Verifica que Orchestrator configura Model Router"""
        orchestrator = create_test_orchestrator()
        
        # Esperar a que inicialización complete
        await asyncio.sleep(2)
        
        assert orchestrator._model_router._hardware_profile is not None
        assert orchestrator._model_router._capability_manager is not None
```

### 6.3 E2E Tests (10%)

#### Tests de Flujo Completo
```python
class TestHardwareIntelligenceE2E:
    async def test_system_recommends_model_based_on_hardware(self):
        """Verifica que el sistema recomienda modelo según hardware"""
        # Configurar sistema con GPU simulada
        await configure_hardware(gpu=True, ram_gb=16)
        
        # Solicitar recomendación
        recommendation = await api_get_recommended_models("reasoning")
        
        # Debe recomendar modelo GPU
        assert "gpu" in recommendation["recommended"]["recommended_hardware"]
        assert recommendation["confidence"] > 0.7
    
    async def test_system_fallback_to_cpu_without_gpu(self):
        """Verifica que sistema fallback a CPU sin GPU"""
        # Configurar sistema sin GPU
        await configure_hardware(gpu=False, ram_gb=8)
        
        recommendation = await api_get_recommended_models("reasoning")
        
        # Debe recomendar modelo CPU
        assert "cpu" in recommendation["recommended"]["recommended_hardware"]
    
    async def test_user_can_override_recommendation(self):
        """Verifica que usuario puede sobrescribir recomendación"""
        # Obtener recomendación
        recommendation = await api_get_recommended_models("reasoning")
        
        # Usuario selecciona modelo diferente
        await api_set_model("custom_model")
        
        # Verificar que se usa modelo seleccionado
        response = await api_sentinel_process("test message")
        assert response["model"] == "custom_model"
```

### 6.4 Performance Tests

```python
class TestHardwareIntelligencePerformance:
    async def test_hardware_profiling_performance_acceptable(self):
        """Verifica que perfilado de hardware tiene performance aceptable"""
        profiler = HardwareProfiler()
        
        start = time.perf_counter()
        profile = await profiler.profile()
        elapsed = time.perf_counter() - start
        
        assert elapsed < 3.0  # Menos de 3 segundos
    
    async def test_model_recommendation_performance_acceptable(self):
        """Verifica que recomendación de modelo es rápida"""
        hardware = HardwareProfile(cpu_cores=8, ram_gb=16)
        manager = ModelCapabilityManager(hardware)
        
        start = time.perf_counter()
        recommendation = await manager.recommend_model(TaskType.REASONING, {})
        elapsed = time.perf_counter() - start
        
        assert elapsed < 0.5  # Menos de 500ms
    
    async def test_hardware_aware_selection_overhead_minimal(self):
        """Verifica que overhead de selección inteligente es mínimo"""
        router = ModelRouter()
        router.set_hardware_profile(create_hardware_profile())
        router.set_capability_manager(create_capability_manager())
        
        start = time.perf_counter()
        decision = router.select(TaskType.REASONING, {})
        elapsed = time.perf_counter() - start
        
        assert elapsed < 0.1  # Menos de 100ms overhead
```

### 6.5 Coverage Goal

- **HardwareProfiler**: >85% coverage
- **ModelCapabilityManager**: >85% coverage
- **Integración**: >80% coverage
- **Total FASE 6**: >80% coverage

---

## 7. IMPLEMENTACIÓN DETALLADA

### 7.1 Semana 1: Hardware Profiler

**Objetivo**: Implementar análisis de hardware del dispositivo

**Tareas**:
1. Crear `sentinel/core/hardware_profiler.py`
2. Implementar detección de CPU (psutil)
3. Implementar detección de RAM (psutil)
4. Implementar detección de GPU (CUDA, OpenCL, DirectX)
5. Implementar detección de NPU (si está disponible)
6. Implementar detección de almacenamiento
7. Implementar detección de batería
8. Implementar detección de OS
9. Unit tests para cada componente de detección
10. Tests de performance de perfilado

**Entregables**:
- HardwareProfiler funcional
- Detección de componentes principales funcionando
- Tests unitarios pasando
- Documentación de detección por plataforma

### 7.2 Semana 2: Model Capability Manager e Integración

**Objetivo**: Implementar gestión de capacidades e integración completa

**Tareas**:
1. Crear `sentinel/core/model_capability.py`
2. Implementar base de datos de capacidades de modelos
3. Implementar lógica de recomendación de modelos
4. Implementar optimización de configuración
5. Extender ProviderSpec con requisitos hardware
6. Integrar en Model Router
7. Integrar en Orchestrator
8. Agregar endpoints API
9. Integration tests completos
10. E2E tests
11. Performance tests
12. Documentación completa
13. Code review

**Entregables**:
- ModelCapabilityManager funcional
- Integración completa en pipeline
- Todos los tests pasando
- Documentación completa
- Listo para beta testing

---

## 8. DEPENDENCIAS Y REQUISITOS

### 8.1 Dependencias Existentes (Nuevas)

**Ninguna** - Todos los componentes nuevos usan solo dependencias existentes:
- `asyncio` (standard library)
- `typing` (standard library)
- `dataclasses` (standard library)
- `psutil` (ya es dependencia del proyecto)
- Componentes existentes de Sentinel

### 8.2 Dependencias de Componentes

**HardwareProfiler depende de**:
- Ninguna (usa psutil que ya es dependencia)

**ModelCapabilityManager depende de**:
- HardwareProfiler (inyectado)
- ModelRouter (inyectado)

### 8.3 Requisitos de Sistema

**CPU**: Sin impacto adicional
**RAM**: ~20MB adicional para caché de perfil
**Disco**: ~3MB para código nuevo
**GPU**: No requiere GPU para funcionar (puede detectar sin tener una)

### 8.4 Requisitos de Plataforma

**Windows**: Soporte completo (DirectX para GPU)
**Linux**: Soporte (CUDA, OpenCL para GPU)
**macOS**: Soporte (Metal para GPU)

---

## 9. MÉTRICAS DE ÉXITO

### 9.1 Métricas Técnicas

- **Coverage**: >80% para código nuevo
- **Profiling Performance**: <3s para perfilado completo
- **Recommendation Performance**: <500ms para recomendación
- **Selection Overhead**: <100ms overhead en selección inteligente
- **Accuracy**: >90% de detecciones de hardware correctas

### 9.2 Métricas Funcionales

- **Hardware Detection Accuracy**: >90% de componentes detectados correctamente
- **Model Recommendation Accuracy**: >85% de recomendaciones son óptimas
- **Hardware Utilization**: >80% de capacidad de hardware utilizada cuando posible
- **Fallback Success**: 100% de fallbacks funcionan correctamente

### 9.3 Métricas de Performance

- **Startup Impact**: <2s overhead en inicio (perfilado en background)
- **Selection Improvement**: >30% mejora en selección de modelos vs. tradicional
- **Resource Efficiency**: >40% mejor uso de recursos disponibles

### 9.4 Métricas de Calidad

- **Bug Rate**: <2 bugs críticos durante fase 6
- **Test Pass Rate**: 100% de tests pasando al final
- **Documentation Coverage**: 100% de componentes nuevos documentados

---

## 10. PLAN DE COMUNICACIÓN

### 10.1 Stakeholders

**Usuarios**:
- Comunicar mejora en selección de modelos
- Explicar que el sistema adapta a su hardware
- Documentar cómo ver perfil de hardware
- Explicar cómo sobrescribir selección automática

**Desarrolladores**:
- Comunicar nueva capacidad de hardware-aware routing
- Documentar API para gestión de hardware
- Explicar patrones de extensión
- Proporcionar ejemplos de integración

**QA**:
- Proporcionar criterios de aceptación
- Documentar casos de prueba de hardware
- Explicar procedimientos de validación multi-plataforma

### 10.2 Documentación Requerida

1. **Documentación de Usuario**:
   - Cómo funciona el hardware-aware routing
   - Cómo ver perfil de hardware del dispositivo
   - Cómo sobrescribir selección automática de modelos
   - Opciones de configuración

2. **Documentación de Desarrollador**:
   - API para Hardware Profiler
   - API para Model Capability Manager
   - Cómo agregar capacidades de nuevos modelos
   - Patrones de optimización

3. **Documentación de Arquitectura**:
   - Diagrama de sistema de hardware intelligence
   - Flujo de selección de modelos basado en hardware
   - Integración con componentes existentes

4. **Documentación de API**:
   - Nuevos endpoints para hardware y capacidades
   - Cambios en Model Router
   - Ejemplos de uso

---

## 11. CRITERIOS DE ACEPTACIÓN

### 11.1 Criterios Técnicos

- [ ] Todos los unit tests pasan (>80% coverage)
- [ ] Todos los integration tests pasan
- [ ] Todos los E2E tests pasan
- [ ] Todos los performance tests pasan
- [ ] Code review completado y aprobado
- [ ] Sin dependencias nuevas agregadas

### 11.2 Criterios Funcionales

- [ ] HardwareProfiler detecta >90% de componentes correctamente
- [ ] ModelCapabilityManager recomienda modelos óptimos >85% del tiempo
- [ ] Hardware-aware routing mejora selección vs. tradicional >30%
- [ ] Fallback a comportamiento tradicional funciona 100%
- [ ] Sistema funciona correctamente sin GPU o NPU

### 11.3 Criterios de Performance

- [ ] Profiling performance <3s (100%)
- [ ] Recommendation performance <500ms (100%)
- [ ] Selection overhead <100ms (100%)
- [ ] Startup overhead <2s (100%)

### 11.4 Criterios de Multi-Plataforma

- [ ] Hardware profiling funciona en Windows (100%)
- [ ] Hardware profiling funciona en Linux (100%)
- [ ] Hardware profiling funciona en macOS (100%)
- [ ] GPU detection funciona en las tres plataformas (100%)

### 11.5 Criterios de Calidad

- [ ] Documentación completa y precisa
- [ ] Código sigue convenciones del projecto
- [ ] Sin warnings de linter
- [ ] Sin vulnerabilidades de seguridad introducidas
- [ ] Compatible con versiones existentes

---

## 12. CONFIRMACIÓN REQUERIDA

Antes de proceder con la implementación de FASE 6, confirmar:

1. **¿Aprobar el plan de implementación propuesto?**
2. **¿Están de acuerdo con la estrategia de testing multi-plataforma?**
3. **¿Los criterios de aceptación (incluyendo multi-plataforma) son apropiados?**
4. **¿Algún ajuste requerido antes de comenzar la implementación?**

---

## 13. CONSIDERACIONES ESPECIALES

### 13.1 Multi-Plataforma

**Consideración**: Soportar diferentes sistemas operativos y hardware
- Implementar detección específica por plataforma (Windows/DirectX, Linux/CUDA, macOS/Metal)
- Tests de compatibilidad cruzada
- Documentación para cada plataforma
- Fallbacks cuando detección específica falla

### 13.2 Compatibilidad con FASE 2, 3, 4, 5

**Consideración**: Integración con cambios anteriores
- Hardware Intelligence debe trabajar con Grounding de FASE 2
- Presentation Layer de FASE 3 debe filtrar detalles de hardware
- Decision Engine de FASE 4 debe considerar capacidades del hardware
- Environmental Learning de FASE 5 debe almacenar perfiles de hardware

### 13.3 Extensibilidad

**Consideración: Facilitar agregar soporte para nuevos modelos
- Sistema de capacidades debe ser fácilmente extensible
- Validación de requisitos de hardware debe ser flexible
- Documentación clara para agregar nuevos modelos

### 13.4 Privacy

**Consideración**: Respetar privacidad del usuario
- Solo se detecta información técnica de hardware
- No se envía información de hardware a servicios externos
- Opción para deshabilitar profiling
- Datos de hardware solo se usan localmente

---

**DOCUMENTO FASE_6_ARCHITECTURE_IMPACT.md COMPLETADO**

Este documento detalla el impacto arquitectónico de implementar el Hardware Intelligence en FASE 6, incluyendo archivos afectados, nivel de riesgo MEDIO, estrategia de rollback y plan de testing con énfasis en multi-plataforma y performance.

**ESTADO**: Pendiente de aprobación antes de implementación.
