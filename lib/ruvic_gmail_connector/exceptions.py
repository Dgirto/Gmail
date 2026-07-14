"""Excepciones propias del conector Gmail.

Separan los tres tipos de fallo que el usuario debe distinguir:
autenticación, red/servidor y datos. Nunca exponemos excepciones
crípticas del cliente HTTP subyacente.
"""


class GmailConnectorError(Exception):
    """Error base del conector."""


class GmailAuthError(GmailConnectorError):
    """Credenciales inválidas, delegación de dominio no autorizada o permisos insuficientes."""


class GmailNetworkError(GmailConnectorError):
    """No se pudo alcanzar la API de Gmail (red, timeout, error temporal del servidor)."""


class GmailDataError(GmailConnectorError):
    """La operación es válida pero el recurso no existe o los datos son inválidos."""
