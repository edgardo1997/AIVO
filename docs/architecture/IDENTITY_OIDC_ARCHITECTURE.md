# Sentinel — Arquitectura de identidad, sesión y OAuth/OIDC

Fecha: 2026-08-05
Rama: `feature/normal-user-experience`
Estado: **DISEÑO / IMPLEMENTACIÓN PARCIAL**

---

## 1. Objetivo

Definir una cadena segura y gobernada para:

- Cuenta local.
- Sesión de Tauri/backend.
- Inicio de sesión con Google (OIDC + PKCE).
- Inicio de sesión con Microsoft (OIDC + PKCE).
- Vinculación de cuentas.
- Cierre de sesión.
- Custodia de tokens.
- Separación entre identidad, IA e integraciones.

---

## 2. Fuente de verdad

```text
Tauri / backend sidecar
├── token de sesión (Tauri → sidecar vía SENTINEL_SESSION_TOKEN)
├── perfil local cifrado
├── store de transacciones OAuth
├── vault de tokens
└── router de sesión (/auth/session, /auth/local/profile, /auth/onboarding)

     ↓

SessionContext / useSession
└── UserSession (estado derivado)

     ↓

Guards y componentes
```

El **frontend nunca es fuente de verdad** para:

- `authenticated`
- `session_valid`
- `user_role`
- `admin`
- `permissions`
- `cloud_authority`
- `provider_tokens`
- `OAuth state / nonce / PKCE verifier`
- `grants`

`localStorage` solo puede almacenar preferencias no sensibles:

- `developer_mode_visible`
- `sidebar_collapsed`
- `selected_language`

---

## 3. Cuenta local

### 3.1 Datos del perfil

| Campo | Origen | Persistencia | Sensible |
|-------|--------|--------------|----------|
| `user_id` | UUID generado por backend | store cifrado | sí |
| `display_name` | Windows / usuario | store cifrado | no |
| `identity_provider` | `local` | store cifrado | no |
| `created_at` | ISO 8601 UTC | store cifrado | no |
| `profile_version` | schema version | store cifrado | no |

### 3.2 Flujo

```text
Welcome
└── Usar Sentinel localmente
    ├── sidecar devuelve session token
    ├── /auth/session responde
    ├── ¿existe local/profile?
    │   ├── Sí → continuar
    │   └── No → crear /auth/local/profile
    └── ¿onboarding completado?
        ├── Sí → Inicio
        └── No → Onboarding
```

### 3.3 Roles

- Cuenta local normal: `roles = ["user"]`.
- `developer mode` es una preferencia UI, no un rol.
- `admin` requiere una política real y se expone solo si el backend lo incluye en `roles`.

---

## 4. Sesión

### 4.1 Contrato `UserSession`

```typescript
type SessionStatus =
  | "checking"
  | "unauthenticated"
  | "authenticated"
  | "expired"
  | "error";

interface UserSession {
  status: SessionStatus;
  userId?: string;
  displayName?: string;
  avatarUrl?: string;
  identityProvider?: "local" | "google" | "microsoft";
  roles: string[];
  onboardingCompleted: boolean;
  expiresAt?: string;
}
```

### 4.2 Endpoints

| Endpoint | Descripción |
|----------|-------------|
| `GET /auth/session` | Retorna la sesión canónica del usuario. |
| `GET /auth/local/profile` | Retorna el perfil local o `null`. |
| `POST /auth/local/profile` | Crea un perfil local. |
| `GET /auth/onboarding` | Estado del onboarding. |
| `POST /auth/onboarding` | Marca onboarding como completado. |

### 4.3 Logout

```text
Cerrar sesión
≠ Eliminar perfil
≠ Restablecer Sentinel
```

Cerrar sesión limpia el token en frontend; no borra perfil, historial ni configuración.

---

## 5. Onboarding de cuatro pasos

