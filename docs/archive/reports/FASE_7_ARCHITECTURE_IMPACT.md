# FASE 7: RELIABLE MEMORY - ARCHITECTURE IMPACT

**Fecha**: 2025-01-17
**Fase**: 7 - Reliable Memory
**Prioridad**: ALTA
**Duración Estimada**: 2 semanas
**Estado**: Pendiente de aprobación

---

## 1. PROPÓSITO

Implementar un sistema de memoria confiable con metadata de fuente, fecha, confianza y contexto que permita a Sentinel saber "No recuerdo esto con certeza" en lugar de inventar, separando diferentes tipos de memoria (usuario, sistema, temporal, conocimiento) y proporcionando mecanismos de invalidación.

**Objetivo**: Toda memoria debe tener fuente, fecha, confianza, contexto y posibilidad de invalidación. Sentinel debe expresar incertidumbre cuando no está seguro en lugar de alucinar.

---

## 2. ARCHITECTURE IMPACT

### 2.1 Nuevo Componente: Reliable Memory

**Archivo**: `sentinel/core/reliable_memory.py` (NUEVO)
**Responsabilidad**: 
- Sistema de memoria con metadatos de confianza
- Separación por tipos de memoria (USER, SYSTEM, TEMPORAL, KNOWLEDGE)
- Validación de confianza antes de retornar datos
- Sistema de invalidación de memoria
- Gestión de TTL y expiración

**Dependencias**:
- MemoryBackend (para almacenamiento)

**Interfaces Públicas**:
```python
class MemoryType(Enum):
    USER = "user"           # Preferencias, historial de usuario
    SYSTEM = "system"       # Conocimiento del sistema
    TEMPORAL = "temporal"   # Contexto de sesión actual
    KNOWLEDGE = "knowledge" # Conocimiento verificable

@dataclass
class MemoryMetadata:
    """Metadata para entradas de memoria"""
    source: str  # 'user_input', 'tool_result', 'llm_generation', 'system_scan'
    timestamp: str
    confidence: float  # 0.0 a 1.0
    context: Dict[str, Any]
    invalidatable: bool
    ttl_seconds: Optional[float]
    memory_type: MemoryType
    access_count: int = 0
    last_accessed: Optional[str] = None

@dataclass
class MemoryEntry:
    """Entrada de memoria con metadata"""
    key: str
    value: Any
    metadata: MemoryMetadata

class ReliableMemory:
    def __init__(self, backend: MemoryBackend)
    async def store(self, key: str, value: Any, metadata: MemoryMetadata) -> None
    async def retrieve(self, key: str, min_confidence: float = 0.5) -> Optional[Tuple[Any, MemoryMetadata]]
    async def retrieve_by_type(self, memory_type: MemoryType, min_confidence: float = 0.5) -> List[MemoryEntry]
    async def search(self, pattern: str, memory_type: Optional[MemoryType] = None) -> List[MemoryEntry]
    async def invalidate(self, key: str, reason: str) -> None
    async def invalidate_by_type(self, memory_type: MemoryType, reason: str) -> int
    async def invalidate_by_source(self, source: str, reason: str) -> int
    async def invalidate_stale(self) -> int
    async def get_uncertain_memories(self, confidence_threshold: float = 0.5) -> List[MemoryEntry]
    async def update_confidence(self, key: str, new_confidence: float, reason: str) -> None
    async def get_memory_stats(self) -> Dict[str, Any]
    def should_trust(self, metadata: MemoryMetadata) -> bool
```

### 2.2 Nuevo Componente: Memory Validator

**Archivo**: `sentinel/core/memory_validator.py` (NUEVO)
**Responsabilidad**: 
- Validar datos antes de almacenar en memoria
- Verificar integridad de datos
- Detectar anomalías en memoria
- Validar metadata de confianza

**Dependencias**:
- Ninguna (self-contained)

**Interfaces Públicas**:
```python
class MemoryValidator:
    def __init__(self)
    def validate_value(self, value: Any, memory_type: MemoryType) -> Tuple[bool, List[str]]
    def validate_metadata(self, metadata: MemoryMetadata) -> Tuple[bool, List[str]]
    def validate_confidence(self, confidence: float, source: str) -> Tuple[bool, str]
    def detect_anomalies(self, entries: List[MemoryEntry]) -> List[str]
    def should_invalidate(self, entry: MemoryEntry) -> Tuple[bool, str]
```

### 2.3 Nuevo Componente: Memory Conflict Resolver

**Archivo**: `sentinel/core/memory_conflict_resolver.py` (NUEVO)
**Responsabilidad**: 
- Resolver conflictos cuando hay múltiples entradas para el mismo key
- Fusionar entradas basado en confianza y fuente
- Detectar inconsistencias en memoria
- Proponer resoluciones de conflictos

**Dependencias**:
- ReliableMemory (para acceso a memoria)

**Interfaces Públicas**:
```python
@dataclass
class MemoryConflict:
    """Conflicto detectado en memoria"""
    key: str
    entries: List[MemoryEntry]
    conflict_type: str  # 'value_mismatch', 'confidence_conflict', 'source_conflict'
    detected_at: str
    severity: str  # 'low', 'medium', 'high'

@dataclass
class ConflictResolution:
    """Resolución de conflicto"""
    key: str
    resolved_entry: Optional[MemoryEntry]
    action: str  # 'merge', 'keep_highest_confidence', 'keep_most_recent', 'invalidate_all'
    reason: str

class MemoryConflictResolver:
    def __init__(self, memory: ReliableMemory)
    async def detect_conflicts(self) -> List[MemoryConflict]
    async def resolve_conflict(self, conflict: MemoryConflict) -> ConflictResolution
    async def auto_resolve_conflicts(self) -> List[ConflictResolution]
    def calculate_confidence_delta(self, entries: List[MemoryEntry]) -> float
```

