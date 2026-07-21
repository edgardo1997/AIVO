# FASE 5: ENVIRONMENTAL LEARNING - ARCHITECTURE IMPACT

**Fecha**: 2025-01-17
**Fase**: 5 - Environmental Learning
**Prioridad**: ALTA
**Duración Estimada**: 3 semanas
**Estado**: Pendiente de aprobación

---

## 1. PROPÓSITO

Implementar un sistema de aprendizaje contextual del entorno que permita a Sentinel construir conocimiento operativo sobre aplicaciones instaladas, rutas, capacidades, preferencias del usuario y cambios del sistema.

**Objetivo**: Sentinel debe aprender continuamente del dispositivo donde está instalado para mejorar la precisión de sus respuestas y acciones sin depender exclusivamente del modelo de IA.

---

## 2. ARCHITECTURE IMPACT

### 2.1 Nuevo Componente: Application Discovery Service

**Archivo**: `sentinel/services/app_discovery.py` (NUEVO)
**Responsabilidad**: 
- Detectar nuevas aplicaciones instaladas
- Detectar cambios de versión
- Detectar nuevos ejecutables
- Analizar aplicaciones desconocidas
- Actualizar App Knowledge Engine

**Dependencias**:
- Ninguna (usa sistema operativo directamente)

**Interfaces Públicas**:
```python
@dataclass
class AppProfile:
    """Perfil de una aplicación descubierta"""
    name: str
    path: str
    executable: str
    version: Optional[str]
    icon: Optional[str]
    category: str
    permissions: List[str]
    capabilities: List[str]
    possible_actions: List[str]
    discovered_at: str
    last_seen: str
    confidence: float
    file_hash: Optional[str]  # Para detectar cambios

class ApplicationDiscoveryService:
    def __init__(self, knowledge_base: KnowledgeBase)
    async def discover_applications(self) -> List[AppProfile]
    async def detect_changes(self) -> List[AppChange]
    def resolve_app_intent(self, user_intent: str) -> Optional[AppProfile]
    async def analyze_unknown_app(self, path: str) -> AppProfile
    async def scan_directory(self, directory: str) -> List[AppProfile]
```

### 2.2 Nuevo Componente: App Knowledge Engine

**Archivo**: `sentinel/services/app_knowledge.py` (NUEVO)
**Responsabilidad**: 
- Almacenar y recuperar perfiles de aplicaciones
- Indexar aplicaciones por nombre, ruta, capacidades
- Mantener caché de aplicaciones conocidas
- Proporcionar búsqueda semántica de aplicaciones
- Invalidar conocimiento obsoleto

**Dependencias**:
- KnowledgeBase (para persistencia)

**Interfaces Públicas**:
```python
@dataclass
class AppChange:
    """Cambio detectado en una aplicación"""
    app_id: str
    change_type: str  # 'installed', 'updated', 'removed', 'path_changed'
    old_profile: Optional[AppProfile]
    new_profile: Optional[AppProfile]
    detected_at: str

class AppKnowledgeEngine:
    def __init__(self, knowledge_base: KnowledgeBase)
    async def store_profile(self, profile: AppProfile) -> None
    async def get_profile(self, app_id: str) -> Optional[AppProfile]
    async def search_by_name(self, name: str) -> List[AppProfile]
    async def search_by_capability(self, capability: str) -> List[AppProfile]
    async def search_by_category(self, category: str) -> List[AppProfile]
    async def resolve_alias(self, alias: str) -> Optional[AppProfile]
    async def update_profile(self, app_id: str, profile: AppProfile) -> None
    async def remove_profile(self, app_id: str) -> None
    async def get_all_profiles(self) -> List[AppProfile]
    async def invalidate_stale(self, ttl_hours: float = 168) -> int
```

### 2.3 Nuevo Componente: Change Detector

**Archivo**: `sentinel/services/change_detector.py` (NUEVO)
**Responsabilidad**: 
- Detectar cambios en el sistema
- Comparar estado actual con estado anterior
- Identificar cambios relevantes para Sentinel
- Generar eventos de cambio

**Dependencias**:
- ApplicationDiscoveryService (para detectar cambios de apps)
- KnowledgeBase (para estado anterior)

**Interfaces Públicas**:
```python
@dataclass
class SystemChange:
    """Cambio detectado en el sistema"""
    change_type: str  # 'app_installed', 'app_removed', 'app_updated', 'config_changed'
    entity_id: str
    description: str
    detected_at: str
    relevance: str  # 'high', 'medium', 'low'

class ChangeDetector:
    def __init__(self, discovery_service: ApplicationDiscoveryService, knowledge_base: KnowledgeBase)
    async def scan_for_changes(self) -> List[SystemChange]
    async def get_change_history(self, limit: int = 100) -> List[SystemChange]
    async def mark_change_processed(self, change_id: str) -> None
```

### 2.4 Nuevo Componente: Environment Memory

**Archivo**: `sentinel/services/environment_memory.py` (NUEVO)
**Responsabilidad**: 
- Almacenar conocimiento del entorno
- Mantener preferencias del usuario
- Recordar patrones de uso
- Aprender de interacciones exitosas/fallidas

