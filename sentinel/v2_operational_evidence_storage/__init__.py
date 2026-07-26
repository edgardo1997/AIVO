"""Public interfaces for isolated operational evidence persistence."""

from importlib import import_module

__all__ = [
    "V2_OPERATIONAL_EVIDENCE_STORAGE_ENABLED",
    "EvidenceIntegrityError",
    "EvidenceRecordV1",
    "EvidenceRetentionPolicy",
    "EvidenceStorageControl",
    "EvidenceStorageMetrics",
    "EvidenceStorageReport",
    "OperationalEvidenceStorage",
    "RecoveryManager",
    "RecoveryStatus",
]

_EXPORTS = {
    "V2_OPERATIONAL_EVIDENCE_STORAGE_ENABLED": (
        ".control",
        "V2_OPERATIONAL_EVIDENCE_STORAGE_ENABLED",
    ),
    "EvidenceIntegrityError": (".integrity", "EvidenceIntegrityError"),
    "EvidenceRecordV1": (".schema", "EvidenceRecordV1"),
    "EvidenceRetentionPolicy": (".retention", "EvidenceRetentionPolicy"),
    "EvidenceStorageControl": (".control", "EvidenceStorageControl"),
    "EvidenceStorageMetrics": (".metrics", "EvidenceStorageMetrics"),
    "EvidenceStorageReport": (".report", "EvidenceStorageReport"),
    "OperationalEvidenceStorage": (".storage", "OperationalEvidenceStorage"),
    "RecoveryManager": (".recovery", "RecoveryManager"),
    "RecoveryStatus": (".recovery", "RecoveryStatus"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