### 2.4 Modificación: Memory Backend

**Archivo**: `sentinel/core/operational_memory.py`
**Cambio**: Extender para soportar MemoryMetadata

**Cambio Específico**:
```python
# ANTES
async def store(self, key: str, value: Any, category: Optional[str] = None) -> None:
    """Almacena un valor en memoria"""
    entry = MemoryEntry(key=key, value=value, timestamp=datetime.now(timezone.utc).isoformat())
    await self._repository.store(key, entry.to_dict(), category=category)

async def retrieve(self, key: str) -> Optional[Any]:
    """Recupera un valor de memoria"""
    data = await self._repository.retrieve(key)
    if data:
        entry = MemoryEntry.from_dict(data)
        return entry.value
    return None

# DESPUÉS
async def store(self, key: str, value: Any, category: Optional[str] = None, metadata: Optional[MemoryMetadata] = None) -> None:
    """Almacena un valor en memoria con metadata opcional"""
    if metadata:
        entry = MemoryEntry(key=key, value=value, metadata=metadata)
    else:
        # Compatibilidad: metadata opcional
        entry = MemoryEntry(
            key=key, 
            value=value, 
            metadata=MemoryMetadata(
                source="legacy",
                timestamp=datetime.now(timezone.utc).isoformat(),
                confidence=0.5,
                context={},
                invalidatable=True,
                ttl_seconds=None,
                memory_type=MemoryType.TEMPORAL
            )
        )
    await self._repository.store(key, entry.to_dict(), category=category)

async def retrieve(self, key: str) -> Optional[Tuple[Any, Optional[MemoryMetadata]]]:
    """Recupera un valor de memoria con metadata"""
    data = await self._repository.retrieve(key)
    if data:
        entry = MemoryEntry.from_dict(data)
        return entry.value, entry.metadata
    return None, None

async def retrieve_with_metadata(self, key: str) -> Optional[MemoryEntry]:
    """Recupera entrada completa con metadata"""
    data = await self._repository.retrieve(key)
    if data:
        return MemoryEntry.from_dict(data)
    return None
```

**Integración**:
- Extiende MemoryBackend existente
- Metadata es opcional (compatibilidad con código existente)
- Métodos nuevos para acceder a metadata

### 2.5 Modificación: Knowledge Base

**Archivo**: `sentinel/core/knowledge_base.py`
**Cambio**: Integrar con Reliable Memory

**Cambio Específico**:
```python
# EN __init__
def __init__(self, ...):
    # ... código existente ...
    self._reliable_memory = None  # NUEVO

def set_reliable_memory(self, memory: ReliableMemory) -> None:
    """Configura Reliable Memory"""
    self._reliable_memory = memory

# EN métodos de almacenamiento/recuperación
async def store_knowledge(self, key: str, value: Any, source: str = "user") -> None:
    """Almacena conocimiento con metadata de confianza"""
    if self._reliable_memory:
        metadata = MemoryMetadata(
            source=source,
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=0.8 if source == "tool" else 0.5,
            context={"type": "knowledge"},
            invalidatable=True,
            ttl_seconds=None,
            memory_type=MemoryType.KNOWLEDGE
        )
        await self._reliable_memory.store(key, value, metadata)
    else:
        # Fallback a comportamiento existente
        await self._repository.store(key, value, category="knowledge")

async def retrieve_knowledge(self, key: str) -> Optional[Tuple[Any, MemoryMetadata]]:
    """Recupera conocimiento con metadata"""
    if self._reliable_memory:
        return await self._reliable_memory.retrieve(key, min_confidence=0.5)
    else:
        # Fallback a comportamiento existente
        data = await self._repository.retrieve(key)
        return data, None
```

**Integración**:
- KnowledgeBase puede usar Reliable Memory
- Fallback a comportamiento existente si no está configurado
- Metadata de confianza para conocimiento

### 2.6 Modificación: Orchestrator

**Archivo**: `sentinel/core/orchestrator.py`
**Cambio**: Usar Reliable Memory para almacenamiento con metadata

**Cambio Específico**:
```python
# EN __init__
def __init__(self, ...):
    # ... código existente ...
    self._reliable_memory = None  # NUEVO

def set_reliable_memory(self, memory: ReliableMemory) -> None:
    """Configura Reliable Memory"""
    self._reliable_memory = memory
    if self._knowledge_base:
        self._knowledge_base.set_reliable_memory(memory)

# EN process() - cuando almacena resultados
async def process(self, utterance: str, ...) -> ExecutionResult:
    # ... código existente ...
    
    # NUEVO: Almacenar resultado con metadata
    if self._reliable_memory and result.tool_result and result.tool_result.success:
        metadata = MemoryMetadata(
            source="tool_result",
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=0.9,  # Alta confianza para resultados de herramientas
            context={
                "intent": intent.action,
                "target": intent.target,
                "tool": result.tool_result.tool_id,
            },
            invalidatable=True,
            ttl_seconds=3600,  # 1 hora para resultados temporales
            memory_type=MemoryType.TEMPORAL
        )
        await self._reliable_memory.store(
            f"result:{intent.action}:{intent.target}",
            result.tool_result.data,
            metadata
        )
    
    return result
```

