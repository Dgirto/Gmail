"""Prueba de conexión estándar del conector gmail.

Firma estándar Ruvic: def test_connection() -> tuple[bool, str]
- Lee la configuración EXCLUSIVAMENTE de las env vars RUVIC_GMAIL_*.
- Nunca lanza excepciones; retorna (ok, mensaje).

Ejecutable también como script para pruebas locales:
    python test_connection.py
"""

from __future__ import annotations


def test_connection() -> tuple[bool, str]:
    """Autentica contra Gmail API y consulta el perfil del buzón delegado
    usando las env vars RUVIC_GMAIL_*."""
    try:
        from ruvic_gmail_connector import (
            GmailAuthError,
            GmailClient,
            GmailDataError,
            GmailNetworkError,
        )
    except ImportError:
        return (
            False,
            "La librería ruvic-gmail-connector no está instalada. "
            "Instala con: pip install git+https://github.com/tu-org/"
            "conector-gmail.git#subdirectory=lib",
        )

    try:
        client = GmailClient()  # valida que existan las env vars
    except ValueError as exc:
        return False, str(exc)

    try:
        email = client.get_authenticated_email()
    except GmailAuthError as exc:
        return False, f"Autenticación fallida: {exc}"
    except GmailNetworkError as exc:
        return False, f"Error de red: {exc}"
    except GmailDataError as exc:
        return False, f"Error de datos: {exc}"
    except Exception as exc:  # red de seguridad: jamás propagar
        return False, f"Error inesperado: {exc}"

    return (
        True,
        f"Conexión exitosa al buzón {email}",
    )


if __name__ == "__main__":
    ok, message = test_connection()
    print(f"{'OK' if ok else 'FALLO'}: {message}")
    raise SystemExit(0 if ok else 1)
