"""Product experience layer for Sentinel Desktop.

This package is a thin, user-facing translation layer. It never decides or
executes governed actions; it only exposes the underlying intelligence
(mode managers, model registry, system optimizer) as a stable product API
and records product-level metrics.

Modules:
- modes:          unified product modes with snapshot + rollback
- model_center:   user-facing model ecosystem (cards, favorites, priorities)
- metrics:        product metrics (first action, completions, retention)
- control_center: system overview and safe, reversible actions
"""

from sentinel.product.modes import ModesService
from sentinel.product.model_center import ModelCenterService
from sentinel.product.metrics import ProductMetricsService

__all__ = ["ModesService", "ModelCenterService", "ProductMetricsService"]