**Integración**:
- Orchestrator puede usar Reliable Memory
- Metadata apropiada para diferentes tipos de datos
- Fallback a comportamiento existente

### 2.7 Nuevo Endpoint API

**Archivo**: `sidecar/modules/sentinel_bridge.py`
**Cambio**: Agregar endpoints para gestión de memoria confiable

**Cambio Específico**:
```python
# NUEVO: Endpoint para obtener memoria con metadata
@router.get("/sentinel/memory")
async def get_memory(key: str = Query(...)):
    """Retorna entrada de memoria con metadata"""
    from modules import get_reliable_memory
    
    memory = get_reliable_memory()
    if not memory:
        return {"error": "Reliable memory not available"}
    
    entry = await memory.retrieve(key)
    if entry:
        value, metadata = entry
        return {
            "key": key,
            "value": value,
            "metadata": metadata.to_dict(),
            "trusted": memory.should_trust(metadata)
        }
    else:
        return {"error": "Key not found"}

# NUEVO: Endpoint para buscar memoria
@router.get("/sentinel/memory/search")
async def search_memory(pattern: str = Query(...), memory_type: Optional[str] = Query(None)):
    """Busca entradas de memoria"""
    from modules import get_reliable_memory
    
    memory = get_reliable_memory()
    if not memory:
        return {"error": "Reliable memory not available"}
    
    mem_type = MemoryType(memory_type) if memory_type else None
    entries = await memory.search(pattern, memory_type=mem_type)
    
    return {
        "pattern": pattern,
        "results": [
            {
                "key": e.key,
                "value": e.value,
                "metadata": e.metadata.to_dict(),
                "trusted": memory.should_trust(e.metadata)
            }
            for e in entries
        ]
    }

# NUEVO: Endpoint para invalidar memoria
@router.post("/sentinel/memory/invalidate")
async def invalidate_memory(body: dict, request: Request):
    """Invalida entradas de memoria"""
    from modules import get_reliable_memory
    
    memory = get_reliable_memory()
    if not memory:
        return {"error": "Reliable memory not available"}
    
    key = body.get("key")
    reason = body.get("reason", "manual_invalidation")
    
    if key:
        await memory.invalidate(key, reason)
        return {"status": "invalidated", "key": key}
    else:
        return {"error": "Key required"}

# NUEVO: Endpoint para obtener memorias inciertas
@router.get("/sentinel/memory/uncertain")
async def get_uncertain_memory(threshold: float = Query(0.5)):
    """Retorna memorias con baja confianza"""
    from modules import get_reliable_memory
    
    memory = get_reliable_memory()
    if not memory:
        return {"error": "Reliable memory not available"}
    
    entries = await memory.get_uncertain_memories(confidence_threshold=threshold)
    
    return {
        "threshold": threshold,
        "count": len(entries),
        "entries": [
            {
                "key": e.key,
                "confidence": e.metadata.confidence,
                "source": e.metadata.source,
                "timestamp": e.metadata.timestamp
            }
            for e in entries
        ]
}

# NUEVO: Endpoint para obtener estadísticas de memoria
@router.get("/sentinel/memory/stats")
async def get_memory_stats():
    """Retorna estadísticas de memoria"""
    from modules import get_reliable_memory
    
    memory = get_reliable_memory()
    if not memory:
        return {"error": "Reliable memory not available"}
    
    stats = await memory.get_memory_stats()
    return stats
```

---

## 3. FILES AFFECTED

### 3.1 Nuevos Archivos

1. **`sentinel/core/reliable_memory.py`** (NUEVO)
   - ~500 líneas estimadas
   - Sistema de memoria confiable con metadata
   - Depende de: MemoryBackend

2. **`sentinel/core/memory_validator.py`** (NUEVO)
   - ~300 líneas estimadas
   - Validador de datos y metadata
   - Sin dependencias críticas

3. **`sentinel/core/memory_conflict_resolver.py`** (NUEVO)
   - ~350 líneas estimadas
   - Resolvedor de conflictos de memoria
   - Depende de: ReliableMemory

4. **`tests/test_reliable_memory.py`** (NUEVO)
   - ~400 líneas estimadas
   - Tests de memoria confiable

5. **`tests/test_memory_validator.py`** (NUEVO)
   - ~250 líneas estimadas
   - Tests de validador

6. **`tests/test_memory_conflict_resolver.py`** (NUEVO)
   - ~300 líneas estimadas
   - Tests de resolvedor de conflictos

### 3.2 Archivos Modificados

1. **`sentinel/core/operational_memory.py`**
   - Cambio: Extender para soportar MemoryMetadata
   - Líneas afectadas: ~50-70
   - Riesgo: BAJO (extensión aditiva con fallback)

2. **`sentinel/core/knowledge_base.py`**
   - Cambio: Integrar con Reliable Memory
   - Líneas afectadas: ~40-60
   - Riesgo: BAJO (integración opcional con fallback)

