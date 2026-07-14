# Conector Gmail (CON-005)

Conector Ruvic para Gmail (cuenta personal o Google Workspace). Permite
buscar/listar correos con filtros, leer el detalle de un correo, enviar
correos y enviar correos con adjunto, usando OAuth2 con un refresh token
obtenido una única vez durante la configuración.

## Instalación

```bash
pip install git+https://github.com/Dgirto/Gmail.git#subdirectory=lib
```

Python 3.10+. Dependencias: `google-auth` y `google-api-python-client`.

## Obtener credenciales (una sola vez, por buzón a conectar)

### 1. Proyecto y OAuth consent screen en Google Cloud Console

1. Crea (o reutiliza) un proyecto en [Google Cloud Console](https://console.cloud.google.com/).
2. Habilita la **Gmail API** (buscar "Gmail API" → Habilitar).
3. Configura la **pantalla de consentimiento OAuth** (APIs y servicios → Pantalla de consentimiento de OAuth):
   - Tipo de usuario: **Externo** (obligatorio para cuentas @gmail.com personales; también funciona para Workspace).
   - Agrega el/los correo(s) del buzón a conectar como **usuarios de prueba** (mientras la app esté en estado "Testing" no requiere verificación de Google).

### 2. Cliente OAuth (tipo "Aplicación de escritorio")

1. APIs y servicios → **Credenciales** → **Crear credenciales → ID de cliente de OAuth**.
2. Tipo de aplicación: **Aplicación de escritorio**.
3. Anota el **Client ID** y **Client Secret** generados (o descarga el JSON).

### 3. Obtener el refresh token (script incluido)

```bash
pip install google-auth-oauthlib
python get_refresh_token.py --client-id TU_CLIENT_ID --client-secret TU_CLIENT_SECRET
```

Se abre el navegador; inicia sesión con el buzón que quieres conectar y acepta los permisos. El script imprime `client_id`, `client_secret` y `refresh_token` — esos tres valores van al formulario del conector en Ruvic (o a las env vars para pruebas locales).

> **Importante:** mientras la app de OAuth esté en estado "Testing" en Google Cloud, el refresh token puede expirar a los 7 días de inactividad. Para uso productivo continuo, publica la app (Pantalla de consentimiento → Publicar app) — con solo los scopes de Gmail usados aquí generalmente no requiere el proceso completo de verificación de Google, pero puede pedir una revisión básica.

## Variables de entorno (`RUVIC_GMAIL_*`)

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `RUVIC_GMAIL_CLIENT_ID` | Sí | Client ID del cliente OAuth de escritorio |
| `RUVIC_GMAIL_CLIENT_SECRET` | Sí | Client Secret del mismo cliente OAuth |
| `RUVIC_GMAIL_REFRESH_TOKEN` | Sí | Refresh token obtenido con `get_refresh_token.py` |
| `RUVIC_GMAIL_REQUEST_TIMEOUT` | No (default `30`) | Timeout de solicitud en segundos |

## Pruebas locales

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ./lib

export RUVIC_GMAIL_CLIENT_ID=xxxxx.apps.googleusercontent.com
export RUVIC_GMAIL_CLIENT_SECRET=xxxxx
export RUVIC_GMAIL_REFRESH_TOKEN=xxxxx

python test_connection.py
python validate_local.py
```

`validate_local.py` envía dos correos de prueba reales (uno con adjunto) al
propio buzón autenticado — no requiere un buzón de destino externo.

Prueba también los casos de error (client_secret incorrecto, refresh token
revocado, adjunto inexistente o demasiado grande) y verifica que los
mensajes sean claros.

## Notas de integración

- **OAuth2 de usuario, no cuenta de servicio**: a diferencia de otros
  conectores de Google Workspace que pueden usar delegación de dominio,
  Gmail para cuentas **personales** (@gmail.com) no admite delegación de
  dominio — por eso este conector usa el flujo OAuth2 "installed app" con
  refresh token, que funciona igual para cuentas personales y Workspace.
- **Remitente fijo**: todos los correos se envían desde el buzón que
  autorizó el refresh token; el conector no permite suplantar otro
  remitente (Gmail API lo ignora si se intenta).
- **Alcance mínimo**: solo `gmail.readonly` y `gmail.send`. No puede borrar
  correos, cambiar etiquetas ni modificar configuración del buzón.
- **Límite de adjuntos**: 20 MB por archivo (Gmail acepta ~25 MB totales
  una vez codificado en base64; se deja margen).
- **Expiración del refresh token**: no expira por tiempo si la app OAuth
  está publicada ("In production"); en estado "Testing" puede expirar a
  los 7 días sin uso — si esto ocurre, hay que volver a correr
  `get_refresh_token.py`.
- **Revocación**: si el refresh token se compromete, revócalo desde
  [myaccount.google.com/permissions](https://myaccount.google.com/permissions)
  (el usuario del buzón, buscando la app OAuth) y genera uno nuevo.
- Los errores HTTP 401/403 de la API se clasifican como `GmailAuthError`;
  404 como `GmailDataError`; 429 y 5xx como `GmailNetworkError` (reintentable).
