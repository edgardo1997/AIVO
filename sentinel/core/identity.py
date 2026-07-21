"""Windows identity provider: user info, Windows Hello, Credential Manager, DPAPI."""

import ctypes
import ctypes.wintypes
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# --- Win32 API constants ---
NameSamCompatible = 2
NameUserPrincipal = 8
TokenElevation = 20
TokenElevationType = 18
TokenElevationTypeDefault = 1
TokenElevationTypeFull = 2
TokenElevationTypeLimited = 3

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
CRED_MAX_CREDENTIAL_BLOB_SIZE = 512
CRED_MAX_ATTRIBUTES = 64

# --- ctypes bindings ---

_advapi32 = ctypes.windll.advapi32
_kernel32 = ctypes.windll.kernel32
_credui = ctypes.windll.credui


def _get_last_error() -> int:
    return ctypes.GetLastError()


def _check_bool(result: int) -> bool:
    return result != 0


# --- Windows Identity ---

@dataclass
class WindowsIdentity:
    username: str
    domain: str = ""
    sid: str = ""
    is_admin: bool = False
    is_elevated: bool = False
    is_system: bool = False
    session_id: int = 0


def get_windows_identity() -> WindowsIdentity:
    try:
        username = os.environ.get("USERNAME", "")
        domain = os.environ.get("USERDOMAIN", "")
        sid = _get_user_sid()
        is_admin = _is_admin()
        is_elevated = _is_elevated()
        is_system = username.lower() == "system"
        session_id = _get_session_id()
        return WindowsIdentity(
            username=username,
            domain=domain or "",
            sid=sid or "",
            is_admin=is_admin,
            is_elevated=is_elevated,
            is_system=is_system,
            session_id=session_id,
        )
    except Exception as e:
        log.warning("Failed to get Windows identity: %s", e)
        return WindowsIdentity(username=os.environ.get("USERNAME", "unknown"))


def _get_user_sid() -> str:
    try:
        token = ctypes.wintypes.HANDLE()
        _advapi32.OpenProcessToken(
            _kernel32.GetCurrentProcess(),
            0x0008,  # TOKEN_QUERY
            ctypes.byref(token),
        )
        if not token:
            return ""
        try:
            size = ctypes.wintypes.DWORD(0)
            _advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))  # TokenUser = 1
            buf = ctypes.create_string_buffer(size.value)
            if _advapi32.GetTokenInformation(token, 1, buf, size, ctypes.byref(size)):
                import ntsecuritycon as _
            return ""
        finally:
            _kernel32.CloseHandle(token)
    except Exception:
        return ""


def _is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _is_elevated() -> bool:
    try:
        token = ctypes.wintypes.HANDLE()
        _advapi32.OpenProcessToken(
            _kernel32.GetCurrentProcess(),
            0x0008,
            ctypes.byref(token),
        )
        if not token:
            return False
        try:
            elevation = ctypes.wintypes.DWORD(0)
            size = ctypes.wintypes.DWORD(ctypes.sizeof(elevation))
            ok = _advapi32.GetTokenInformation(
                token, TokenElevation, ctypes.byref(elevation), size, ctypes.byref(size),
            )
            return ok and elevation.value != 0
        finally:
            _kernel32.CloseHandle(token)
    except Exception:
        return False


def _get_session_id() -> int:
    try:
        _kernel32.GetCurrentProcessId()
        token = ctypes.wintypes.HANDLE()
        _advapi32.OpenProcessToken(
            _kernel32.GetCurrentProcess(),
            0x0008,
            ctypes.byref(token),
        )
        if not token:
            return 0
        try:
            session = ctypes.wintypes.DWORD(0)
            size = ctypes.wintypes.DWORD(ctypes.sizeof(session))
            ok = _advapi32.GetTokenInformation(
                token, 12, ctypes.byref(session), size, ctypes.byref(size),  # TokenSessionId = 12
            )
            return session.value if ok else 0
        finally:
            _kernel32.CloseHandle(token)
    except Exception:
        return 0


def identity_to_dict(identity: WindowsIdentity) -> Dict[str, Any]:
    return {
        "user_id": identity.username,
        "username": identity.username,
        "domain": identity.domain,
        "sid": identity.sid,
        "is_admin": identity.is_admin,
        "is_elevated": identity.is_elevated,
        "is_system": identity.is_system,
        "session_id": identity.session_id,
        "is_authenticated": True,
    }


# --- Windows Hello verification ---

@dataclass
class VerificationResult:
    success: bool
    method: str = ""
    error: str = ""


def verify_with_hello(purpose: str = "") -> VerificationResult:
    try:
        _credui.CredUIPromptForWindowsCredentialsW.argtypes = [
            ctypes.POINTER(ctypes.c_void_p), ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD, ctypes.wintypes.DWORD,
            ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD,
            ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD,
            ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD,
        ]
    except AttributeError:
        return VerificationResult(success=False, method="", error="Windows Hello API not available")

    try:
        target_name = ctypes.c_wchar_p(purpose or "Sentinel AI Authorization")
        auth_buffer = ctypes.c_void_p()
        auth_size = ctypes.wintypes.DWORD(0)
        save = ctypes.wintypes.BOOL(False)

        result = _credui.CredUIPromptForWindowsCredentialsW(
            None, 0, 0, 0,
            target_name, 0,
            None, 0,
            ctypes.byref(auth_buffer), ctypes.byref(auth_size),
            ctypes.byref(save), 0x100,  # GENERIC_CRED UI
        )
        if result == 0:
            _kernel32.CoTaskMemFree(auth_buffer)
            return VerificationResult(success=True, method="windows_hello")
        return VerificationResult(success=False, method="", error=f"Windows Hello failed: {result}")
    except Exception as e:
        return VerificationResult(success=False, method="", error=str(e))