**Dependencias**:
- KnowledgeBase (para persistencia)

**Interfaces Públicas**:
```python
@dataclass
class EnvironmentMemoryEntry:
    """Entrada de memoria del entorno"""
    key: str
    value: Any
    source: str
    timestamp: str
    confidence: float
    category: str  # 'app_preference', 'usage_pattern', 'system_state', 'user_behavior'
    ttl_seconds: Optional[float]

class EnvironmentMemory:
    def __init__(self, knowledge_base: KnowledgeBase)
    async def store(self, key: str, value: Any, category: str, **kwargs) -> None
    async def retrieve(self, key: str) -> Optional[EnvironmentMemoryEntry]
    async def retrieve_by_category(self, category: str) -> List[EnvironmentMemoryEntry]
    async def search(self, pattern: str) -> List[EnvironmentMemoryEntry]
    async def invalidate(self, key: str) -> None
    async def invalidate_category(self, category: str) -> int
    async def cleanup_expired(self) -> int
```

### 2.5 Modificación: Deep Context Engine

**Archivo**: `sentinel/core/deep_context.py`
**Cambio**: Implementar app_discovery_fn real usando Application Discovery Service

**Cambio Específico**:
```python
# ANTES
def __init__(self, ...):
    self._app_discovery = app_discovery_fn  # Hook no implementado
    
async def collect(self) -> Dict[str, Any]:
    # ...
    try:
        if self._app_discovery:
            apps = self._app_discovery()  # Hook returns None
            ctx["installed_apps"] = apps
            ctx["installed_apps_count"] = len(apps) if apps else 0
    except Exception as e:
        logger.debug("Apps not available: %s", e)
        ctx["installed_apps"] = []
        ctx["installed_apps_count"] = 0

# DESPUÉS
def __init__(self, ...):
    self._app_discovery_service = app_discovery_service  # Servicio real
    
async def collect(self) -> Dict[str, Any]:
    # ...
    try:
        if self._app_discovery_service:
            # Usar servicio real de descubrimiento
            apps = await self._app_discovery_service.discover_applications()
            ctx["installed_apps"] = [app.to_dict() for app in apps]
            ctx["installed_apps_count"] = len(apps)
            ctx["app_categories"] = self._categorize_apps(apps)
    except Exception as e:
        logger.warning("App discovery failed: %s", e)
        ctx["installed_apps"] = []
        ctx["installed_apps_count"] = 0
```

**Integración**:
- Implementación real del hook existente
- Usa ApplicationDiscoveryService
- Proporciona datos enriquecidos de aplicaciones

### 2.6 Modificación: Knowledge Base

**Archivo**: `sentinel/core/knowledge_base.py`
**Cambio**: Extender para soportar AppProfile y Environment Memory

**Cambio Específico**:
```python
# NUEVOS MÉTODOS
async def store_app_profile(self, profile: AppProfile) -> None:
    """Almacena un perfil de aplicación"""
    await self._repository.store(
        f"app_profile:{profile.name}:{profile.path}",
        profile.to_dict(),
        category="app_profile"
    )

async def get_app_profile(self, app_id: str) -> Optional[AppProfile]:
    """Recupera un perfil de aplicación"""
    data = await self._repository.retrieve(f"app_profile:{app_id}")
    return AppProfile.from_dict(data) if data else None

async def search_app_profiles(self, query: str) -> List[AppProfile]:
    """Busca perfiles de aplicación"""
    profiles = await self._repository.search(query, category="app_profile")
    return [AppProfile.from_dict(p) for p in profiles]

async def store_environment_memory(self, entry: EnvironmentMemoryEntry) -> None:
    """Almacena entrada de memoria del entorno"""
    await self._repository.store(
        f"env_memory:{entry.category}:{entry.key}",
        entry.to_dict(),
        category="environment_memory"
    )

async def get_environment_memory(self, key: str) -> Optional[EnvironmentMemoryEntry]:
    """Recupera entrada de memoria del entorno"""
    data = await self._repository.retrieve(f"env_memory:{key}")
    return EnvironmentMemoryEntry.from_dict(data) if data else None
```

**Integración**:
- Extiende KnowledgeBase existente
- Soporta nuevos tipos de datos
- Mantiene compatibilidad con funcionalidad existente

### 2.7 Modificación: Planner

**Archivo**: `sentinel/core/planner.py`
**Cambio**: Integrar con Application Discovery para planes inteligentes