| Paso | Nombre | Contenido | Validación |
|------|--------|-----------|------------|
| 1 | Identidad | Nombre, tipo de cuenta, privacidad local | perfil local creado |
| 2 | IA | Modelo local, cloud opcional, proveedores | selección guardada |
| 3 | Carpetas | Carpetas permitidas, revocación | permisos persistidos |
| 4 | Resumen | Confirmación, resumen, términos | backend marca `onboarding_completed` |

### Recuperación

- El frontend puede cerrarse en cualquier paso.
- Al reiniciar se consulta `/auth/onboarding`.
- Si el frontend dice `completado` pero el backend dice `pendiente`, gana el backend.
- `onboardingCompleted` es una preferencia local únicamente si el backend no está disponible; la fuente final es backend.

---

## 6. Estrategia de redirect desktop

### Opción elegida: loopback local temporal

```text
http://127.0.0.1:<puerto-aleatorio>/oauth/callback
```

#### Justificación

- No requiere registro de `sentinel://` esquema.
- No depende de soporte del proveedor para custom URI.
- Se cierra automáticamente después de una respuesta o timeout.
- Fácil de auditar y probar.

#### Requisitos

- Puerto aleatorio por transacción.
- Listener TCP temporal.
- Timeout corto (por ejemplo, 5 minutos).
- Rechazar más de una respuesta.
- `state` obligatorio y de un solo uso.
- `nonce` obligatorio.
- Validar `iss` en el ID token.

---

## 7. Ciclo de vida de la transacción OAuth

```text
1. Usuario pulsa "Continuar con Google"
2. Frontend pide a Tauri/backend: iniciar OAuth Google
3. Backend genera:
   - transaction_id
   - state (256 bits)
   - nonce (256 bits)
   - PKCE code_verifier
   - redirect_uri aleatorio
4. Backend almacena hash de state y nonce, y code_verifier cifrado
5. Backend abre el navegador del sistema con URL de autorización
6. Proveedor redirige al loopback
7. Backend recibe code, valida state, obtiene tokens con PKCE
8. Backend valida nonce en ID token
9. Backend crea o vincula perfil
10. Backend cierra listener, elimina transacción
11. Frontend refresca sesión desde /auth/session
```

### Datos almacenados

```text
OAuthTransaction
├── transaction_id: uuid
├── provider: google | microsoft
├── state_hash: sha256
├── nonce_hash: sha256
├── pkce_verifier: cifrado
├── redirect_uri: string
├── created_at: ISO 8601
├── expires_at: ISO 8601
├── used: bool
└── user_id: nullable
```

### Reglas

- Una sola utilización.
- Expiración breve.
- Eliminación al cancelar o completar.
- Rechazo de replay.
- El `verifier` nunca se expone al frontend.

---

## 8. Custodia de tokens

### Componente: `SecureTokenStore`

Almacena:

```text
access_token    (cifrado)
refresh_token   (cifrado)
id_token        (cifrado)
pkce_verifier   (cifrado, temporal)
transaction_id  (hash)
```

### Mecanismos aceptables

- Windows Credential Manager.
- Tauri `tauri-plugin-stronghold` o equivalente.
- Vault cifrado existente.
- Alternativa aprobada por seguridad.

### Prohibido

- `localStorage`
- `sessionStorage`
- Redux persist.
- JSON plano.
- `.env`.
- Logs.
- SQLite sin cifrar.

---

## 9. Interfaces de proveedores

```typescript
interface IdentityProvider {
  id: "local" | "google" | "microsoft";
  startLogin(): Promise<OAuthStartResult>;
  handleCallback(callback: OAuthCallback): Promise<UserSession>;
  cancelLogin(transactionId: string): Promise<void>;
  refreshSession(): Promise<UserSession>;
  logout(): Promise<void>;
  getProfile(): Promise<Profile>;
}
```

### Implementaciones

- `LocalIdentityProvider`: usa Tauri session token.
- `GoogleIdentityProvider`: CONFIGURATION_REQUIRED.
- `MicrosoftIdentityProvider`: CONFIGURATION_REQUIRED.

### Scopes OIDC

```text
openid email profile
```