3. **`sentinel/core/orchestrator.py`**
   - Cambio: Usar Reliable Memory para almacenamiento
   - Líneas afectadas: ~30-50
   - Riesgo: BAJO (integración opcional con fallback)

### 3.3 Archivos Sin Cambios

Todos los demás archivos permanecen sin cambios para mantener compatibilidad.

---

## 4. RISK LEVEL

### 4.1 Riesgo General: MEDIO

**Justificación**:
- Componentes nuevos sin dependencias críticas
- Cambios en componentes existentes son integrativos (con fallback)
- Metadata es opcional (compatibilidad con código existente)
- Puede deshabilitarse mediante configuración
- No cambia interfaces principales de ejecución

### 4.2 Riesgos Específicos

#### RIESGO 1: Memory Bloat
**Severidad**: MEDIA
**Probabilidad**: MEDIA
**Impacto: Almacenar metadata adicional puede aumentar tamaño de memoria
**Mitigación**:
- TTL para todas las entradas
- Limpieza automática de entradas expiradas
- Compresión de metadata si es necesario
- Límites de tamaño por entrada

#### RIESGO 2: Performance Impact por Validación
**Severidad**: BAJA
**Probabilidad**: BAJA
**Impacto: Validación de metadata puede agregar latencia
**Mitigación**:
- Validación asíncrona cuando sea posible
- Caché de validaciones repetitivas
- Validación opcional (puede deshabilitarse)
- Métricas de performance en tests

#### RIESGO 3: Incorrect Confidence Scoring
**Severidad**: MEDIA
**Probabilidad**: MEDIA
**Impacto: Scores de confianza incorrectos pueden afectar decisiones
**Mitigación**:
- Heurísticas conservadoras para scoring
- Validación de scores por fuente
- Ajuste de scores basado en feedback
- Logging extenso para debugging

#### RIESGO 4: Conflict Resolution Errors
**Severidad**: MEDIA
**Probabilidad**: BAJA
**Impacto: Resolución incorrecta de conflictos puede causar pérdida de datos
**Mitigación**:
- Resolución manual disponible
- Backup de entradas antes de resolución
- Logging de todas las resoluciones
- Reversión de resoluciones si es necesario

#### RIESGO 5: Integration with Existing Memory

**Severidad**: BAJA
**Probabilidad**: BAJA
**Impacto: Integración puede afectar comportamiento existente
**Mitigación**:
- Fallback a comportamiento existente
- Tests exhaustivos de integración
- Feature flag para deshabilitar rápidamente
- Comparación con comportamiento anterior

---

## 5. ROLLBACK STRATEGY

### 5.1 Rollback Plan A: Deshabilitar Reliable Memory

**Trigger**: Problemas con memoria confiable o validación
**Acción**:
```python
# En Orchestrator.__init__
if config.get("enable_reliable_memory", False):  # Default False
    self._reliable_memory = ReliableMemory(memory_backend)
else:
    self._reliable_memory = None

# En KnowledgeBase
if config.get("enable_reliable_memory", False):
    self._reliable_memory = memory
else:
    self._reliable_memory = None
```

**Tiempo**: <5 minutos
**Impacto**: Sistema usa memoria tradicional sin metadata
**Riesgo**: Ninguno

### 5.2 Rollback Plan B: Deshabilitar Validación

**Trigger**: Problemas con validación de datos
**Acción**:
```python
# En ReliableMemory
if config.get("enable_memory_validation", False):
    self._validator = MemoryValidator()
else:
    self._validator = None
```

**Tiempo**: <5 minutos
**Impacto: Sistema almacena sin validación adicional
**Riesgo**: Bajo

### 5.3 Rollback Plan C: Revertir Integración

**Trigger**: Problemas de integración con componentes existentes
**Acción**:
- Revertir cambios en operational_memory.py
- Revertir cambios en knowledge_base.py
- Revertir cambios en orchestrator.py
- Mantener componentes nuevos para futuro uso

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