**Cambio Específico**:
```python
# EN __init__
def __init__(self, ..., app_knowledge: Optional[AppKnowledgeEngine] = None):
    # ... código existente ...
    self._app_knowledge = app_knowledge

# EN plan()
async def plan(self, intent: Intent, context: Optional[Dict[str, Any]] = None) -> Plan:
    target = intent.target
    
    # NUEVO: Intentar resolver a aplicación si es relevante
    if self._app_knowledge and self._is_app_intent(intent):
        app_profile = await self._app_knowledge.resolve_app_intent(target)
        if app_profile:
            # Generar plan basado en aplicación conocida
            return self._create_app_plan(intent, app_profile, context)
    
    # ... código existente ...
    
def _is_app_intent(self, intent: Intent) -> bool:
    """Verifica si el intent se refiere a una aplicación"""
    app_keywords = ["abre", "abrir", "lanza", "lanzar", "inicia", "iniciar", "start", "launch"]
    return any(kw in intent.raw_input.lower() for kw in app_keywords)

def _create_app_plan(self, intent: Intent, app_profile: AppProfile, context: Dict[str, Any]) -> Plan:
    """Crea un plan basado en una aplicación conocida"""
    # Usar capacidades conocidas de la aplicación
    # Por ejemplo, si es VS Code, incluir capacidades de edición
    steps = []
    
    if "coding" in app_profile.capabilities:
        steps.append(PlanStep(
            id="open_app",
            tool_id="executor.launch",
            description=f"Abrir {app_profile.name}",
            params={"app_name": app_profile.name, "path": app_profile.path},
            estimated_impact="low",
            is_reversible=True
        ))
    
    return Plan(steps=steps, intent=intent, risk_score=0.1)
```

**Integración**:
- Planner puede usar conocimiento de aplicaciones
- Genera planes más inteligentes para intents de aplicaciones
- Fallback a comportamiento existente si no hay conocimiento

### 2.8 Nuevo Endpoint API

**Archivo**: `sidecar/modules/sentinel_bridge.py`
**Cambio**: Agregar endpoints para gestión de conocimiento del entorno

**Cambio Específico**:
```python
# NUEVO: Endpoint para descubrir aplicaciones
@router.post("/sentinel/discover-apps")
async def discover_apps(request: Request):
    """Dispara descubrimiento de aplicaciones"""
    from modules import get_app_discovery_service
    
    discovery = get_app_discovery_service()
    apps = await discovery.discover_applications()
    
    return {
        "discovered": len(apps),
        "apps": [app.to_dict() for app in apps],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# NUEVO: Endpoint para obtener aplicaciones conocidas
@router.get("/sentinel/apps")
async def get_known_apps(request: Request):
    """Retorna aplicaciones conocidas"""
    from modules import get_app_knowledge
    
    knowledge = get_app_knowledge()
    apps = await knowledge.get_all_profiles()
    
    return {
        "total": len(apps),
        "apps": [app.to_dict() for app in apps]
    }

# NUEVO: Endpoint para buscar aplicaciones
@router.get("/sentinel/apps/search")
async def search_apps(query: str = Query(...)):
    """Busca aplicaciones por nombre o capacidad"""
    from modules import get_app_knowledge
    
    knowledge = get_app_knowledge()
    results = await knowledge.search_by_name(query)
    
    return {
        "query": query,
        "results": [app.to_dict() for app in results]
    }

# NUEVO: Endpoint para obtener cambios del sistema
@router.get("/sentinel/changes")
async def get_system_changes(limit: int = Query(50)):
    """Retorna cambios detectados en el sistema"""
    from modules import get_change_detector
    
    detector = get_change_detector()
    changes = await detector.get_change_history(limit)
    
    return {
        "total": len(changes),
        "changes": [change.to_dict() for change in changes]
    }
```

---

## 3. FILES AFFECTED

### 3.1 Nuevos Archivos

1. **`sentinel/services/app_discovery.py`** (NUEVO)
   - ~400 líneas estimadas
   - Servicio de descubrimiento de aplicaciones
   - Sin dependencias críticas

2. **`sentinel/services/app_knowledge.py`** (NUEVO)
   - ~350 líneas estimadas
   - Motor de conocimiento de aplicaciones
   - Depende de: KnowledgeBase

3. **`sentinel/services/change_detector.py`** (NUEVO)
   - ~250 líneas estimadas
   - Detector de cambios del sistema
   - Depende de: ApplicationDiscoveryService, KnowledgeBase

4. **`sentinel/services/environment_memory.py`** (NUEVO)
   - ~300 líneas estimadas
   - Memoria del entorno
   - Depende de: KnowledgeBase

5. **`tests/test_app_discovery.py`** (NUEVO)
   - ~300 líneas estimadas
   - Tests de descubrimiento de aplicaciones

6. **`tests/test_app_knowledge.py`** (NUEVO)
   - ~250 líneas estimadas
   - Tests de motor de conocimiento

7. **`tests/test_change_detector.py`** (NUEVO)
   - ~200 líneas estimadas
   - Tests de detector de cambios

8. **`tests/test_environment_memory.py`** (NUEVO)
   - ~200 líneas estimadas
   - Tests de memoria del entorno

### 3.2 Archivos Modificados

1. **`sentinel/core/deep_context.py`**
   - Cambio: Implementar app_discovery_fn real
   - Cambio: Usar ApplicationDiscoveryService
   - Líneas afectadas: ~30-50
   - Riesgo: MEDIO (implementación de hook existente)

2. **`sentinel/core/knowledge_base.py`**
   - Cambio: Extender para soportar AppProfile y Environment Memory
   - Líneas afectadas: ~50-70
   - Riesgo: BAJO (extensión aditiva)

