---
name: gmail
description: >
  Usa la librería ruvic_gmail_connector para leer y enviar correos en Gmail
  (Google Workspace) - buscar/listar correos con filtros (list_messages),
  leer el detalle de un correo (get_message), enviar un correo (send_message)
  y enviar un correo con adjunto (send_message_with_attachment). Úsala
  cuando el usuario pida leer, buscar, filtrar o enviar correos por Gmail.
triggers:
- gmail
- correo
- correos
- email
- enviar correo
- leer correos
- bandeja de entrada
- buzón
---

# Conector Gmail (ruvic_gmail_connector)

Librería Python para leer y enviar correos en Gmail (cuenta personal o Google Workspace). Está **preinstalada en el runtime** cuando el conector está configurado (si no, instálala con `pip install git+https://github.com/Dgirto/Gmail.git#subdirectory=lib`). Usa la API oficial de Gmail con OAuth2 y un refresh token obtenido una única vez durante la configuración (no hay flujo de login interactivo en cada ejecución).

## Regla crítica de credenciales

El código generado **NUNCA hardcodea credenciales**. Siempre se leen de variables de entorno, disponibles cuando el conector `gmail` está configurado:

| Variable | Contenido |
|----------|-----------|
| `RUVIC_GMAIL_CLIENT_ID` | Client ID del cliente OAuth de Google Cloud |
| `RUVIC_GMAIL_CLIENT_SECRET` | Client Secret del mismo cliente OAuth |
| `RUVIC_GMAIL_REFRESH_TOKEN` | Refresh token obtenido al autorizar el buzón |
| `RUVIC_GMAIL_REQUEST_TIMEOUT` | (opcional) timeout en segundos, default 30 |

Si estas variables NO existen, el conector no está configurado: no generes código que lo use; indica al usuario que lo configure en **Settings → Conectores**.

## Conexión (siempre igual)

```python
from ruvic_gmail_connector import GmailClient

client = GmailClient()  # lee RUVIC_GMAIL_* del entorno automáticamente
```

## Capacidad 1 — Buscar/listar correos con filtros

```python
# query usa la sintaxis de búsqueda de Gmail: is:unread, from:x@y.com,
# subject:factura, after:2026/07/01, has:attachment, etc.
messages = client.list_messages(query="is:unread", max_results=20)
for m in messages:
    print(f"{m['date']} | {m['from']} | {m['subject']}")
```

## Capacidad 2 — Leer el detalle de un correo

```python
detail = client.get_message(messages[0]["id"])
print(detail["subject"], detail["from"], detail["body_text"])
```

## Capacidad 3 — Enviar un correo

```python
result = client.send_message(
    to="cliente@dominio.com",
    subject="Actualización del ticket",
    body_text="Buen día, le confirmamos que el ticket fue resuelto.",
    cc="supervisor@tuempresa.com",  # opcional
)
print(result["id"])
```

## Capacidad 4 — Enviar un correo con adjunto

```python
result = client.send_message_with_attachment(
    to="cliente@dominio.com",
    subject="Reporte mensual",
    body_text="Adjunto el reporte solicitado.",
    attachment_path="/tmp/reporte.pdf",  # máximo 20 MB
)
print(result["id"])
```

## Manejo de errores

```python
from ruvic_gmail_connector import (
    GmailAuthError, GmailDataError, GmailNetworkError,
)

try:
    client.send_message("cliente@dominio.com", "Asunto", "Cuerpo")
except GmailAuthError:
    print("Credenciales inválidas o refresh token vencido — revisa la configuración del conector")
except GmailNetworkError:
    print("Gmail API no respondió — puede ser un límite de cuota temporal")
except GmailDataError as e:
    print(f"Error de datos: {e}")  # ej. archivo adjunto inexistente
```

## Buenas prácticas al generar código

1. Lee credenciales SOLO de las variables `RUVIC_GMAIL_*` (el constructor de `GmailClient` ya lo hace).
2. Nunca imprimas `RUVIC_GMAIL_CLIENT_SECRET` ni `RUVIC_GMAIL_REFRESH_TOKEN` en logs ni en la salida.
3. Usa `max_results` razonable en `list_messages` (default 20, máximo 100) para no traer la bandeja completa.
4. Todos los correos se envían siempre desde el buzón que autorizó el refresh token; no es posible suplantar otro remitente.
5. `attachment_path` debe ser una ruta local accesible en el runtime; el conector rechaza archivos mayores a 20 MB.
6. El scope del conector es de solo lectura + envío (`gmail.readonly`, `gmail.send`): no puede modificar etiquetas, eliminar correos ni cambiar configuración del buzón.