#### Tests para ReliableMemory
```python
class TestReliableMemory:
    async def test_stores_and_retrieves_with_metadata(self):
        """Verifica que memoria almacena y recupera con metadata"""
        memory = ReliableMemory(backend)
        metadata = MemoryMetadata(
            source="test",
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=0.8,
            context={},
            invalidatable=True,
            ttl_seconds=None,
            memory_type=MemoryType.USER
        )
        
        await memory.store("test_key", "test_value", metadata)
        result = await memory.retrieve("test_key")
        
        assert result is not None
        value, retrieved_metadata = result
        assert value == "test_value"
        assert retrieved_metadata.confidence == 0.8
    
    async def test_retrieves_only_if_meets_min_confidence(self):
        """Verifica que retrieve solo retorna si cumple confianza mínima"""
        memory = ReliableMemory(backend)
        
        # Almacenar con baja confianza
        low_conf_metadata = MemoryMetadata(..., confidence=0.3)
        await memory.store("low_conf", "value", low_conf_metadata)
        
        # Intentar recuperar con confianza mínima de 0.5
        result = await memory.retrieve("low_conf", min_confidence=0.5)
        
        assert result is None  # No debe retornar entrada con baja confianza
    
    async def test_invalidates_entry(self):
        """Verifica que invalidación funciona"""
        memory = ReliableMemory(backend)
        metadata = MemoryMetadata(..., invalidatable=True)
        
        await memory.store("test_key", "value", metadata)
        await memory.invalidate("test_key", "test_reason")
        
        result = await memory.retrieve("test_key")
        assert result is None
    
    async def test_invalidates_by_type(self):
        """Verifica que invalidación por tipo funciona"""
        memory = ReliableMemory(backend)
        
        await memory.store("user_1", "value", MemoryMetadata(..., memory_type=MemoryType.USER))
        await memory.store("system_1", "value", MemoryMetadata(..., memory_type=MemoryType.SYSTEM))
        
        invalidated = await memory.invalidate_by_type(MemoryType.USER, "test")
        
        assert invalidated == 1
        assert await memory.retrieve("user_1") is None
        assert await memory.retrieve("system_1") is not None
    
    async def test_invalidates_stale_entries(self):
        """Verifica que invalidación de entradas obsoletas funciona"""
        memory = ReliableMemory(backend)
        
        # Crear entrada expirada
        stale_metadata = MemoryMetadata(..., ttl_seconds=1)
        await memory.store("stale", "value", stale_metadata)
        await asyncio.sleep(2)
        
        invalidated = await memory.invalidate_stale()
        
        assert invalidated >= 1
    
    async def test_gets_uncertain_memories(self):
        """Verifica que obtiene memorias con baja confianza"""
        memory = ReliableMemory(backend)
        
        await memory.store("certain", "value", MemoryMetadata(..., confidence=0.9))
        await memory.store("uncertain", "value", MemoryMetadata(..., confidence=0.3))
        
        uncertain = await memory.get_uncertain_memories(confidence_threshold=0.5)
        
        assert len(uncertain) == 1
        assert uncertain[0].key == "uncertain"
    
    async def test_updates_confidence(self):
        """Verifica que actualización de confianza funciona"""
        memory = ReliableMemory(backend)
        metadata = MemoryMetadata(..., confidence=0.5)
        
        await memory.store("test", "value", metadata)
        await memory.update_confidence("test", 0.9, "validated_by_tool")
        
        result = await memory.retrieve("test")
        assert result[1].confidence == 0.9
    
    def test_should_trust_based_on_confidence(self):
        """Verifica que should_trust funciona basado en confianza"""
        memory = ReliableMemory(backend)
        
        high_conf_metadata = MemoryMetadata(..., confidence=0.9)
        low_conf_metadata = MemoryMetadata(..., confidence=0.3)
        
        assert memory.should_trust(high_conf_metadata) == True
        assert memory.should_trust(low_conf_metadata) == False
```

#### Tests para MemoryValidator
```python
class TestMemoryValidator:
    def test_validates_value_correctly(self):
        """Verifica que validador valida valores correctamente"""
        validator = MemoryValidator()
        
        valid, errors = validator.validate_value("test_value", MemoryType.USER)
        assert valid == True
        assert len(errors) == 0
    
    def test_rejects_invalid_values(self):
        """Verifica que validador rechaza valores inválidos"""
        validator = MemoryValidator()
        
        # Valor nulo no debería ser válido para ciertos tipos
        valid, errors = validator.validate_value(None, MemoryType.KNOWLEDGE)
        assert valid == False
        assert len(errors) > 0
    
    def test_validates_metadata_correctly(self):
        """Verifica que validador valida metadata correctamente"""
        validator = MemoryValidator()
        
        metadata = MemoryMetadata(
            source="test",
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=0.8,
            context={},
            invalidatable=True,
            ttl_seconds=None,
            memory_type=MemoryType.USER
        )
        
        valid, errors = validator.validate_metadata(metadata)
        assert valid == True
    
    def test_rejects_invalid_confidence(self):
        """Verifica que validador rechaza confianza inválida"""
        validator = MemoryValidator()
        
        valid, reason = validator.validate_confidence(1.5, "test")  # Fuera de rango
        assert valid == False
        
        valid, reason = validator.validate_confidence(-0.1, "test")  # Fuera de rango
        assert valid == False
    
    def test_detects_anomalies(self):
        """Verifica que validador detecta anomalías"""
        validator = MemoryValidator()
        
        entries = [
            MemoryEntry("key1", "value1", MemoryMetadata(..., confidence=0.9)),
            MemoryEntry("key1", "value2", MemoryMetadata(..., confidence=0.9)),  # Duplicado con valor diferente
        ]
        
        anomalies = validator.detect_anomalies(entries)
        assert len(anomalies) > 0
```

#### Tests para MemoryConflictResolver
```python
class TestMemoryConflictResolver:
    async def test_detects_value_conflicts(self):
        """Verifica que detector detecta conflictos de valor"""
        memory = ReliableMemory(backend)
        resolver = MemoryConflictResolver(memory)
        
        # Almacenar dos entradas con mismo key pero diferentes valores
        await memory.store("key", "value1", MemoryMetadata(..., confidence=0.8))
        await memory.store("key", "value2", MemoryMetadata(..., confidence=0.7))
        
        conflicts = await resolver.detect_conflicts()
        
        assert len(conflicts) > 0
        assert conflicts[0].conflict_type == "value_mismatch"
    
    async def test_resolves_conflict_by_highest_confidence(self):
        """Verifica que resuelve conflicto por confianza más alta"""
        memory = ReliableMemory(backend)
        resolver = MemoryConflictResolver(memory)
        
        conflict = MemoryConflict(
            key="test",
            entries=[
                MemoryEntry("test", "value1", MemoryMetadata(..., confidence=0.9)),
                MemoryEntry("test", "value2", MemoryMetadata(..., confidence=0.7)),
            ],
            conflict_type="value_mismatch",
            detected_at=datetime.now(timezone.utc).isoformat(),
            severity="medium"
        )
        
        resolution = await resolver.resolve_conflict(conflict)
        
        assert resolution.action == "keep_highest_confidence"
        assert resolution.resolved_entry.metadata.confidence == 0.9
    
    async def test_auto_resolves_conflicts(self):
        """Verifica que auto-resolución funciona"""
        memory = ReliableMemory(backend)
        resolver = MemoryConflictResolver(memory)
        
        # Crear conflictos
        await memory.store("key1", "value1", MemoryMetadata(..., confidence=0.8))
        await memory.store("key1", "value2", MemoryMetadata(..., confidence=0.7))
        
        resolutions = await resolver.auto_resolve_conflicts()
        
        assert len(resolutions) > 0
        assert all(r.action in ["keep_highest_confidence", "keep_most_recent"] for r in resolutions)
```