3. **`sentinel/core/planner.py`**
   - Cambio: Integrar con Application Discovery
   - Líneas afectadas: ~40-60
   - Riesgo: MEDIO (integración en componente existente)

4. **`sidecar/modules/sentinel_bridge.py`**
   - Cambio: Agregar endpoints para gestión de conocimiento
   - Líneas afectadas: ~50-70
   - Riesgo: BAJO (nuevos endpoints aditivos)

### 3.3 Archivos Sin Cambios

Todos los demás archivos permanecen sin cambios para mantener compatibilidad.

---

## 4. RISK LEVEL

### 4.1 Riesgo General: MEDIO

**Justificación**:
- Componentes nuevos sin dependencias críticas
- Cambios en componentes existentes son extensiones aditivas
- DeepContextEngine hook ya existía (solo implementación)
- Puede deshabilitarse mediante configuración
- No cambia interfaces principales de ejecución

### 4.2 Riesgos Específicos

#### RIESGO 1: Discovery Performance Impact
**Severidad**: MEDIA
**Probabilidad**: MEDIA
**Impacto**: Escaneo de aplicaciones puede ser lento en sistemas con muchas apps
**Mitigación**:
- Implementar escaneo diferencial (solo directorios comunes)
- Caché de resultados de descubrimiento
- Escaneo en background, no bloqueante
- Lazy loading de detalles de aplicaciones

#### RIESGO 2: False Positives en App Detection
**Severidad**: BAJA
**Probabilidad**: MEDIA
**Impacto**: Puede detectar archivos como aplicaciones incorrectamente
**Mitigación**:
- Heurísticas conservadoras para detección
- Validación de ejecutables (extensiones, headers)
- Confianza score en perfiles
- Revisión manual de detecciones dudosas

#### RIESGO 3: Knowledge Base Pollution
**Severidad**: MEDIA
**Probabilidad**: BAJA
**Impacto: Conocimiento incorrecto puede afectar decisiones
**Mitigación**:
- TTL para todas las entradas de conocimiento
- Validación de datos antes de almacenar
- Sistema de invalidación automática
- Confianza score para filtrar conocimiento dudoso

#### RIESGO 4: Privacy Impact
**Severidad**: MEDIA
**Probabilidad**: BAJA
**Impacto: Almacenar información de aplicaciones puede exponer hábitos del usuario
**Mitigación**:
- Solo almacenar metadatos técnicos (nombre, ruta, versión)
- No almacenar historial de uso sin consentimiento
- Opción para deshabilitar descubrimiento
- Política de retención clara

#### RIESGO 5: Integration with Planner
**Severidad**: MEDIA
**Probabilidad**: BAJA
**Impacto: Integración con Planner puede afectar generación de planes
**Mitigación**:
- Fallback a comportamiento existente si conocimiento falla
- Tests exhaustivos de integración
- Validación de planes generados
- Feature flag para deshabilitar rápidamente

---

## 5. ROLLBACK STRATEGY

### 5.1 Rollback Plan A: Deshabilitar Discovery

**Trigger**: Problemas de performance o detección incorrecta
**Acción**:
```python
# En DeepContextEngine.__init__
if config.get("enable_app_discovery", False):  # Default False
    self._app_discovery_service = app_discovery_service
else:
    self._app_discovery_service = None

# En Planner.__init__
if config.get("enable_app_knowledge", False):
    self._app_knowledge = app_knowledge
else:
    self._app_knowledge = None
```

**Tiempo**: <5 minutos
**Impacto**: Sistema funciona sin descubrimiento de aplicaciones
**Riesgo**: Ninguno

### 5.2 Rollback Plan B: Deshabilitar Endpoints

**Trigger**: Problemas con nuevos endpoints API
**Acción**:
- Remover nuevos endpoints de sentinel_bridge.py
- Mantener servicios backend para futuro uso

**Tiempo**: ~10 minutos
**Impacto**: UI no tiene acceso a nuevos features
**Riesgo**: Bajo

### 5.3 Rollback Plan C: Revertir Integración

**Trigger**: Problemas de integración con componentes existentes
**Acción**:
- Revertir cambios en deep_context.py
- Revertir cambios en knowledge_base.py
- Revertir cambios en planner.py
- Mantener servicios nuevos para futuro uso

**Tiempo**: ~20 minutos
**Impacto**: Vuelve a comportamiento anterior exacto
**Riesgo**: Bajo

### 5.4 Rollback Plan D: Rollback Completo

**Trigger**: Problemas severos que requieren limpieza total
**Acción**:
- Revertir todos los cambios en componentes existentes
- Eliminar archivos nuevos
- Restaurar versión anterior de repositorio

**Tiempo**: ~30 minutos
**Impacto**: Vuelve a estado anterior exacto
**Riesgo**: Ninguno

---

## 6. TESTING PLAN

### 6.1 Unit Tests (70%)

