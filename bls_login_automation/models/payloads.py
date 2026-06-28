from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoginStagePayload:
    data: dict[str, str]
    email_field: str


@dataclass(frozen=True)
class CaptchaStagePayload:
    data: dict[str, str]
    password_field: str
    selected_images: list[str]
