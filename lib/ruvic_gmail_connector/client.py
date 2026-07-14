"""Cliente de Gmail (cuenta personal o Google Workspace) vía OAuth2 con
refresh token de usuario.

Capacidades:
- list_messages():              buscar/listar correos con filtros (sintaxis
                                 de búsqueda de Gmail).
- get_message():                leer el detalle y cuerpo de un correo.
- send_message():                enviar un correo.
- send_message_with_attachment(): enviar un correo con un archivo adjunto.

Las credenciales SIEMPRE provienen de variables de entorno RUVIC_GMAIL_*
(ver config.GmailConfig.from_env). Prohibido hardcodearlas.
"""

from __future__ import annotations

import base64
import mimetypes
import socket
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from google.auth.exceptions import GoogleAuthError, RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import GmailConfig
from .exceptions import (
    GmailAuthError,
    GmailConnectorError,
    GmailDataError,
    GmailNetworkError,
)
from .logging_utils import get_logger

_TOKEN_URI = "https://oauth2.googleapis.com/token"

# Alcance mínimo: leer/buscar correos y enviarlos. No incluye
# gmail.modify/gmail.settings.basic ni otros scopes de administración.
_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# Límite conservador de adjunto: Gmail acepta ~25 MB totales ya
# codificados en base64 (~+37% de overhead); 20 MB de archivo crudo
# deja margen suficiente.
_MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024


def _wrap_http_error(exc: HttpError) -> GmailConnectorError:
    """Traduce un error HTTP de la API de Gmail a una excepción propia,
    sin dejar escapar nunca el tipo crudo del cliente HTTP."""
    status = exc.resp.status if getattr(exc, "resp", None) is not None else None
    if status in (401, 403):
        return GmailAuthError(
            "Credenciales inválidas o sin permiso suficiente. Verifica que el "
            "refresh token no esté revocado o vencido, y que se haya autorizado "
            "con los scopes gmail.readonly y gmail.send (vuelve a correr "
            "get_refresh_token.py si es necesario)."
        )
    if status == 404:
        return GmailDataError("El mensaje o recurso solicitado no existe.")
    if status == 429 or (status is not None and status >= 500):
        return GmailNetworkError(
            f"Gmail API no respondió correctamente (HTTP {status}). "
            "Puede ser un límite de cuota temporal; reintenta en unos segundos."
        )
    return GmailDataError(f"Error de Gmail API (HTTP {status}): {exc}")


def _validate_no_header_injection(**fields: str | None) -> None:
    """Evita inyección de cabeceras de correo (CRLF) en campos que se
    interpolan directamente en el mensaje MIME (to/cc/bcc/subject)."""
    for name, value in fields.items():
        if value and ("\r" in value or "\n" in value):
            raise GmailDataError(
                f"El campo '{name}' contiene saltos de línea, lo cual no está "
                "permitido (previene inyección de cabeceras de correo)."
            )