#### Tests para ApplicationDiscoveryService
```python
class TestApplicationDiscoveryService:
    async def test_discovers_installed_apps(self):
        """Verifica que el servicio descubre aplicaciones instaladas"""
        service = ApplicationDiscoveryService(knowledge_base)
        apps = await service.discover_applications()
        
        assert len(apps) > 0
        assert all(isinstance(app, AppProfile) for app in apps)
    
    async def test_detects_new_installations(self):
        """Verifica que el servicio detecta nuevas instalaciones"""
        service = ApplicationDiscoveryService(knowledge_base)
        
        # Simular instalación de nueva app
        changes = await service.detect_changes()
        
        assert any(c.change_type == "installed" for c in changes)
    
    async def test_detects_app_updates(self):
        """Verifica que el servicio detecta actualizaciones"""
        service = ApplicationDiscoveryService(knowledge_base)
        
        # Simular actualización de app
        changes = await service.detect_changes()
        
        assert any(c.change_type == "updated" for c in changes)
    
    def test_resolves_app_intent(self):
        """Verifica que el servicio resuelve intenciones de usuario"""
        service = ApplicationDiscoveryService(knowledge_base)
        
        # Simular conocimiento de VS Code
        await service._knowledge.store_profile(create_vscode_profile())
        
        result = service.resolve_app_intent("abre mi editor")
        
        assert result is not None
        assert result.name == "Visual Studio Code"
    
    async def test_analyzes_unknown_app(self):
        """Verifica que el servicio analiza aplicaciones desconocidas"""
        service = ApplicationDiscoveryService(knowledge_base)
        
        profile = await service.analyze_unknown_app("/path/to/unknown/app.exe")
        
        assert profile is not None
        assert profile.confidence < 1.0  # Menor confianza para apps desconocidas
```

#### Tests para AppKnowledgeEngine
```python
class TestAppKnowledgeEngine:
    async def test_stores_and_retrieves_profile(self):
        """Verifica que el motor almacena y recupera perfiles"""
        engine = AppKnowledgeEngine(knowledge_base)
        profile = create_test_profile()
        
        await engine.store_profile(profile)
        retrieved = await engine.get_profile(profile.name)
        
        assert retrieved is not None
        assert retrieved.name == profile.name
    
    async def test_searches_by_name(self):
        """Verifica que el motor busca por nombre"""
        engine = AppKnowledgeEngine(knowledge_base)
        
        await engine.store_profile(create_test_profile(name="VS Code"))
        await engine.store_profile(create_test_profile(name="Chrome"))
        
        results = await engine.search_by_name("code")
        
        assert len(results) > 0
        assert any("code" in r.name.lower() for r in results)
    
    async def test_searches_by_capability(self):
        """Verifica que el motor busca por capacidad"""
        engine = AppKnowledgeEngine(knowledge_base)
        
        await engine.store_profile(create_test_profile(capabilities=["coding"]))
        await engine.store_profile(create_test_profile(capabilities=["browsing"]))
        
        results = await engine.search_by_capability("coding")
        
        assert len(results) > 0
        assert all("coding" in r.capabilities for r in results)
    
    async def test_invalidates_stale_profiles(self):
        """Verifica que el motor invalida perfiles obsoletos"""
        engine = AppKnowledgeEngine(knowledge_base)
        
        # Crear perfil antiguo
        old_profile = create_test_profile()
        old_profile.last_seen = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        await engine.store_profile(old_profile)
        
        # Invalidar perfiles con TTL de 7 días
        invalidated = await engine.invalidate_stale(ttl_hours=168)
        
        assert invalidated >= 1
```

#### Tests para ChangeDetector
```python
class TestChangeDetector:
    async def test_detects_new_installations(self):
        """Verifica que el detector detecta instalaciones nuevas"""
        detector = ChangeDetector(discovery_service, knowledge_base)
        
        changes = await detector.scan_for_changes()
        
        assert any(c.change_type == "app_installed" for c in changes)
    
    async def test_detects_removals(self):
        """Verifica que el detector detecta eliminaciones"""
        detector = ChangeDetector(discovery_service, knowledge_base)
        
        changes = await detector.scan_for_changes()
        
        assert any(c.change_type == "app_removed" for c in changes)
    
    async def test_maintains_change_history(self):
        """Verifica que el detector mantiene historial de cambios"""
        detector = ChangeDetector(discovery_service, knowledge_base)
        
        # Simular múltiples cambios
        for i in range(5):
            await detector.scan_for_changes()
        
        history = await detector.get_change_history(limit=10)
        
        assert len(history) >= 5
```

#### Tests para EnvironmentMemory
```python
class TestEnvironmentMemory:
    async def test_stores_and_retrieves_memory(self):
        """Verifica que la memoria almacena y recupera"""
        memory = EnvironmentMemory(knowledge_base)
        
        await memory.store("preferred_editor", "VS Code", "app_preference")
        entry = await memory.retrieve("preferred_editor")
        
        assert entry is not None
        assert entry.value == "VS Code"
    
    async def test_retrieves_by_category(self):
        """Verifica que la memoria recupera por categoría"""
        memory = EnvironmentMemory(knowledge_base)
        
        await memory.store("editor", "VS Code", "app_preference")
        await memory.store("theme", "dark", "app_preference")
        
        entries = await memory.retrieve_by_category("app_preference")
        
        assert len(entries) == 2
    
    async def test_invalidates_expired_entries(self):
        """Verifica que la memoria invalida entradas expiradas"""
        memory = EnvironmentMemory(knowledge_base)
        
        # Crear entrada expirada
        await memory.store("temp", "value", "temp", ttl_seconds=1)
        await asyncio.sleep(2)
        
        cleaned = await memory.cleanup_expired()
        
        assert cleaned >= 1
```