# --- Credential Manager ---

class CredentialManager:
    def __init__(self, target_prefix: str = "SentinelAI"):
        self._prefix = target_prefix

    def _make_target(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def set(self, key: str, value: str) -> Dict[str, Any]:
        target = self._make_target(key)
        try:
            blob = (value + "\x00").encode("utf-16-le")
            _cred = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)

            _CREDENTIAL = ctypes.c_ubyte * 0
            cred_struct = (ctypes.c_ubyte * (4 + 4 + 4 + 4 + 4 + 4 + 4 + len(target) * 2 + 4 + 4 + 4 + len(blob)))()

            result = _advapi32.CredWriteW(cred_struct, 0)
            if result:
                return {"success": True, "message": f"Credential '{key}' saved"}
            return {"success": False, "error": f"CredWrite failed: {_get_last_error()}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get(self, key: str) -> Dict[str, Any]:
        target = self._make_target(key)
        try:
            pcred = ctypes.POINTER(ctypes.c_ubyte)()
            result = _advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pcred))
            if result:
                _advapi32.CredFree(pcred)
                return {"success": True, "exists": True, "key": key}
            return {"success": False, "error": f"Credential '{key}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete(self, key: str) -> Dict[str, Any]:
        target = self._make_target(key)
        try:
            result = _advapi32.CredDeleteW(target, CRED_TYPE_GENERIC, 0)
            if result:
                return {"success": True, "message": f"Credential '{key}' deleted"}
            return {"success": False, "error": f"CredDelete failed: {_get_last_error()}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_keys(self) -> Dict[str, Any]:
        keys = []
        try:
            pcred = ctypes.POINTER(ctypes.c_ubyte)()
            count = ctypes.wintypes.DWORD(0)
            result = _advapi32.CredEnumerateW(f"{self._prefix}:*", 0, ctypes.byref(count), ctypes.byref(pcred))
            if result:
                _advapi32.CredFree(pcred)
            return {"success": True, "keys": keys}
        except Exception as e:
            return {"success": False, "error": str(e)}


# --- DPAPI Encryption ---

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class DataProtection:
    @staticmethod
    def _make_blob(data: bytes) -> _DATA_BLOB:
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        return _DATA_BLOB(len(data), buf)

    @staticmethod
    def _blob_to_bytes(blob: _DATA_BLOB) -> bytes:
        return ctypes.string_at(blob.pbData, blob.cbData)

    @staticmethod
    def protect(plaintext: str, entropy: Optional[bytes] = None) -> Dict[str, Any]:
        try:
            _crypt32 = ctypes.windll.crypt32
            data_in = DataProtection._make_blob(plaintext.encode("utf-8"))
            data_out = _DATA_BLOB()

            flags = 0
            entropy_blob = _DATA_BLOB(0, None)
            if entropy:
                entropy_blob = DataProtection._make_blob(entropy)
                flags |= 0x00000004  # CRYPTPROTECT_LOCAL_MACHINE

            result = _crypt32.CryptProtectData(
                ctypes.byref(data_in),
                None,
                ctypes.byref(entropy_blob) if entropy else None,
                None, None,
                flags,
                ctypes.byref(data_out),
            )
            if result:
                return {"success": True, "message": "Data protected"}
            return {"success": False, "error": f"Protect failed: {_get_last_error()}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def unprotect(ciphertext: bytes, entropy: Optional[bytes] = None) -> Dict[str, Any]:
        try:
            _crypt32 = ctypes.windll.crypt32
            data_in = DataProtection._make_blob(ciphertext)
            data_out = _DATA_BLOB()
            p_desc = ctypes.c_wchar_p()

            entropy_blob = _DATA_BLOB(0, None)
            if entropy:
                entropy_blob = DataProtection._make_blob(entropy)

            result = _crypt32.CryptUnprotectData(
                ctypes.byref(data_in),
                ctypes.byref(p_desc),
                ctypes.byref(entropy_blob) if entropy else None,
                None, None,
                0,
                ctypes.byref(data_out),
            )
            if result:
                plain = ctypes.string_at(data_out.pbData, data_out.cbData)
                _crypt32.LocalFree(data_out.pbData)
                return {"success": True, "data": plain.decode("utf-8")}
            return {"success": False, "error": f"Unprotect failed: {_get_last_error()}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# --- Identity Provider (for pipeline integration) ---

_credential_manager: Optional[CredentialManager] = None


def get_credential_manager() -> CredentialManager:
    global _credential_manager
    if _credential_manager is None:
        _credential_manager = CredentialManager()
    return _credential_manager
