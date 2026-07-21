"""Grounding Engine: Detecta y fuerza uso de herramientas para información verificable.

Este es el núcleo del principio "IA nunca debe inventar información verificable".
Si existe una fuente verificable para una pregunta, LA HERRAMIENTA TIENE PRIORIDAD SOBRE EL MODELO.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class GroundingCategory(Enum):
    """Categorías de información que requieren grounding"""
    SYSTEM_STATE = "system_state"  # CPU, RAM, disco, procesos
    FILE_INFO = "file_info"  # Información de archivos
    PROCESS_INFO = "process_info"  # Información de procesos
    NETWORK_INFO = "network_info"  # Información de red
    APP_INFO = "app_info"  # Información de aplicaciones
    HARDWARE_INFO = "hardware_info"  # GPU, VRAM, NPU, hardware profile
    KNOWLEDGE_VERIFIABLE = "knowledge_verifiable"  # Conocimiento verificable
    NONE = "none"  # No requiere grounding


@dataclass
class GroundingRequirement:
    """Define qué información requiere grounding"""
    category: GroundingCategory
    required: bool
    freshness_seconds: float  # TTL para datos en segundos
    source_preference: List[str] = field(default_factory=list)  # ['tool', 'cache']
    tool_id: Optional[str] = None  # Herramienta específica a usar
    tool_params: Optional[Dict[str, Any]] = None  # Parámetros para la herramienta
    reason: str = ""  # Razón por la que se requiere grounding


@dataclass
class GroundingResult:
    """Resultado de una operación de grounding"""
    grounded: bool
    data: Optional[Dict[str, Any]] = None
    source: str = ""  # 'tool', 'cache', 'context_engine'
    timestamp: str = ""
    error: Optional[str] = None
    confidence: float = 1.0  # Confianza en que los datos son correctos


class GroundingEngine:
    """Detecta y fuerza grounding para información verificable"""

    # Patrones que indican necesidad de grounding
    SYSTEM_STATE_PATTERNS = [
        r"(cpu|processor|procesador)",
        r"(ram|memory|memoria)",
        r"(disk|disco|drive|storage)",
        r"(process|proceso|task)",
        r"(network|red|internet)",
        r"(system|sistema).*(info|information|status|estado)",
    ]

    FILE_INFO_PATTERNS = [
        r"(file|archivo)",
        r"(directory|directorio|folder|carpeta)",
        r"(path|ruta)",
        r"(read|leer).*(file|archivo)",
        r"(write|escribir).*(file|archivo)",
    ]

    PROCESS_INFO_PATTERNS = [
        r"(running|ejecutando).*(process|proceso)",
        r"(kill|matar).*(process|proceso)",
        r"(top|processes|procesos)",
    ]

    NETWORK_INFO_PATTERNS = [
        r"(network|red).*(connection|conexi[oó]n)",
        r"(internet|connectivity|conectividad)",
        r"(ip|dns|port)",
    ]

    HARDWARE_INFO_PATTERNS = [
        r"(gpu|graphics|gr[aá]fica|video)",
        r"(vram|video.*ram|gpu.*memory)",
        r"(npu|neural.*processor|ai.*accelerator)",
        r"(hardware|hardware.*profile|specs|especificaciones)",
        r"(nvidia|amd|intel.*(arc|gpu))",
        r"(cuda|cudnn|tensor.*core)",
    ]

    def __init__(
        self,
        context_engine: Optional[Any] = None,
        tool_gateway: Optional[Any] = None,
        capability_registry: Optional[Any] = None,
    ):
        self._context_engine = context_engine
        self._tool_gateway = tool_gateway
        self._capability_registry = capability_registry
        self._cache: Dict[str, tuple[Any, float]] = {}  # key -> (data, timestamp)

    def analyze_requirement(self, intent: Any) -> List[GroundingRequirement]:
        """Analiza si una intención requiere grounding

        Args:
            intent: Intent object con action, target, raw_input

        Returns:
            Lista de GroundingRequirement detectadas
        """
        requirements = []

        # Obtener texto del intent
        text = intent.raw_input.lower() if hasattr(intent, 'raw_input') else ""
        action = intent.action if hasattr(intent, 'action') else ""
        target = intent.target if hasattr(intent, 'target') else ""

        # Detectar categoría de grounding basado en el target
        category = self._detect_category(action, target, text)

        if category != GroundingCategory.NONE:
            # Determinar TTL basado en la categoría
            freshness = self._get_freshness_for_category(category)

            # Determinar herramienta específica si es posible
            tool_id, tool_params = self._get_tool_for_category(category, target, intent.parameters if hasattr(intent, 'parameters') else {})

            requirement = GroundingRequirement(
                category=category,
                required=True,
                freshness_seconds=freshness,
                # A model response is never evidence for machine state.
                source_preference=["tool", "cache"],
                tool_id=tool_id,
                tool_params=tool_params,
                reason=self._get_reason_for_category(category, target)
            )
            requirements.append(requirement)

        logger.debug(f"Grounding analysis for '{text}': {len(requirements)} requirements")
        return requirements

    def _detect_category(self, action: str, target: str, text: str) -> GroundingCategory:
        """Detecta la categoría de grounding necesaria"""
        import re

        # Verificar target directo
        if target.startswith("system."):
            return GroundingCategory.SYSTEM_STATE
        elif target in {"filesystem.read", "filesystem.search", "filesystem.list"}:
            return GroundingCategory.FILE_INFO
        elif target in {"app.discovery", "executor.launch", "app.launch"}:
            return GroundingCategory.APP_INFO
        elif target.startswith("executor.") and "process" in target:
            return GroundingCategory.PROCESS_INFO
        elif target.startswith("network."):
            return GroundingCategory.NETWORK_INFO
        elif target in {"system.gpu", "hardware.intelligence", "hardware.profile"}:
            return GroundingCategory.HARDWARE_INFO

        # Verificar patrones en el texto
        # Mutating actions are validated by their governed execution result;
        # they must not trigger a hidden preliminary read.
        if action not in {"query", "analyze"}:
            return GroundingCategory.NONE

        if any(re.search(pattern, text, re.IGNORECASE) for pattern in self.SYSTEM_STATE_PATTERNS):
            return GroundingCategory.SYSTEM_STATE
        elif any(re.search(pattern, text, re.IGNORECASE) for pattern in self.FILE_INFO_PATTERNS):
            return GroundingCategory.FILE_INFO
        elif any(re.search(pattern, text, re.IGNORECASE) for pattern in self.PROCESS_INFO_PATTERNS):
            return GroundingCategory.PROCESS_INFO
        elif any(re.search(pattern, text, re.IGNORECASE) for pattern in self.NETWORK_INFO_PATTERNS):
            return GroundingCategory.NETWORK_INFO
        elif any(re.search(pattern, text, re.IGNORECASE) for pattern in self.HARDWARE_INFO_PATTERNS):
            return GroundingCategory.HARDWARE_INFO

        return GroundingCategory.NONE

    def _get_freshness_for_category(self, category: GroundingCategory) -> float:
        """Retorna el TTL en segundos para una categoría"""
        freshness_map = {
            GroundingCategory.SYSTEM_STATE: 5.0,  # 5 segundos para estado del sistema
            GroundingCategory.FILE_INFO: 30.0,  # 30 segundos para info de archivos
            GroundingCategory.PROCESS_INFO: 10.0,  # 10 segundos para procesos
            GroundingCategory.NETWORK_INFO: 15.0,  # 15 segundos para red
            GroundingCategory.APP_INFO: 60.0,  # 1 minuto para apps
            GroundingCategory.HARDWARE_INFO: 120.0,  # 2 minutos para hardware (cambia poco)
            GroundingCategory.KNOWLEDGE_VERIFIABLE: 300.0,  # 5 minutos para conocimiento
        }
        return freshness_map.get(category, 30.0)

    def _get_tool_for_category(self, category: GroundingCategory, target: str, parameters: Dict[str, Any]) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Determina la herramienta específica para una categoría"""
        # Mapeo de targets a herramientas
        target_to_tool = {
            "system.cpu": ("system.cpu", {}),
            "system.memory": ("system.memory", {}),
            "system.disk": ("system.disk", {}),
            "system.processes": ("system.processes", parameters),
            "system.network": ("system.network", {}),
            "system.info": ("system.info", {}),
            "system.health": ("system.info", {}),
            "system.gpu": ("system.gpu", {}),
            "hardware.intelligence": ("system.gpu", {}),
            "hardware.profile": ("system.gpu", {}),
            "filesystem.read": ("filesystem.read", parameters),
            "filesystem.search": ("filesystem.search", parameters),
            "filesystem.list": ("filesystem.list", parameters),
            "app.discovery": ("app.discovery", parameters),
        }

        if target in target_to_tool:
            return target_to_tool[target]

        # Mapeo de categorías a herramientas por defecto
        category_tool_map = {
            GroundingCategory.SYSTEM_STATE: ("system.info", {}),
            GroundingCategory.FILE_INFO: ("filesystem.read", parameters),
            GroundingCategory.PROCESS_INFO: ("system.processes", parameters),
            GroundingCategory.NETWORK_INFO: ("system.info", {}),
            GroundingCategory.APP_INFO: ("app.discovery", parameters),
            GroundingCategory.HARDWARE_INFO: ("system.gpu", parameters),
        }

        return category_tool_map.get(category, (None, None))

    def _get_reason_for_category(self, category: GroundingCategory, target: str) -> str:
        """Genera una razón explicativa para el grounding"""
        reason_map = {
            GroundingCategory.SYSTEM_STATE: "Estado del sistema es información verificable que cambia dinámicamente",
            GroundingCategory.FILE_INFO: "Información de archivos requiere verificación del sistema de archivos",
            GroundingCategory.PROCESS_INFO: "Información de procesos requiere verificación en tiempo real",
            GroundingCategory.NETWORK_INFO: "Información de red requiere verificación actual",
            GroundingCategory.APP_INFO: "Información de aplicaciones requiere verificación del sistema",
            GroundingCategory.HARDWARE_INFO: "Perfil de hardware requiere verificación del sistema",
            GroundingCategory.KNOWLEDGE_VERIFIABLE: "Conocimiento verificable requiere fuente confiable",
        }
        return reason_map.get(category, "Información verificable requiere grounding")

    async def enforce_grounding(
        self,
        requirement: GroundingRequirement,
        context: Optional[Dict[str, Any]] = None
    ) -> GroundingResult:
        """Fuerza la obtención de datos desde fuente real

        Args:
            requirement: GroundingRequirement a cumplir
            context: Contexto adicional para la ejecución

        Returns:
            GroundingResult con los datos obtenidos
        """
        # Primero verificar caché
        cache_key = self._get_cache_key(requirement)
        cached_data, cached_timestamp = self._cache.get(cache_key, (None, 0))

        if cached_data is not None:
            # Verificar frescura
            if self._validate_freshness_cached(cached_timestamp, requirement):
                logger.debug(f"Using cached grounding data for {requirement.category}")
                return GroundingResult(
                    grounded=True,
                    data=cached_data,
                    source="cache",
                    timestamp=datetime.fromtimestamp(cached_timestamp, timezone.utc).isoformat(),
                    confidence=0.9
                )

        # No hay caché o está obsoleto, obtener desde herramienta
        if requirement.tool_id and self._tool_gateway:
            try:
                tool_params = requirement.tool_params or {}
                tool_result = await self._tool_gateway.execute(
                    requirement.tool_id,
                    tool_params,
                    context=context or {}
                )

                if tool_result.success and tool_result.data:
                    # Cachear resultado
                    self._cache[cache_key] = (tool_result.data, datetime.now(timezone.utc).timestamp())

                    return GroundingResult(
                        grounded=True,
                        data=tool_result.data,
                        source="tool",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        confidence=1.0
                    )
                else:
                    return GroundingResult(
                        grounded=False,
                        error=tool_result.error or "Tool execution failed",
                        confidence=0.0
                    )
            except Exception as e:
                logger.error(f"Tool execution failed for grounding: {e}")
                return GroundingResult(
                    grounded=False,
                    error=str(e),
                    confidence=0.0
                )

        # Fallback a ContextEngine si está disponible
        if self._context_engine and requirement.category == GroundingCategory.SYSTEM_STATE:
            try:
                sys_ctx = await self._context_engine.collect(include_processes=False)
                data = sys_ctx.to_dict()

                # Cachear resultado
                self._cache[cache_key] = (data, datetime.now(timezone.utc).timestamp())

                return GroundingResult(
                    grounded=True,
                    data=data,
                    source="context_engine",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    confidence=0.95
                )
            except Exception as e:
                logger.error(f"Context engine failed for grounding: {e}")

        # No se pudo obtener grounding
        return GroundingResult(
            grounded=False,
            error="No source available for grounding",
            confidence=0.0
        )

    def validate_freshness(self, data: Dict[str, Any], requirement: GroundingRequirement) -> bool:
        """Valida que los datos sean suficientemente frescos

        Args:
            data: Datos a validar (debe tener campo 'timestamp')
            requirement: GroundingRequirement con freshness_seconds

        Returns:
            True si los datos son suficientemente frescos
        """
        timestamp_str = data.get("timestamp", "")
        if not timestamp_str:
            return False

        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            age = datetime.now(timezone.utc) - timestamp
            return age.total_seconds() < requirement.freshness_seconds
        except Exception as e:
            logger.warning(f"Failed to validate freshness: {e}")
            return False

    def _validate_freshness_cached(self, cached_timestamp: float, requirement: GroundingRequirement) -> bool:
        """Valida frescura de datos cacheados"""
        age = datetime.now(timezone.utc).timestamp() - cached_timestamp
        return age < requirement.freshness_seconds

    def _get_cache_key(self, requirement: GroundingRequirement) -> str:
        """Genera una clave única para caché"""
        canonical_params = json.dumps(
            requirement.tool_params or {},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        params_digest = hashlib.sha256(canonical_params.encode("utf-8")).hexdigest()[:16]
        parts = [
            requirement.category.value,
            requirement.tool_id or "no_tool",
            params_digest,
        ]
        return ":".join(parts)

    def invalidate_cache(self, pattern: Optional[str] = None) -> None:
        """Invalida caché de grounding

        Args:
            pattern: Si proporcionado, solo invalida keys que contienen este patrón
        """
        if pattern:
            keys_to_remove = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self._cache[key]
            logger.debug(f"Invalidated {len(keys_to_remove)} cache entries matching '{pattern}'")
        else:
            count = len(self._cache)
            self._cache.clear()
            logger.debug(f"Invalidated all {count} cache entries")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas de caché"""
        return {
            "total_entries": len(self._cache),
            "keys": list(self._cache.keys()),
        }