### 6.2 Integration Tests (20%)

#### Tests de Integración con DeepContextEngine
```python
class TestDeepContextIntegration:
    async def test_deep_context_uses_discovery_service(self):
        """Verifica que DeepContext usa servicio de descubrimiento"""
        discovery = MockDiscoveryService(apps=[create_test_profile()])
        context = DeepContextEngine(app_discovery_service=discovery)
        
        ctx = await context.collect()
        
        assert "installed_apps" in ctx
        assert len(ctx["installed_apps"]) > 0
        assert discovery.was_called()
    
    async def test_deep_context_handles_discovery_failure(self):
        """Verifica que DeepContext maneja fallos de descubrimiento"""
        discovery = FailingDiscoveryService()
        context = DeepContextEngine(app_discovery_service=discovery)
        
        ctx = await context.collect()
        
        # Debe manejar fallo gracefully
        assert "installed_apps" in ctx
        assert ctx["installed_apps_count"] == 0
```

#### Tests de Integración con Planner
```python
class TestPlannerIntegration:
    async def test_planner_uses_app_knowledge(self):
        """Verifica que Planner usa conocimiento de aplicaciones"""
        knowledge = MockAppKnowledge(app_profile=create_vscode_profile())
        planner = Planner(app_knowledge=knowledge)
        
        intent = Intent(action="execute", target="editor", raw_input="abre mi editor")
        plan = await planner.plan(intent)
        
        # Debe generar plan basado en aplicación conocida
        assert any("VS Code" in step.description for step in plan.steps)
    
    async def test_planner_fallback_without_knowledge(self):
        """Verifica que Planner funciona sin conocimiento de aplicaciones"""
        planner = Planner(app_knowledge=None)
        
        intent = Intent(action="execute", target="unknown_app", raw_input="abre app")
        plan = await planner.plan(intent)
        
        # Debe usar comportamiento existente (fallback)
        assert len(plan.steps) > 0
```

#### Tests de Integración con KnowledgeBase
```python
class TestKnowledgeBaseIntegration:
    async def test_knowledge_base_supports_app_profiles(self):
        """Verifica que KnowledgeBase soporta perfiles de aplicaciones"""
        kb = KnowledgeBase(repository)
        
        profile = create_test_profile()
        await kb.store_app_profile(profile)
        
        retrieved = await kb.get_app_profile(profile.name)
        
        assert retrieved is not None
        assert retrieved.name == profile.name
    
    async def test_knowledge_base_supports_environment_memory(self):
        """Verifica que KnowledgeBase soporta memoria del entorno"""
        kb = KnowledgeBase(repository)
        
        entry = EnvironmentMemoryEntry(key="test", value="data", ...)
        await kb.store_environment_memory(entry)
        
        retrieved = await kb.get_environment_memory("test")
        
        assert retrieved is not None
        assert retrieved.value == "data"
```

### 6.3 E2E Tests (10%)

#### Tests de Flujo Completo
```python
class TestEnvironmentalLearningE2E:
    async def test_user_open_app_uses_learned_knowledge(self):
        """Verifica que usuario abrir app usa conocimiento aprendido"""
        # Primera interacción: Sentinel aprende sobre VS Code
        await trigger_app_discovery()
        
        # Segunda interacción: usuario pide abrir editor
        response = await api_sentinel_process("abre mi editor")
        
        # Debe usar conocimiento aprendido
        assert "VS Code" in response["tool_result"]["data"]["app_name"]
    
    async def test_system_detects_app_installation(self):
        """Verifica que el sistema detecta instalación de aplicación"""
        # Instalar nueva aplicación
        await install_application("Firefox")
        
        # Disparar descubrimiento
        await api_discover_apps()
        
        # Verificar que fue detectada
        apps = await api_get_known_apps()
        assert any(app["name"] == "Firefox" for app in apps["apps"])
    
    async def test_system_adapts_to_user_preferences(self):
        """Verifica que el sistema adapta a preferencias del usuario"""
        # Usuario usa consistentemente VS Code para edición
        for i in range(5):
            await api_sentinel_process("abre el editor")
        
        # Verificar que sistema aprendió preferencia
        memory = await api_get_environment_memory("preferred_editor")
        assert memory["value"] == "VS Code"
```

### 6.4 Performance Tests

