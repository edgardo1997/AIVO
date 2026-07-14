import logging
from fastapi import APIRouter
from services.fleet_service import FleetService

log = logging.getLogger("sentinel.fleet")
router = APIRouter()
_svc = FleetService()


@router.get("/status")
def get_fleet_status():
    return _svc.get_status()


@router.post("/pairing/generate")
def generate_pairing():
    return _svc.generate_pairing()


@router.post("/pairing/revoke")
def revoke_pairing():
    return _svc.revoke_pairing()


@router.post("/remote/toggle")
def toggle_remote():
    return _svc.toggle_remote()


@router.get("/pairing/qr")
def get_pairing_qr():
    return _svc.get_qr_data()


# Startup handled in main.py (on_event is deprecated)
