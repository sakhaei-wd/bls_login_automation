from __future__ import annotations

import logging
from pathlib import Path

from bls_login_automation.client.session import BrowserSession, form_headers, navigation_headers
from bls_login_automation.config import load_settings
from bls_login_automation.constants import CAPTCHA_SUBMIT_PATH, LOGIN_PATH, LOGIN_SUBMIT_PATH
from bls_login_automation.parsers.captcha import build_stage2_payload
from bls_login_automation.parsers.login import build_stage1_payload, find_captcha_url
from bls_login_automation.utils.logging import configure_logging

LOGGER = logging.getLogger("bls-login-flow")


def save_debug_html(name: str, html: str) -> None:
    out = Path("debug")
    out.mkdir(exist_ok=True)
    (out / name).write_text(html, encoding="utf-8")


def main() -> int:
    configure_logging()
    settings = load_settings()
    client = BrowserSession(proxies=settings.proxies, timeout=settings.timeout)

    base_url = settings.base_url
    login_url = f"{base_url}{LOGIN_PATH}"
    login_submit_url = f"{base_url}{LOGIN_SUBMIT_PATH}"
    captcha_submit_url = f"{base_url}{CAPTCHA_SUBMIT_PATH}"

    # Stage 1: GET login page, parse dynamic values, submit LoginSubmit.
    login_page = client.get(login_url, headers=navigation_headers())
    login_page.raise_for_status()
    if settings.debug_html:
        save_debug_html("stage1_login_page.html", login_page.text)

    stage1 = build_stage1_payload(
        login_page.text,
        email=settings.email,
        forced_email_field=settings.stage1_email_field,
    )
    stage1_response = client.post(
        login_submit_url,
        data=stage1.data,
        headers=form_headers(origin=base_url, referer=login_url),
        allow_redirects=True,
    )
    print(f"Stage 1 HTTP status: {stage1_response.status_code}")
    stage1_response.raise_for_status()
    if settings.debug_html:
        save_debug_html("stage1_response.html", stage1_response.text)

    captcha_url = find_captcha_url(stage1_response.url, stage1_response.text, base_url)
    if not captcha_url:
        raise RuntimeError(
            "Could not locate captcha URL after Stage 1. "
            "Enable BLS_DEBUG_HTML=true and inspect debug/stage1_response.html."
        )
    LOGGER.info("Captcha URL: %s", captcha_url)

    # Stage 2: GET captcha page, select all 9 visible images, submit captcha form.
    captcha_page = client.get(captcha_url, headers=navigation_headers(referer=login_url))
    captcha_page.raise_for_status()
    if settings.debug_html:
        save_debug_html("stage2_captcha_page.html", captcha_page.text)

    stage2 = build_stage2_payload(
        captcha_page.text,
        password=settings.password,
        captcha_url=captcha_url,
        forced_password_field=settings.stage2_password_field,
    )
    captcha_response = client.post(
        captcha_submit_url,
        data=stage2.data,
        headers=form_headers(origin=base_url, referer=captcha_url),
        allow_redirects=True,
    )
    print(f"Stage 2 HTTP status: {captcha_response.status_code}")
    print(f"Stage 2 selected images count: {len(stage2.selected_images)}")
    print(f"Stage 2 selected images: {','.join(stage2.selected_images)}")

    # The expected result for this assignment is HTTP 200 with an invalid captcha
    # selection message because we intentionally submit all 9 images instead of
    # solving the challenge.
    body_preview = captcha_response.text[:1000].replace("\n", " ").strip()
    print("Stage 2 response preview:")
    print(body_preview)
    captcha_response.raise_for_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
