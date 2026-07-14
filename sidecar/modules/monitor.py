import logging
from fastapi import APIRouter
from services.monitor_service import MonitorService

log = logging.getLogger("sentinel.monitor")
router = APIRouter()
_svc = MonitorService()

@router.get("/system")
def get_system_info():
    return _svc.get_system_info()

@router.get("/cpu")
def get_cpu():
    return _svc.get_cpu()

@router.get("/memory")
def get_memory():
    return _svc.get_memory()

@router.get("/disk")
def get_disk():
    return _svc.get_disk()

@router.get("/network")
def get_network():
    return _svc.get_network()

@router.get("/processes")
def get_processes():
    return _svc.get_processes()

@router.get("/gpu")
def get_gpu():
    return _svc.get_gpu()