```python
class TestEnvironmentalLearningPerformance:
    async def test_discovery_performance_acceptable(self):
        """Verifica que descubrimiento tiene performance aceptable"""
        service = ApplicationDiscoveryService(knowledge_base)
        
        start = time.perf_counter()
        apps = await service.discover_applications()
        elapsed = time.perf_counter() - start
        
        assert elapsed < 5.0  # Menos de 5 segundos
    
    async def test_knowledge_retrieval_performance(self):
        """Verifica que recuperación de conocimiento es rápida"""
        engine = AppKnowledgeEngine(knowledge_base)
        
        start = time.perf_counter()
        profile = await engine.get_profile("VS Code")
        elapsed = time.perf_counter() - start
        
        assert elapsed < 0.1  # Menos de 100ms
    
    async def test_change_detection_performance(self):
        """Verifica que detección de cambios es rápida"""
        detector = ChangeDetector(discovery_service, knowledge_base)
        
        start = time.perf_counter()
        changes = await detector.scan_for_changes()
        elapsed = time.perf_counter() - start
        
        assert elapsed < 2.0  # Menos de 2 segundos
```

### 6.5 Coverage Goal

- **ApplicationDiscoveryService**: >85% coverage
- **AppKnowledgeEngine**: >85% coverage
- **ChangeDetector**: >80% coverage
- **EnvironmentMemory**: >80% coverage
- **Integración**: >80% coverage
- **Total FASE 5**: >80% coverage

---

## 7. IMPLEMENTACIÓN DETALLADA

### 7.1 Semana 1: Core Application Discovery

**Objetivo**: Implementar funcionalidad básica de descubrimiento de aplicaciones

**Tareas**:
1. Crear `sentinel/services/app_discovery.py`
2. Implementar detección de aplicaciones en directorios comunes
3. Implementar análisis de ejecutables
4. Implementar generación de AppProfile
5. Unit tests básicos
6. Tests de performance de escaneo

**Entregables**:
- ApplicationDiscoveryService funcional
- Detección de aplicaciones básica funcionando
- Tests unitarios pasando
- Documentación básica

### 7.2 Semana 2: App Knowledge y Change Detection

**Objetivo**: Implementar motor de conocimiento y detector de cambios

**Tareas**:
1. Crear `sentinel/services/app_knowledge.py`
2. Crear `sentinel/services/change_detector.py`
3. Extender `sentinel/core/knowledge_base.py`
4. Implementar almacenamiento y recuperación de perfiles
5. Implementar detección de cambios
6. Integration tests con KnowledgeBase
7. Unit tests completos

**Entregables**:
- AppKnowledgeEngine funcional
- ChangeDetector funcional
- KnowledgeBase extendido
- Tests unitarios pasando

### 7.3 Semana 3: Environment Memory e Integración Completa

**Objetivo**: Implementar memoria del entorno e integración completa

**Tareas**:
1. Crear `sentinel/services/environment_memory.py`
2. Implementar `app_discovery_fn` en DeepContextEngine
3. Integrar AppKnowledge en Planner
4. Agregar endpoints API en SentinelBridge
5. E2E tests
6. Performance tests
7. Documentación completa
8. Code review

**Entregables**:
- EnvironmentMemory funcional
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
- `pathlib` (standard library)
- `hashlib` (standard library) - para file hashing
- Componentes existentes de Sentinel

### 8.2 Dependencias de Componentes

**ApplicationDiscoveryService depende de**:
- Ninguna (usa sistema operativo directamente)

**AppKnowledgeEngine depende de**:
- KnowledgeBase (inyectado)

**ChangeDetector depende de**:
- ApplicationDiscoveryService (inyectado)
- KnowledgeBase (inyectado)

**EnvironmentMemory depende de**:
- KnowledgeBase (inyectado)

### 8.3 Requisitos de Sistema

**CPU**: Impacto mínimo durante escaneo (periódico)
**RAM**: ~30MB adicional para caché de aplicaciones
**Disco**: ~5MB para código nuevo + almacenamiento de perfiles
**Red**: Sin impacto adicional

### 8.4 Requisitos de Sistema Operativo

**Windows**: Soporte completo (implementación principal)
**Linux**: Soporte mediante adaptación de rutas
**macOS**: Soporte mediante adaptación de rutas

---

## 9. MÉTRICAS DE ÉXITO

### 9.1 Métricas Técnicas

- **Coverage**: >80% para código nuevo
- **Discovery Performance**: <5s para escaneo completo
- **Knowledge Retrieval**: <100ms para recuperación de perfil
- **Change Detection**: <2s para detección de cambios
- **Memory Retrieval**: <50ms para recuperación de memoria

### 9.2 Métricas Funcionales

- **Discovery Accuracy**: >90% de aplicaciones instaladas detectadas
- **Knowledge Precision**: >95% de perfiles almacenados son correctos
- **Change Detection Rate**: >90% de cambios relevantes detectados
- **Intent Resolution**: >85% de intents de aplicaciones resueltos correctamente
- **Memory Retention**: >90% de entradas relevantes retenidas

### 9.3 Métricas de UX

- **Plan Improvement**: >80% de planes de aplicaciones son mejores que genéricos
- **User Adaptation**: >75% de preferencias de usuario aprendidas correctamente
- **Response Accuracy**: >70% de respuestas usan conocimiento del entorno

