# FASE 14 — EVIDENCIA GUI

## Metadatos

| Field | Value |
|-------|-------|
| Date | |
| Tester | |
| Machine | |
| Windows version | |
| Display resolution | |
| Display scale | |
| Sentinel commit | |
| Build ID | |
| Installer path | |
| `sentinel.exe` SHA-256 | |
| `sidecar.exe` SHA-256 | |

## A. Inicio

| Check | Result | Capture |
|-------|--------|---------|
| Sentinel abre | | |
| No aparece consola | | |
| No aparece stack trace | | |
| GUI no queda en blanco | | |
| Estado del sistema carga | | |

**Notes:**

## B. Página de soporte

| Check | Result | Capture |
|-------|--------|---------|
| Página existe | | |
| Versión visible | | |
| Build ID visible | | |
| Canal visible | | |
| Estado comprensible | | |
| IA local en lenguaje humano | | |
| Cloud en lenguaje humano | | |
| Detalles técnicos ocultos | | |
| Sin nombres de clases | | |
| Sin errores HTTP crudos | | |

**Build ID mostrado:**

**Notes:**

## C. Detalles técnicos

| Check | Result | Capture |
|-------|--------|---------|
| Versión del motor visible | | |
| Hash/identidad sidecar visible | | |
| PID visible | | |
| Puerto visible | | |
| Correlation IDs visibles | | |
| Sin claves | | |
| Sin tokens | | |
| Sin conversaciones completas | | |

**Notes:**

## D. Crear diagnóstico

| Check | Result | Capture |
|-------|--------|---------|
| Explica qué incluye | | |
| Explica qué no incluye | | |
| Permite cancelar | | |
| Permite escoger ubicación | | |
| Genera ZIP | | |
| Muestra ubicación final | | |
| Puede abrir carpeta | | |
| No envía automáticamente | | |

**ZIP path:**

**Notes:**

## E. Revisión ZIP

**Validation script command:**

```powershell
.\scripts\validate-diagnostic-package.ps1 -DiagnosticZip "<path>" -ExpectedBuildId "<build-id>"
```

| Check | Result | Capture |
|-------|--------|---------|
| ZIP abre | | |
| Hashes coinciden | | |
| Manifest lista archivos | | |
| Build ID coincide | | |
| Versión coincide | | |
| Canal coincide | | |
| Sistema operativo aparece | | |
| Estado del motor aparece | | |
| Modelo aparece | | |
| Proveedor aparece | | |
| Cloud Authority aparece | | |

**Redaction search (must be 0):**

| Secret | Matches |
|--------|---------|
| `FAKE_API_KEY_SENTINEL_TEST` | |
| `FAKE_BEARER_TOKEN_SENTINEL_TEST` | |
| `FAKE_PASSWORD_SENTINEL_TEST` | |
| `FAKE_PRIVATE_KEY_SENTINEL_TEST` | |
| `FAKE_COOKIE_SENTINEL_TEST` | |

**Notes:**

## F. Reparar configuración

| Check | Result | Capture |
|-------|--------|---------|
| Detecta corrupción | | |
| Sin excepción cruda | | |
| Preserva copia corrupta | | |
| Usa backup válido | | |
| Informa qué reparó | | |
| Conserva historial | | |
| Conserva datos personales | | |
| Sigue funcionando | | |

**Notes:**

## G. Restablecer interfaz

| Check | Result | Capture |
|-------|--------|---------|
| Explica qué cambiará | | |
| No borra historial | | |
| No cambia permisos | | |
| No cambia Cloud Authority | | |
| No elimina vault | | |
| Tras reinicio conserva datos | | |

**Notes:**

## H. Restablecer configuración

| Check | Result | Capture |
|-------|--------|---------|
| Lista qué se restablecerá | | |
| Lista qué se conservará | | |
| Solicita confirmación | | |
| Reinicia settings | | |
| Reinicia permisos según contrato | | |
| Conserva historial | | |
| Conserva modelos | | |
| Conserva archivos personales | | |

**Notes:**

## I. Restablecimiento completo

| Check | Result | Capture |
|-------|--------|---------|
| Lista exacta de eliminación | | |
| Lista exacta de conservación | | |
| Requiere confirmación fuerte | | |
| Crea backup | | |
| Cierra stores | | |
| Ejecuta reset | | |
| Reinicia correctamente | | |
| Presenta onboarding si corresponde | | |
| No deja estado parcial | | |

**Notes:**

## J. Cierre y reapertura

| Check | Result | Capture |
|-------|--------|---------|
| Cierra normalmente | | |
| No quedan procesos | | |
| No queda puerto 8765 | | |
| Reabre | | |
| Página de soporte funciona | | |
| Build ID permanece igual | | |
| Diagnóstico puede regenerarse | | |

**Notes:**

## Bugs encontrados

| ID | Severidad | Pasos | Esperado | Real | Captura |
|----|-----------|-------|----------|------|---------|
| | | | | | |

## Veredicto

- [ ] APROBADO
- [ ] PARCIAL
- [ ] RECHAZADO

**Justification:**