### 6.2 Integration Tests (20%)

#### Tests de Integración con MemoryBackend
```python
class TestMemoryBackendIntegration:
    async def test_backend_supports_metadata(self):
        """Verifica que MemoryBackend soporta metadata"""
        backend = MemoryBackend(repository)
        metadata = MemoryMetadata(
            source="test",
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=0.8,
            context={},
            invalidatable=True,
            ttl_seconds=None,
            memory_type=MemoryType.USER
        )
        
        await backend.store("test", "value", metadata=metadata)
        result = await backend.retrieve_with_metadata("test")
        
        assert result is not None
        assert result.metadata.confidence == 0.8
    
    async def test_backward_compatibility_without_metadata(self):
        """Verifica compatibilidad backward sin metadata"""
        backend = MemoryBackend(repository)
        
        # Almacenar sin metadata (comportamiento antiguo)
        await backend.store("test", "value")
        result = await backend.retrieve("test")
        
        # Debe funcionar
        assert result is not None
```

#### Tests de Integración con KnowledgeBase
```python
class TestKnowledgeBaseIntegration:
    async def test_knowledge_base_uses_reliable_memory(self):
        """Verifica que KnowledgeBase usa Reliable Memory"""
        backend = MemoryBackend(repository)
        reliable_memory = ReliableMemory(backend)
        kb = KnowledgeBase(repository)
        kb.set_reliable_memory(reliable_memory)
        
        await kb.store_knowledge("test", "value", source="tool")
        
        result = await kb.retrieve_knowledge("test")
        
        assert result is not None
        assert result[1].source == "tool"
        assert result[1].memory_type == MemoryType.KNOWLEDGE
    
    async def test_knowledge_base_fallback_without_reliable_memory(self):
        """Verifica que KnowledgeBase fallback sin Reliable Memory"""
        kb = KnowledgeBase(repository)
        # Sin Reliable Memory configurado
        
        await kb.store_knowledge("test", "value")
        result = await kb.retrieve_knowledge("test")
        
        # Debe funcionar con comportamiento tradicional
        assert result is not None
```

#### Tests de Integración con Orchestrator
```python
class TestOrchestratorIntegration:
    async def test_orchestrator_uses_reliable_memory(self):
        """Verifica que Orchestrator usa Reliable Memory"""
        orchestrator = create_test_orchestrator()
        reliable_memory = ReliableMemory(backend)
        orchestrator.set_reliable_memory(reliable_memory)
        
        # Ejecutar una acción
        result = await orchestrator.process("test query")
        
        # Verificar que se almacenó con metadata
        if result.tool_result and result.tool_result.success:
            memory_entry = await reliable_memory.retrieve("result:query:test")
            assert memory_entry is not None
            assert memory_entry[1].source == "tool_result"
```

### 6.3 E2E Tests (10%)

#### Tests de Flujo Completo
```python
class TestReliableMemoryE2E:
    async def test_system_expresses_uncertainty_when_unsure(self):
        """Verifica que sistema expresa incertidumbre cuando no está seguro"""
        # Almacenar información con baja confianza
        await api_store_memory("uncertain_fact", "some_value", confidence=0.3)
        
        # Consultar la información
        response = await api_sentinel_process("¿Qué es uncertain_fact?")
        
        # Debe expresar incertidumbre
        assert "no estoy seguro" in response["response"].lower() or "no recuerdo con certeza" in response["response"].lower()
    
    async def test_system_trusts_high_confidence_memory(self):
        """Verifica que sistema confía en memoria con alta confianza"""
        # Almacenar información con alta confianza
        await api_store_memory("certain_fact", "value", confidence=0.9, source="tool")
        
        response = await api_sentinel_process("¿Qué es certain_fact?")
        
        # Debe confiar y usar la información
        assert "value" in response["response"]
        assert "no estoy seguro" not in response["response"].lower()
    
    async def test_user_can_invalidate_memory(self):
        """Verifica que usuario puede invalidar memoria"""
        # Almacenar información
        await api_store_memory("fact", "value")
        
        # Invalidar
        await api_invalidate_memory("fact", reason="user_requested")
        
        # Verificar que fue invalidada
        result = await api_get_memory("fact")
        assert "error" in result  # No debe existir
```

### 6.4 Performance Tests