### 9.4 Métricas de Calidad

- **Bug Rate**: <3 bugs críticos durante fase 5
- **Test Pass Rate**: 100% de tests pasando al final
- **Documentation Coverage**: 100% de servicios nuevos documentados

---

## 10. PLAN DE COMUNICACIÓN

### 10.1 Stakeholders

**Usuarios**:
- Comunicar mejora en comprensión de contexto
- Explicar que el sistema aprende de sus aplicaciones
- Documentar cómo gestionar conocimiento aprendido
- Proporcionar opción de deshabilitar descubrimiento

**Desarrolladores**:
- Comunicar nueva capacidad de aprendizaje del entorno
- Documentar API para gestión de conocimiento
- Explicar patrones de uso
- Proporcionar ejemplos de integración

**QA**:
- Proporcionar criterios de aceptación
- Documentar casos de prueba de aprendizaje
- Explicar procedimientos de validación

### 10.2 Documentación Requerida

1. **Documentación de Usuario**:
   - Cómo funciona el aprendizaje del entorno
   - Qué información se aprende
   - Cómo gestionar conocimiento aprendido
   - Opciones de privacidad

2. **Documentación de Desarrollador**:
   - API para Application Discovery
   - API para App Knowledge
   - API para Environment Memory
   - Patrones de uso y extensión

3. **Documentación de Arquitectura**:
   - Diagrama de sistema de aprendizaje
   - Flujo de descubrimiento y conocimiento
   - Integración con componentes existentes

4. **Documentación de API**:
   - Nuevos endpoints para gestión de conocimiento
   - Cambios en componentes existentes
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

- [ ] Application Discovery detecta >90% de aplicaciones instaladas
- [ ] App Knowledge almacena y recupera perfiles correctamente
- [ ] Change Detector detecta >90% de cambios relevantes
- [ ] Environment Memory almacena y recupera preferencias
- [ ] Planner usa conocimiento de aplicaciones cuando disponible
- [ ] DeepContextEngine usa servicio de descubrimiento real

### 11.3 Criterios de Performance

- [ ] Discovery performance <5s (100%)
- [ ] Knowledge retrieval <100ms (100%)
- [ ] Change detection <2s (100%)
- [ ] No degradación significativa de performance del sistema (<10%)

### 11.4 Criterios de Privacidad

- [ ] Solo se almacenan metadatos técnicos de aplicaciones
- [ ] No se almacena historial de uso sin consentimiento
- [ ] Opción para deshabilitar descubrimiento funciona
- [ ] Política de retención clara y documentada
- [ ] Datos pueden ser eliminados por usuario

### 11.5 Criterios de Calidad

- [ ] Documentación completa y precisa
- [ ] Código sigue convenciones del proyecto
- [ ] Sin warnings de linter
- [ ] Sin vulnerabilidades de seguridad introducidas
- [ ] Compatible con versiones existentes

---

## 12. CONFIRMACIÓN REQUERIDA

Antes de proceder con la implementación de FASE 5, confirmar:

1. **¿Aprobar el plan de implementación propuesto?**
2. **¿Están de acuerdo con la estrategia de testing de privacidad?**
3. **¿Los criterios de aceptación (incluyendo privacidad) son apropiados?**
4. **¿Algún ajuste requerido antes de comenzar la implementación?**

---

## 13. CONSIDERACIONES ESPECIALES

### 13.1 Privacidad

**Consideración**: Respetar privacidad del usuario
- Solo almacenar metadatos técnicos (nombre, ruta, versión, capacidades)
- No almacenar historial de uso sin consentimiento explícito
- Proporcionar opción para deshabilitar descubrimiento completamente
- Implementar eliminación completa de conocimiento aprendido
- Política de retención clara (por ejemplo, 30 días para apps no usadas)

### 13.2 Multi-Plataforma

**Consideración**: Soportar diferentes sistemas operativos
- Implementar detección específica por plataforma
- Adaptar rutas comunes para Windows, Linux, macOS
- Tests de compatibilidad cruzada
- Documentación para cada plataforma

### 13.3 Compatibilidad con FASE 2, 3, 4

**Consideración**: Integración con cambios anteriores
- Application Discovery debe trabajar con Grounding de FASE 2
- Presentation Layer de FASE 3 debe filtrar detalles de aprendizaje
- Decision Engine de FASE 4 debe considerar conocimiento del entorno

### 13.4 Escalabilidad

**Consideración**: Manejar sistemas con muchas aplicaciones
- Implementar escaneo diferencial (no escanear todo el sistema)
- Caché inteligente de resultados de descubrimiento
- Lazy loading de detalles de aplicaciones
- Paginación en endpoints API

---

**DOCUMENTO FASE_5_ARCHITECTURE_IMPACT.md COMPLETADO**

Este documento detalla el impacto arquitectónico de implementar el Environmental Learning en FASE 5, incluyendo archivos afectados, nivel de riesgo MEDIO, estrategia de rollback y plan de testing con énfasis en privacidad y funcionalidad.

**ESTADO**: Pendiente de aprobación antes de implementación.
