from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    base_url: str
    email: str
    password: str
    proxy_url: str | None
    timeout: int
    debug_html: bool
    stage1_email_field: str | None
    stage2_password_field: str | None

    @property
    def proxies(self) -> dict[str, str] | None:
        if not self.proxy_url:
            return None
        return {"http": self.proxy_url, "https": self.proxy_url}


def load_settings() -> Settings:
    load_dotenv()
    email = os.getenv("BLS_EMAIL", "").strip()
    password = os.getenv("BLS_PASSWORD", "").strip()
    if not email:
        raise RuntimeError("BLS_EMAIL is required. Copy .env.example to .env and set it.")
    if not password:
        raise RuntimeError("BLS_PASSWORD is required. Copy .env.example to .env and set it.")

    return Settings(
        base_url=os.getenv("BLS_BASE_URL", "https://turkey.blsspainglobal.com").rstrip("/"),
        email=email,
        password=password,
        proxy_url=os.getenv("BLS_PROXY_URL") or None,
        timeout=int(os.getenv("BLS_TIMEOUT", "30")),
        debug_html=os.getenv("BLS_DEBUG_HTML", "false").lower() in {"1", "true", "yes"},
        stage1_email_field=os.getenv("BLS_STAGE1_EMAIL_FIELD") or None,
        stage2_password_field=os.getenv("BLS_STAGE2_PASSWORD_FIELD") or None,
    )