```python
class TestReliableMemoryPerformance:
    async def test_storage_with_metadata_performance(self):
        """Verifica que almacenamiento con metadata tiene performance aceptable"""
        memory = ReliableMemory(backend)
        metadata = MemoryMetadata(...)
        
        start = time.perf_counter()
        await memory.store("test", "value", metadata)
        elapsed = time.perf_counter() - start
        
        assert elapsed < 0.1  # Menos de 100ms
    
    async def test_retrieval_with_confidence_check_performance(self):
        """Verifica que recuperación con check de confianza es rápida"""
        memory = ReliableMemory(backend)
        await memory.store("test", "value", MemoryMetadata(...))
        
        start = time.perf_counter()
        result = await memory.retrieve("test", min_confidence=0.5)
        elapsed = time.perf_counter() - start
        
        assert elapsed < 0.05  # Menos de 50ms
    
    async def test_invalidation_performance(self):
        """Verifica que invalidación es rápida"""
        memory = ReliableMemory(backend)
        await memory.store("test", "value", MemoryMetadata(...))
        
        start = time.perf_counter()
        await memory.invalidate("test", "test")
        elapsed = time.perf_counter() - start
        
        assert elapsed < 0.05  # Menos de 50ms
```

### 6.5 Coverage Goal

- **ReliableMemory**: >90% coverage (componente crítico)
- **MemoryValidator**: >85% coverage
- **MemoryConflictResolver**: >80% coverage
- **Integración**: >80% coverage
- **Total FASE 7**: >85% coverage (más alto por ser la última fase y componente crítico)

---

## 7. IMPLEMENTACIÓN DETALLADA

### 7.1 Semana 1: Core Reliable Memory

**Objetivo**: Implementar sistema de memoria confiable básico

**Tareas**:
1. Crear `sentinel/core/reliable_memory.py`
2. Implementar MemoryType enum
3. Implementar MemoryMetadata dataclass
4. Implementar ReliableMemory con métodos básicos
5. Implementar validación de confianza
6. Implementar invalidación
7. Unit tests básicos
8. Tests de performance

**Entregables**:
- ReliableMemory funcional
- Metadata de confianza implementada
- Tests unitarios pasando
- Documentación básica

### 7.2 Semana 2: Validación, Conflictos e Integración Completa

**Objetivo**: Implementar validación, resolución de conflictos e integración completa

**Tareas**:
1. Crear `sentinel/core/memory_validator.py`
2. Crear `sentinel/core/memory_conflict_resolver.py`
3. Extender `sentinel/core/operational_memory.py`
4. Integrar en `sentinel/core/knowledge_base.py`
5. Integrar en `sentinel/core/orchestrator.py`
6. Agregar endpoints API
7. Integration tests completos
8. E2E tests
9. Performance tests
10. Documentación completa
11. Code review

**Entregables**:
- Validador y resolvedor funcionales
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
- `datetime` (standard library)
- Componentes existentes de Sentinel

### 8.2 Dependencias de Componentes

**ReliableMemory depende de**:
- MemoryBackend (inyectado)

**MemoryValidator depende de**:
- Ninguna (self-contained)

**MemoryConflictResolver depende de**:
- ReliableMemory (inyectado)

### 8.3 Requisitos de Sistema

**CPU**: Sin impacto adicional significativo
**RAM**: ~40MB adicional para metadata y caché
**Disco**: ~5MB para código nuevo + almacenamiento de metadata
**Red**: Sin impacto adicional

---

## 9. MÉTRICAS DE ÉXITO

### 9.1 Métricas Técnicas

- **Coverage**: >85% para código nuevo (más alto por ser última fase)
- **Storage Performance**: <100ms para almacenamiento con metadata
- **Retrieval Performance**: <50ms para recuperación con check de confianza
- **Invalidation Performance**: <50ms para invalidación
- **Validation Performance**: <10ms para validación de metadata

### 9.2 Métricas Funcionales

- **Metadata Accuracy**: >95% de metadata almacenada correctamente
- **Confidence Scoring Accuracy**: >90% de scores de confianza apropiados
- **Conflict Detection Rate**: >85% de conflictos detectados
- **Conflict Resolution Success**: >90% de conflictos resueltos correctamente
- **Uncertainty Expression**: 100% de respuestas expresan incertidumbre cuando corresponde

### 9.3 Métricas de Calidad

- **Bug Rate**: <2 bugs críticos durante fase 7
- **Test Pass Rate**: 100% de tests pasando al final
- **Documentation Coverage**: 100% de componentes nuevos documentados

---

## 10. PLAN DE COMUNICACIÓN

### 10.1 Stakeholders

**Usuarios**:
- Comunicar mejora en confiabilidad de memoria
- Explicar sistema de confianza y metadata
- Documentar cómo invalidar memoria incorrecta
- Explicar cómo el sistema expresa incertidumbre

**Desarrolladores**:
- Comunicar nueva arquitectura de memoria confiable
- Documentar API para Reliable Memory
- Explicar patrones de uso de metadata
- Proporcionar ejemplos de integración

**QA**:
- Proporcionar criterios de aceptación
- Documentar casos de prueba de memoria
- Explicar procedimientos de validación

### 10.2 Documentación Requerida

1. **Documentación de Usuario**:
   - Cómo funciona el sistema de memoria confiable
   - Qué significa cuando el sistema expresa incertidumbre
   - Cómo invalidar memoria incorrecta
   - Cómo interpretar scores de confianza

