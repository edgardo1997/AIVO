"""Grounding Cache: Caché inteligente para datos verificados de grounding."""

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Entrada en el caché de grounding"""
    data: Any
    timestamp: float
    ttl_seconds: float
    access_count: int = 0
    last_accessed: Optional[float] = None


class GroundingCache:
    """Caché de datos verificados con TTL"""

    def __init__(self, default_ttl: float = 30.0):
        """Inicializa el caché

        Args:
            default_ttl: TTL por defecto en segundos
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._default_ttl = default_ttl
        self._max_size = 1000  # Máximo número de entradas

    def get(self, key: str) -> Optional[Any]:
        """Obtiene un valor del caché

        Args:
            key: Clave del caché

        Returns:
            Valor cacheado o None si no existe o expiró
        """
        entry = self._cache.get(key)
        if entry is None:
            return None

        # Verificar TTL
        if self._is_expired(entry):
            del self._cache[key]
            logger.debug(f"Cache entry expired: {key}")
            return None

        # Actualizar estadísticas de acceso
        entry.access_count += 1
        entry.last_accessed = time.time()
        self._cache.move_to_end(key)

        return entry.data

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Almacena un valor en el caché

        Args:
            key: Clave del caché
            value: Valor a almacenar
            ttl: TTL en segundos (usa default si no se proporciona)
        """
        if len(self._cache) >= self._max_size:
            self._evict_oldest()

        ttl_seconds = ttl if ttl is not None else self._default_ttl
        entry = CacheEntry(
            data=value,
            timestamp=time.time(),
            ttl_seconds=ttl_seconds,
            access_count=0,
            last_accessed=None
        )
        self._cache[key] = entry
        logger.debug(f"Cached: {key} (TTL: {ttl_seconds}s)")

    def invalidate(self, key: str) -> bool:
        """Invalida una entrada específica

        Args:
            key: Clave a invalidar

        Returns:
            True si la entrada existía y fue invalidada
        """
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"Invalidated cache entry: {key}")
            return True
        return False

    def invalidate_pattern(self, pattern: str) -> int:
        """Invalida entradas que contienen un patrón

        Args:
            pattern: Patrón a buscar en las claves

        Returns:
            Número de entradas invalidadas
        """
        keys_to_remove = [k for k in self._cache.keys() if pattern in k]
        for key in keys_to_remove:
            del self._cache[key]

        logger.debug(f"Invalidated {len(keys_to_remove)} cache entries matching '{pattern}'")
        return len(keys_to_remove)

    def invalidate_all(self) -> int:
        """Invalida todas las entradas

        Returns:
            Número de entradas invalidadas
        """
        count = len(self._cache)
        self._cache.clear()
        logger.debug(f"Invalidated all {count} cache entries")
        return count

    def cleanup_expired(self) -> int:
        """Limpia entradas expiradas

        Returns:
            Número de entradas limpiadas
        """
        expired_keys = [k for k, v in self._cache.items() if self._is_expired(v)]
        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del caché"""
        total = len(self._cache)
        expired = sum(1 for v in self._cache.values() if self._is_expired(v))

        # Calcular tasa de hits
        total_accesses = sum(v.access_count for v in self._cache.values())

        return {
            "total_entries": total,
            "expired_entries": expired,
            "valid_entries": total - expired,
            "total_accesses": total_accesses,
            "max_size": self._max_size,
            "utilization": total / self._max_size if self._max_size > 0 else 0,
        }

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Verifica si una entrada ha expirado"""
        age = time.time() - entry.timestamp
        return age > entry.ttl_seconds

    def _evict_oldest(self) -> None:
        """Elimina la entrada más antigua (LRU)"""
        if not self._cache:
            return

        # OrderedDict preserves exact access order even when the platform clock
        # returns identical timestamps for several operations.
        oldest_key, _ = self._cache.popitem(last=False)
        logger.debug(f"Evicted oldest cache entry: {oldest_key}")
