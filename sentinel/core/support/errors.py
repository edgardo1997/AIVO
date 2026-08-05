"""Central error contract for Sentinel.

This module defines the canonical `SentinelError` structure and a registry that
maps exceptions/conditions to stable codes, user-friendly messages and technical
metadata. All Alpha errors should eventually be produced here; legacy exceptions
are funnelled through `map_exception()`.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class ErrorCategory(Enum):
    AUTHENTICATION = "authentication"
    SIDECAR = "sidecar"
    MODEL = "model"
    PROVIDER = "provider"
    NETWORK = "network"
    PERMISSION = "permission"
    FILESYSTEM = "filesystem"
    RESOURCE_CHANGED = "resource_changed"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    AUDIT = "audit"
    PERSISTENCE = "persistence"
    CONFIGURATION = "configuration"
    INSTALLATION = "installation"
    UPDATE = "update"
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class OperationState(Enum):
    NOT_STARTED = "not_started"
    STARTED = "started"
    EFFECT_UNKNOWN = "effect_unknown"
    EFFECT_COMPLETED = "effect_completed"
    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True)
class SentinelError:
    """Canonical representation of an error inside Sentinel."""

    error_code: str
    category: ErrorCategory
    severity: ErrorSeverity
    user_message: str
    technical_message: str
    recommended_action: Optional[str] = None
    retryable: bool = False
    correlation_id: str = ""
    component: str = "unknown"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    build_id: str = ""
    operation_state: Optional[OperationState] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_user_dict(self) -> Dict[str, Any]:
        """Return only safe fields for the GUI."""
        return {
            "error_code": self.error_code,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.user_message,
            "recommended_action": self.recommended_action,
            "retryable": self.retryable,
            "support_code": self.correlation_id[:12] if self.correlation_id else "",
        }

    def to_log_dict(self) -> Dict[str, Any]:
        """Return complete, structured log entry."""
        return {
            "timestamp": self.timestamp,
            "level": self.severity.value.upper(),
            "component": self.component,
            "event": f"{self.category.value}_{self.error_code}",
            "error_code": self.error_code,
            "category": self.category.value,
            "severity": self.severity.value,
            "correlation_id": self.correlation_id,
            "build_id": self.build_id,
            "user_message": self.user_message,
            "technical_message": self.technical_message,
            "recommended_action": self.recommended_action,
            "retryable": self.retryable,
            "operation_state": self.operation_state.value if self.operation_state else None,
            "details": self.details,
        }


class ErrorRegistry:
    """Maps exceptions and conditions to stable SentinelError templates."""

    _codes: Dict[str, Dict[str, Any]] = {}
    _templates: Dict[tuple, str] = {}

    @classmethod
    def register(
        cls,
        code: str,
        category: ErrorCategory,
        severity: ErrorSeverity,
        user_message: str,
        technical_message: str,
        recommended_action: Optional[str] = None,
        retryable: bool = False,
    ):
        if code in cls._codes:
            raise ValueError(f"Duplicate error code: {code}")
        cls._codes[code] = {
            "category": category,
            "severity": severity,
            "user_message": user_message,
            "technical_message": technical_message,
            "recommended_action": recommended_action,
            "retryable": retryable,
        }

    @classmethod
    def build(
        cls,
        code: str,
        component: str = "unknown",
        operation_state: Optional[OperationState] = None,
        details: Optional[Dict[str, Any]] = None,
        correlation_id: str = "",
        build_id: str = "",
    ) -> SentinelError:
        if code not in cls._codes:
            return cls.build_unknown(f"Unregistered error code: {code}", component, correlation_id, build_id)
        template = cls._codes[code]
        safe_details = defaultdict(str, details or {})
        return SentinelError(
            error_code=code,
            category=template["category"],
            severity=template["severity"],
            user_message=template["user_message"],
            technical_message=template["technical_message"].format_map(safe_details),
            recommended_action=template["recommended_action"],
            retryable=template["retryable"],
            correlation_id=correlation_id or _new_correlation(),
            component=component,
            build_id=build_id,
            operation_state=operation_state,
            details=details or {},
        )

    @classmethod
    def build_unknown(
        cls,
        technical: str,
        component: str = "unknown",
        correlation_id: str = "",
        build_id: str = "",
    ) -> SentinelError:
        return SentinelError(
            error_code="SEN-UNKNOWN-001",
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.ERROR,
            user_message="Ocurrió un problema inesperado. Puede crear un diagnóstico para obtener ayuda.",
            technical_message=technical,
            recommended_action="Crear diagnóstico y contactar soporte.",
            retryable=False,
            correlation_id=correlation_id or _new_correlation(),
            component=component,
            build_id=build_id,
        )

    @classmethod
    def codes(cls) -> Dict[str, Dict[str, Any]]:
        return dict(cls._codes)


def _new_correlation() -> str:
    return uuid.uuid4().hex


def map_exception(
    exc: BaseException,
    component: str = "unknown",
    operation_state: Optional[OperationState] = None,
    correlation_id: str = "",
    build_id: str = "",
) -> SentinelError:
    """Boundary for legacy exceptions. Produces a safe SentinelError."""
    message = str(exc) or type(exc).__name__
    for code, meta in ErrorRegistry.codes().items():
        if meta["category"].value.lower() in message.lower():
            return ErrorRegistry.build(
                code,
                component=component,
                operation_state=operation_state,
                correlation_id=correlation_id,
                build_id=build_id,
                details={"exception": type(exc).__name__, "message": message},
            )
    return ErrorRegistry.build_unknown(
        technical=f"{type(exc).__name__}: {message}",
        component=component,
        correlation_id=correlation_id,
        build_id=build_id,
    )


# Register the canonical error catalogue.
ErrorRegistry.register(
    "SEN-AUTH-001",
    ErrorCategory.AUTHENTICATION,
    ErrorSeverity.ERROR,
    user_message="No se pudo verificar su identidad. Inicie sesión de nuevo si el problema continúa.",
    technical_message="Authentication failed for identity: {identity}",
    recommended_action="Verifique credenciales o vuelva a autenticarse.",
    retryable=False,
)
ErrorRegistry.register(
    "SEN-SIDECAR-001",
    ErrorCategory.SIDECAR,
    ErrorSeverity.CRITICAL,
    user_message="El motor de Sentinel no responde. Reinicie la aplicación o cree un diagnóstico.",
    technical_message="Sidecar unreachable: {reason}",
    recommended_action="Crear diagnóstico y reiniciar.",
    retryable=False,
)
ErrorRegistry.register(
    "SEN-MODEL-001",
    ErrorCategory.MODEL,
    ErrorSeverity.WARNING,
    user_message="El modelo local no está disponible. Puede cambiar a otro proveedor mientras se restaura.",
    technical_message="Local model unavailable: {model}",
    recommended_action="Cambiar de proveedor o verificar el modelo local.",
    retryable=True,
)
ErrorRegistry.register(
    "SEN-PROVIDER-001",
    ErrorCategory.PROVIDER,
    ErrorSeverity.WARNING,
    user_message="El proveedor de IA no respondió. Se intentará con el siguiente disponible.",
    technical_message="Provider error: {provider} - {reason}",
    recommended_action="Espere unos segundos o seleccione otro proveedor.",
    retryable=True,
)
ErrorRegistry.register(
    "SEN-NET-001",
    ErrorCategory.NETWORK,
    ErrorSeverity.WARNING,
    user_message="No se pudo conectar con el servicio. Verifique su conexión.",
    technical_message="Network error: {reason}",
    recommended_action="Verifique conexión de red e intente nuevamente.",
    retryable=True,
)
ErrorRegistry.register(
    "SEN-PERM-001",
    ErrorCategory.PERMISSION,
    ErrorSeverity.ERROR,
    user_message="No tiene permiso para realizar esta acción. Puede cambiar el nivel de permiso si es el propietario.",
    technical_message="Permission denied for action: {action}",
    recommended_action="Solicite permiso o ajuste el nivel de permiso.",
    retryable=False,
)
ErrorRegistry.register(
    "SEN-FS-001",
    ErrorCategory.FILESYSTEM,
    ErrorSeverity.ERROR,
    user_message="No se pudo acceder al archivo o carpeta solicitado.",
    technical_message="Filesystem error for path: {path}",
    recommended_action="Verifique la ruta y los permisos.",
    retryable=False,
)
ErrorRegistry.register(
    "SEN-RESOURCE-001",
    ErrorCategory.RESOURCE_CHANGED,
    ErrorSeverity.WARNING,
    user_message="El archivo cambió después de autorizar la acción. Sentinel no la completó.",
    technical_message="Resource identity changed: {path}",
    recommended_action="Revise el archivo y vuelva a confirmar.",
    retryable=True,
)
ErrorRegistry.register(
    "SEN-EXEC-001",
    ErrorCategory.EXECUTION,
    ErrorSeverity.ERROR,
    user_message="La ejecución no pudo completarse de forma segura.",
    technical_message="Execution failed: {reason}",
    recommended_action="Revise los parámetros o consulte el diagnóstico.",
    retryable=False,
)
ErrorRegistry.register(
    "SEN-VERIFY-001",
    ErrorCategory.VERIFICATION,
    ErrorSeverity.WARNING,
    user_message="No se pudo verificar el resultado. La acción puede haber tenido efectos parciales.",
    technical_message="Verification failed: {reason}",
    recommended_action="Revise el estado y considere una verificación manual.",
    retryable=True,
)
ErrorRegistry.register(
    "SEN-AUDIT-001",
    ErrorCategory.AUDIT,
    ErrorSeverity.WARNING,
    user_message="La acción se completó pero no se pudo guardar todo el registro de auditoría.",
    technical_message="Audit storage failed: {reason}",
    recommended_action="No repita la acción. Puede crear un diagnóstico.",
    retryable=False,
)
ErrorRegistry.register(
    "SEN-PERSIST-001",
    ErrorCategory.PERSISTENCE,
    ErrorSeverity.ERROR,
    user_message="No se pudo guardar el estado. Sus datos recientes pueden no conservarse.",
    technical_message="Persistence error: {reason}",
    recommended_action="Verifique espacio en disco y permisos.",
    retryable=True,
)
ErrorRegistry.register(
    "SEN-CONFIG-001",
    ErrorCategory.CONFIGURATION,
    ErrorSeverity.ERROR,
    user_message="La configuración es inválida o está corrupta.",
    technical_message="Configuration error: {reason}",
    recommended_action="Use Reparar configuración o restablecer la configuración.",
    retryable=False,
)
ErrorRegistry.register(
    "SEN-INSTALL-001",
    ErrorCategory.INSTALLATION,
    ErrorSeverity.CRITICAL,
    user_message="La instalación no está completa o es incompatible.",
    technical_message="Installation error: {reason}",
    recommended_action="Reinstale Sentinel o use restablecimiento completo.",
    retryable=False,
)
ErrorRegistry.register(
    "SEN-UPDATE-001",
    ErrorCategory.UPDATE,
    ErrorSeverity.WARNING,
    user_message="No se pudo verificar o aplicar la actualización.",
    technical_message="Update error: {reason}",
    recommended_action="Verifique conexión y vuelva a intentar.",
    retryable=True,
)
ErrorRegistry.register(
    "SEN-UNKNOWN-001",
    ErrorCategory.UNKNOWN,
    ErrorSeverity.ERROR,
    user_message="Ocurrió un problema inesperado. Puede crear un diagnóstico para obtener ayuda.",
    technical_message="Unknown error: {reason}",
    recommended_action="Crear diagnóstico y contactar soporte.",
    retryable=False,
)