2. **Documentación de Desarrollador**:
   - API para Reliable Memory
   - API para Memory Validator
   - API para Memory Conflict Resolver
   - Patrones de uso de metadata
   - Cómo extender tipos de memoria

3. **Documentación de Arquitectura**:
   - Diagrama de sistema de memoria confiable
   - Flujo de validación y almacenamiento
   - Integración con componentes existentes

4. **Documentación de API**:
   - Nuevos endpoints para gestión de memoria
   - Cambios en componentes existentes
   - Ejemplos de uso

---

## 11. CRITERIOS DE ACEPTACIÓN

### 11.1 Criterios Técnicos

- [ ] Todos los unit tests pasan (>85% coverage)
- [ ] Todos los integration tests pasan
- [ ] Todos los E2E tests pasan
- [ ] Todos los performance tests pasan
- [ ] Code review completado y aprobado
- [ ] Sin dependencias nuevas agregadas

### 11.2 Criterios Funcionales

- [ ] ReliableMemory almacena y recupera con metadata correctamente
- [ ] MemoryValidator valida datos y metadata correctamente
- [ ] MemoryConflictResolver detecta y resuelve conflictos
- [ ] Sistema expresa incertidumbre cuando no está seguro
- [ ] Integración con MemoryBackend funciona con fallback
- [ ] Integración con KnowledgeBase funciona con fallback
- [ ] Integración con Orchestrator funciona con fallback

### 11.3 Criterios de Performance

- [ ] Storage performance <100ms (100%)
- [ ] Retrieval performance <50ms (100%)
- [ ] Invalidation performance <50ms (100%)
- [ ] Validation performance <10ms (100%)
- [ ] No degradación significativa de performance del sistema (<10%)

### 11.4 Criterios de Calidad

- [ ] Documentación completa y precisa
- [ ] Código sigue convenciones del proyecto
- [ ] Sin warnings de linter
- [ ] Sin vulnerabilidades de seguridad introducidas
- [ ] Compatible con versiones existentes (backward compatible)

---

## 12. CONFIRMACIÓN REQUERIDA

Antes de proceder con la implementación de FASE 7, confirmar:

1. **¿Aprobar el plan de implementación propuesto?**
2. **¿Están de acuerdo con la estrategia de testing de memoria confiable?**
3. **¿Los criterios de aceptación son apropiados?**
4. **¿Algún ajuste requerido antes de comenzar la implementación?**

---

## 13. CONSIDERACIONES ESPECIALES

### 13.1 Compatibilidad con FASE 2-6

**Consideración**: Integración con todas las fases anteriores
- Reliable Memory debe trabajar con Grounding de FASE 2 (metadata de fuente de datos)
- Presentation Layer de FASE 3 debe filtrar detalles de metadata
- Decision Engine de FASE 4 debe considerar confianza de memoria
- Environmental Learning de FASE 5 debe usar Reliable Memory para conocimiento del entorno
- Hardware Intelligence de FASE 6 debe usar Reliable Memory para perfiles de hardware

### 13.2 Consistencia de Metadata

**Consideración**: Asegurar consistencia en metadata a través del sistema
- Definir estándares para scores de confianza por fuente
- Definir estándares para contextos por tipo de memoria
- Validar consistencia en todas las integraciones
- Documentar patrones de metadata

### 13.3 Expressión de Incertidumbre

**Consideración**: Cómo el sistema expresa incertidumbre al usuario
- Definir mensajes estándar para diferentes niveles de incertidumbre
- Integrar con Advisory Service de FASE 4
- Asegurar que Presentation Layer de FASE 3 formatee apropiadamente
- Proveer opciones para usuarios que prefieren respuestas más conservadoras

### 13.4 Migración de Datos Existentes

**Consideración**: Cómo manejar datos existentes en memoria
- Datos existentes deben migrarse con metadata default
- Score de confianza default para datos migrados
- Marcar datos migrados como invalidables
- Proveer herramienta para limpiar datos migrados si es necesario

---

## 14. RESUMEN FINAL DEL PROYECTO

Al completar FASE 7, se habrán implementado todas las 7 fases principales del plan de evolución de Sentinel:

✅ **FASE 1**: Auditoría Arquitectónica  
✅ **FASE 2**: Grounding Engine  
✅ **FASE 3**: Presentation Layer  
✅ **FASE 4**: Decision Engine Seguro  
✅ **FASE 5**: Environmental Learning  
✅ **FASE 6**: Hardware Intelligence  
✅ **FASE 7**: Reliable Memory  

**FASE ADICIONAL**: Optimización y Pruebas (post-implementación)

El resultado será una plataforma de orquestación de IA con:
- Confianza verificable (grounding obligatorio)
- Separación clara usuario/desarrollador
- Decisiones de seguridad sin autoridad del LLM
- Aprendizaje contextual del entorno
- Adaptación automática al hardware
- Memoria confiable con metadata de confianza

---

**DOCUMENTO FASE_7_ARCHITECTURE_IMPACT.md COMPLETADO**

Este documento detalla el impacto arquitectónico de implementar el Reliable Memory en FASE 7, incluyendo archivos afectados, nivel de riesgo MEDIO, estrategia de rollback y plan de testing con énfasis en confiabilidad y expresión de incertidumbre.

**ESTADO**: Pendiente de aprobación antes de implementación.
