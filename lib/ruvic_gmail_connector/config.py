"""Configuración del conector leída desde variables de entorno.

Convención de la plataforma: cada campo del formulario de configuración
llega como variable de entorno {ENV_PREFIX}{CAMPO} en mayúsculas.
Para este conector el prefijo es RUVIC_GMAIL_.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ENV_PREFIX = "RUVIC_GMAIL_"


@dataclass(frozen=True)
class GmailConfig:
    """Parámetros de conexión a Gmail vía OAuth2 (refresh token de usuario).

    Funciona tanto con cuentas de Gmail personales como con Google
    Workspace: el refresh_token identifica al usuario que autorizó el
    acceso (obtenido una única vez con el flujo OAuth "installed app").
    """

    client_id: str
    client_secret: str
    refresh_token: str
    request_timeout: int = 30

    @classmethod
    def from_env(cls) -> "GmailConfig":
        """Construye la configuración desde las variables RUVIC_GMAIL_*.

        Raises:
            ValueError: si falta alguna variable obligatoria.

        Ejemplo:
            >>> config = GmailConfig.from_env()
            >>> config.client_id
            '1234567890-abc.apps.googleusercontent.com'
        """
        missing = [
            f"{ENV_PREFIX}{name}"
            for name in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN")
            if not os.environ.get(f"{ENV_PREFIX}{name}")
        ]
        if missing:
            raise ValueError(
                "Faltan variables de entorno del conector gmail: "
                + ", ".join(missing)
                + ". Configura el conector en Settings -> Conectores."
            )

        return cls(
            client_id=os.environ[f"{ENV_PREFIX}CLIENT_ID"],
            client_secret=os.environ[f"{ENV_PREFIX}CLIENT_SECRET"],
            refresh_token=os.environ[f"{ENV_PREFIX}REFRESH_TOKEN"],
            request_timeout=int(os.environ.get(f"{ENV_PREFIX}REQUEST_TIMEOUT", "30")),
        )