def _extract_plain_text(payload: dict[str, Any]) -> str:
    """Recorre las partes MIME de un mensaje y retorna el primer
    text/plain decodificado que encuentre."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return _decode_body(payload["body"]["data"])
    for part in payload.get("parts", []) or []:
        text = _extract_plain_text(part)
        if text:
            return text
    return ""


def _decode_body(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


class GmailClient:
    """Cliente de Gmail para leer y enviar correos vía OAuth2 (refresh token).

    Args:
        config: configuración de conexión. Si se omite, se lee de las
            variables de entorno RUVIC_GMAIL_* (comportamiento estándar
            en el runtime de la plataforma).

    Ejemplo:
        >>> client = GmailClient()          # lee RUVIC_GMAIL_* del entorno
        >>> client.list_messages(query="is:unread", max_results=5)
        [{'id': '18f2...', 'subject': 'Hola', 'from': 'a@b.com', ...}]
    """

    def __init__(self, config: GmailConfig | None = None) -> None:
        self.config = config or GmailConfig.from_env()
        self._logger = get_logger()
        self._service: Any = None

    # ------------------------------------------------------------------ #
    # Conexión
    # ------------------------------------------------------------------ #

    def _get_service(self) -> Any:
        if self._service is not None:
            return self._service
        credentials = Credentials(
            token=None,
            refresh_token=self.config.refresh_token,
            token_uri=_TOKEN_URI,
            client_id=self.config.client_id,
            client_secret=self.config.client_secret,
            scopes=_SCOPES,
        )
        try:
            self._service = build(
                "gmail",
                "v1",
                credentials=credentials,
                cache_discovery=False,
                static_discovery=False,
            )
        except (GoogleAuthError, OSError) as exc:
            raise GmailNetworkError(
                f"No se pudo inicializar el cliente de Gmail: {exc}"
            ) from exc
        return self._service

    def get_authenticated_email(self) -> str:
        """Consulta el perfil del buzón autenticado (confirma identidad y
        que las credenciales OAuth funcionan).

        Returns:
            El correo del buzón autenticado.

        Raises:
            GmailAuthError / GmailNetworkError / GmailDataError según el fallo.
        """
        service = self._get_service()
        try:
            profile = service.users().getProfile(userId="me").execute(num_retries=1)
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        except RefreshError as exc:
            raise GmailAuthError(
                "No se pudo autenticar: el refresh token puede estar revocado, "
                "vencido, o el client_id/client_secret no corresponden al mismo "
                "cliente OAuth con el que se generó. Vuelve a autorizar el "
                "conector para obtener un refresh token nuevo."
            ) from exc
        except (socket.error, TimeoutError) as exc:
            raise GmailNetworkError(f"No se pudo conectar con Gmail API: {exc}") from exc
        email = profile.get("emailAddress", "")
        self._logger.info("Autenticación exitosa, buzón: %s", email)
        return email

    def ping(self) -> bool:
        """Verifica la conexión consultando el perfil del buzón autenticado.

        Returns:
            True si la conexión y las credenciales OAuth funcionan.

        Raises:
            GmailAuthError / GmailNetworkError / GmailDataError según el fallo.
        """
        self.get_authenticated_email()
        return True

    # ------------------------------------------------------------------ #
    # Capacidad 1: listar/buscar correos con filtros
    # ------------------------------------------------------------------ #

    def list_messages(self, query: str = "", max_results: int = 20) -> list[dict[str, Any]]:
        """Busca correos usando la sintaxis de búsqueda de Gmail.

        Args:
            query: filtro de búsqueda de Gmail (ej. "is:unread",
                "from:cliente@dominio.com", "subject:factura after:2026/07/01").
                Cadena vacía = los correos más recientes del buzón.
            max_results: máximo de correos a retornar (default 20, máximo 100).

        Returns:
            Lista de dicts: {"id", "thread_id", "subject", "from", "date", "snippet"}.

        Ejemplo:
            >>> client.list_messages(query="is:unread", max_results=5)
            [{'id': '18f2a1', 'subject': 'Factura pendiente', 'from': 'a@b.com', ...}]
        """
        service = self._get_service()
        max_results = max(1, min(int(max_results), 100))
        try:
            listing = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute(num_retries=1)
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc

        results: list[dict[str, Any]] = []
        for item in listing.get("messages", []):
            try:
                msg = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=item["id"],
                        format="metadata",
                        metadataHeaders=["Subject", "From", "Date"],
                    )
                    .execute(num_retries=1)
                )
            except HttpError as exc:
                raise _wrap_http_error(exc) from exc
            headers = {
                h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])
            }
            results.append(
                {
                    "id": msg["id"],
                    "thread_id": msg.get("threadId"),
                    "subject": headers.get("Subject", ""),
                    "from": headers.get("From", ""),
                    "date": headers.get("Date", ""),
                    "snippet": msg.get("snippet", ""),
                }
            )
        self._logger.info("Se listaron %d mensajes (query=%r)", len(results), query)
        return results

    # ------------------------------------------------------------------ #
    # Capacidad 2: leer el detalle de un correo
    # ------------------------------------------------------------------ #

    def get_message(self, message_id: str) -> dict[str, Any]:
        """Obtiene el detalle completo (incluido el cuerpo) de un correo.

        Args:
            message_id: id del mensaje (obtenido de list_messages).

        Returns:
            Dict con: id, thread_id, subject, from, to, date, body_text.

        Ejemplo:
            >>> client.get_message("18f2a1")
            {'id': '18f2a1', 'subject': 'Hola', 'body_text': 'Buen día...', ...}
        """
        service = self._get_service()
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute(num_retries=1)
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        payload = msg.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
        return {
            "id": msg["id"],
            "thread_id": msg.get("threadId"),
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
            "body_text": _extract_plain_text(payload),
        }

    # ------------------------------------------------------------------ #
    # Capacidad 3: enviar un correo
    # ------------------------------------------------------------------ #

    def send_message(
        self,
        to: str,
        subject: str,
        body_text: str,
        cc: str | None = None,
        bcc: str | None = None,
    ) -> dict[str, Any]:
        """Envía un correo de texto plano desde el buzón delegado.

        Args:
            to: destinatario(s), separados por coma.
            subject: asunto del correo.
            body_text: cuerpo en texto plano.
            cc: copia (opcional).
            bcc: copia oculta (opcional).

        Returns:
            Dict con: id, thread_id del mensaje enviado.

        Ejemplo:
            >>> client.send_message("cliente@dominio.com", "Hola", "Buen día...")
            {'id': '18f2a1', 'thread_id': '18f2a1'}
        """
        _validate_no_header_injection(to=to, subject=subject, cc=cc, bcc=bcc)
        service = self._get_service()
        message = MIMEText(body_text, "plain", "utf-8")
        # Gmail API siempre envía desde el buzón autenticado (el dueño del
        # refresh token); fijar "from" a otra dirección es ignorado por el
        # servidor, así que no se establece aquí.
        message["to"] = to
        message["subject"] = subject
        if cc:
            message["cc"] = cc
        if bcc:
            message["bcc"] = bcc
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        try:
            sent = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute(num_retries=1)
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        self._logger.info("Correo enviado a %s (id=%s)", to, sent.get("id"))
        return {"id": sent["id"], "thread_id": sent.get("threadId")}

    # ------------------------------------------------------------------ #
    # Capacidad 4: enviar un correo con adjunto
    # ------------------------------------------------------------------ #

    def send_message_with_attachment(
        self,
        to: str,
        subject: str,
        body_text: str,
        attachment_path: str,
        cc: str | None = None,
        bcc: str | None = None,
    ) -> dict[str, Any]:
        """Envía un correo de texto plano con un archivo adjunto.

        Args:
            to: destinatario(s), separados por coma.
            subject: asunto del correo.
            body_text: cuerpo en texto plano.
            attachment_path: ruta local del archivo a adjuntar (máx. 20 MB).
            cc: copia (opcional).
            bcc: copia oculta (opcional).

        Returns:
            Dict con: id, thread_id del mensaje enviado.

        Ejemplo:
            >>> client.send_message_with_attachment(
            ...     "cliente@dominio.com", "Reporte", "Adjunto el reporte.",
            ...     "/tmp/reporte.pdf",
            ... )
            {'id': '18f2a1', 'thread_id': '18f2a1'}
        """
        _validate_no_header_injection(to=to, subject=subject, cc=cc, bcc=bcc)
        path = Path(attachment_path)
        if not path.is_file():
            raise GmailDataError(f"El archivo adjunto no existe: {attachment_path}")
        size = path.stat().st_size
        if size > _MAX_ATTACHMENT_BYTES:
            raise GmailDataError(
                f"El adjunto pesa {size / 1_048_576:.1f} MB, supera el límite de "
                f"{_MAX_ATTACHMENT_BYTES / 1_048_576:.0f} MB soportado por el conector."
            )

        service = self._get_service()
        message = MIMEMultipart()
        # Gmail API siempre envía desde el buzón autenticado (el dueño del
        # refresh token); fijar "from" a otra dirección es ignorado por el
        # servidor, así que no se establece aquí.
        message["to"] = to
        message["subject"] = subject
        if cc:
            message["cc"] = cc
        if bcc:
            message["bcc"] = bcc
        message.attach(MIMEText(body_text, "plain", "utf-8"))

        content_type, _ = mimetypes.guess_type(path.name)
        content_type = content_type or "application/octet-stream"
        _, subtype = content_type.split("/", 1)
        with path.open("rb") as f:
            attachment = MIMEApplication(f.read(), _subtype=subtype)
        attachment.add_header("Content-Disposition", "attachment", filename=path.name)
        message.attach(attachment)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        try:
            sent = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute(num_retries=1)
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        self._logger.info(
            "Correo con adjunto '%s' enviado a %s (id=%s)", path.name, to, sent.get("id")
        )
        return {"id": sent["id"], "thread_id": sent.get("threadId")}