No pedir todavía:

- Google Drive
- Gmail

## 10. Vinculación de cuentas

Identificador externo canónico:

```text
issuer + subject
```

No email.

### Reglas

- `issuer+subject` existente → iniciar sesión como la cuenta vinculada.
- Email verificado con emisor diferente → no vincular automáticamente.
- Email no verificado → no vincular.
- Cuenta local autenticada → vinculación explícita.
- Desvincular proveedor → conservar perfil local.

### Servicio

- `AccountLinkingService` en `sidecar/services/account_linking.py`.
- Métodos: `find_identity`, `link_identity`, `unlink_identity`, `list_linked_identities`, `validate_link_request`.
- Auditoría de cada acción.

## 11. Protección del PKCE verifier

Para Alpha:

- El verifier se mantiene únicamente en memoria dentro de `OAuthTransactionStore`.
- No se persiste en SQLite.
- No se serializa al frontend.
- No se escribe en logs.
- Se elimina al completar, cancelar o expirar.
- Reinicio del sidecar invalida todas las transacciones pendientes.

## 12. Estado de implementación

| Componente | Estado |
|------------|--------|
| LocalProfileRepository | IMPLEMENTADO |
| AccountLinkingService | IMPLEMENTADO |
| OAuthTransactionStore | IMPLEMENTADO |
| Loopback listener | IMPLEMENTADO |
| Onboarding visual | IMPLEMENTADO |
| Identity provider contracts | IMPLEMENTADO |
| Google | CONFIGURATION_REQUIRED |
| Microsoft | CONFIGURATION_REQUIRED |

- Calendar
- Microsoft Graph
- OneDrive

La identidad no concede integraciones.

---

## 10. Separación de responsabilidades

| Función | Proveedor identidad | Proveedor IA | Integraciones |
|---------|---------------------|--------------|---------------|
| Login   | Sí                  | No           | No            |
| Modelos | No                  | Sí           | No            |
| Drive   | No                  | No           | Sí            |
| Permisos| Establece identidad | Sujeto a permisos | Sujeto a permisos |

Reglas:

- `login Google` no autoriza `Cloud Authority`.
- `login Google` no configura el proveedor IA.
- `login Google` no conecta `Drive`.
- `cuenta local` funciona sin proveedor IA cloud.

---

## 11. Tests de seguridad mínimos

- `state` generado con entropía suficiente.
- `state` almacenado como hash.
- `state` incorrecto rechazado.
- `state` reutilizado rechazado.
- `nonce` incorrecto rechazado.
- Transacción expirada rechazada.
- `PKCE verifier` no llega al frontend.
- Cancelación elimina transacción.
- Callback sin transacción rechazado.
- `provider` incorrecto rechazado.
- `redirect_uri` incorrecta rechazada.
- Tokens no aparecen en logs.
- Tokens no aparecen en diagnóstico.

---

## 12. Configuración de desarrollo

Plantilla: `.env.example`

```text
SENTINEL_GOOGLE_CLIENT_ID=
SENTINEL_GOOGLE_REDIRECT_URI=
SENTINEL_MICROSOFT_CLIENT_ID=
SENTINEL_MICROSOFT_TENANT=
SENTINEL_MICROSOFT_REDIRECT_URI=
```

No incluir valores reales en el repositorio.

---

## 13. Estado actual

| Componente | Estado |
|------------|--------|
| Cuenta local | Backend endpoints creados, almacenamiento en memoria (TODO: persistir) |
| Sesión canónica | `SessionService` + `SessionContext` implementados |
| Onboarding 4 pasos | Diseñado, pendiente de GUI |
| Estrategia redirect | Loopback temporal elegido |
| OAuth transaction lifecycle | Diseñado, pendiente de implementar |
| Secure token store | Diseñado, pendiente de implementar |
| Proveedores de identidad | Interfaces definidas, stubs seguros |
| Google / Microsoft | CONFIGURATION_REQUIRED |
| Tests de seguridad | Pendientes |
