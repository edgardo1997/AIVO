# FASE 14 — GUI Manual Validation Checklist

**Build ID:** ____________________  
**Version:** ____________________  
**Channel:** internal-alpha  
**Tester:** ____________________  
**Date:** ____________________  
**Windows version:** ____________________  
**Resolution/Scale:** ____________________

---

## A. Inicio

Run: `C:\Dev\AIVO\artifacts\internal-alpha\Sentinel_0.1.0-alpha.1_x64-setup.exe`

- [ ] Sentinel abre.
- [ ] No aparece consola de depuración.
- [ ] No aparece stack trace.
- [ ] La GUI no queda en blanco.
- [ ] El estado del sistema carga.

**Observations / evidence:**

---

## B. Página de Soporte y diagnóstico

Navigate: `Configuración → Soporte y diagnóstico` (o `Ayuda → Soporte`).

- [ ] La página existe y se muestra.
- [ ] La versión es visible.
- [ ] El Build ID es visible.
- [ ] El canal `internal-alpha` es visible.
- [ ] El estado general es comprensible.
- [ ] Estado del motor de Sentinel usa lenguaje humano.
- [ ] Estado de Cloud usa lenguaje humano.
- [ ] Última comprobación aparece.
- [ ] Detalles técnicos están ocultos por defecto.
- [ ] No aparecen nombres de clases JavaScript/Python.
- [ ] No aparecen errores HTTP crudos.

**Build ID visible:** ____________________

**Observations / evidence:**

---

## C. Detalles técnicos

Click: `Ver detalles técnicos`

- [ ] Muestra versión del motor.
- [ ] Muestra hash o identidad del sidecar.
- [ ] Muestra PID.
- [ ] Muestra puerto.
- [ ] Muestra correlation IDs recientes si existen.
- [ ] No muestra claves.
- [ ] No muestra tokens.
- [ ] No muestra conversaciones completas.

**Observations / evidence:**

---

## D. Crear diagnóstico

Click: `Crear diagnóstico`

- [ ] Explica qué información se incluirá.
- [ ] Explica qué información no se incluirá.
- [ ] Permite cancelar.
- [ ] Permite escoger ubicación.
- [ ] Genera ZIP.
- [ ] Muestra la ubicación final.
- [ ] Puede abrir la carpeta contenedora.
- [ ] No envía nada automáticamente.

**ZIP path:** ____________________

**Observations / evidence:**

---

## E. Revisar ZIP

Run:

```powershell
.\scripts\validate-diagnostic-package.ps1 -DiagnosticZip <ruta-del-zip> -ExpectedBuildId <build-id>
```

Confirm ZIP contains:

- [ ] `summary.json`
- [ ] `manifest.json`
- [ ] `system.txt`
- [ ] `events.jsonl`
- [ ] `README.txt`
- [ ] `SHA256SUMS.txt`
- [ ] `logs/` directory

Validate:

- [ ] ZIP abre sin errores.
- [ ] Los hashes SHA-256 coinciden.
- [ ] El manifest lista todos los archivos.
- [ ] Build ID en ZIP coincide con GUI.
- [ ] Versión coincide.
- [ ] Canal coincide.
- [ ] Sistema operativo aparece.
- [ ] Estado del motor aparece.
- [ ] Modelo aparece.
- [ ] Proveedor aparece.
- [ ] Cloud Authority aparece.

Search inside ZIP for the following fake secrets. **Result must be 0 matches each.**

- [ ] `FAKE_API_KEY_SENTINEL_TEST` — found: ___
- [ ] `FAKE_BEARER_TOKEN_SENTINEL_TEST` — found: ___
- [ ] `FAKE_PASSWORD_SENTINEL_TEST` — found: ___
- [ ] `FAKE_PRIVATE_KEY_SENTINEL_TEST` — found: ___
- [ ] `FAKE_COOKIE_SENTINEL_TEST` — found: ___

**Validation script exit code:** ____________________

**Observations / evidence:**

---

## F. Reparar configuración

Precondition: run `scripts/prepare-fase14-manual-validation.ps1` to create corrupt config.

Click: `Reparar configuración`

- [ ] Detecta corrupción o inválida.
- [ ] No muestra excepción cruda.
- [ ] Preserva copia corrupta.
- [ ] Usa backup válido.
- [ ] Informa exactamente qué reparó.
- [ ] Conserva historial.
- [ ] Conserva datos personales.
- [ ] Sentinel sigue funcionando tras reparar.

**Observations / evidence:**

---

## G. Restablecer interfaz

Select level: `Interfaz` → Click `Restablecer`

- [ ] Explica qué cambiará.
- [ ] No borra historial.
- [ ] No cambia permisos.
- [ ] No cambia Cloud Authority.
- [ ] No elimina vault.
- [ ] Tras reiniciar conserva datos del usuario.

**Observations / evidence:**

---

## H. Restablecer configuración

Select level: `Configuración` → Click `Restablecer`

- [ ] Lista qué se restablecerá.
- [ ] Lista qué se conservará.
- [ ] Solicita confirmación.
- [ ] Reinicia settings.
- [ ] Reinicia permisos según contrato.
- [ ] Conserva historial.
- [ ] Conserva modelos.
- [ ] Conserva archivos personales.

**Observations / evidence:**

---

## I. Restablecimiento completo

Use only the temporary validation profile.

Select level: `Completo` → Click `Restablecer`

- [ ] Muestra lista exacta de lo que se eliminará.
- [ ] Muestra lista exacta de lo que se conservará.
- [ ] Requiere confirmación fuerte.
- [ ] Crea backup.
- [ ] Cierra stores.
- [ ] Ejecuta reset.
- [ ] Reinicia correctamente.
- [ ] Presenta onboarding cuando corresponde.
- [ ] No deja estado parcial.

**Observations / evidence:**

---

## J. Cierre y reapertura

- [ ] Cierra Sentinel normalmente.
- [ ] No quedan procesos `sentinel.exe` ni `sidecar.exe`.
- [ ] No queda puerto escuchando en `127.0.0.1:8765`.
- [ ] Reabre Sentinel.
- [ ] La página de soporte funciona.
- [ ] El Build ID permanece igual.
- [ ] El diagnóstico puede generarse nuevamente.

**Observations / evidence:**

---

## Veredicto

- [ ] **APROBADO** — todos los checks críticos pasan, 0 secretos filtrados.
- [ ] **PARCIAL** — la implementación funciona, pero faltan pruebas manuales (bloqueo externo).
- [ ] **RECHAZADO** — hay P0/P1, pérdida de datos, fugas de secretos o stack traces.

**Summary of findings:**

