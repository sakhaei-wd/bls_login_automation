from __future__ import annotations

import json
import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from bls_login_automation.constants import (
    ID_FIELD,
    REQUEST_VERIFICATION_FIELD,
    RESPONSE_DATA_FIELD,
    RETURN_URL_FIELD,
)
from bls_login_automation.models.payloads import LoginStagePayload
from bls_login_automation.utils.html import form_inputs, soupify

LOGGER = logging.getLogger(__name__)
SPECIAL_FIELDS = {REQUEST_VERIFICATION_FIELD, RESPONSE_DATA_FIELD, RETURN_URL_FIELD, ID_FIELD}


def build_stage1_payload(html: str, *, email: str, forced_email_field: str | None = None) -> LoginStagePayload:
    """Build the first login POST payload.

    Observed flow:
      - The form contains multiple random field names.
      - Exactly one dynamic field receives the e-mail address.
      - ResponseData is JSON containing the dynamic field/value mapping.
      - Id and __RequestVerificationToken are generated server-side and must be reused.
    """
    soup = soupify(html)
    inputs = form_inputs(soup)
    if REQUEST_VERIFICATION_FIELD not in inputs:
        raise ValueError("Stage 1 anti-forgery token not found in login page HTML")

    dynamic_fields = [name for name in inputs if name not in SPECIAL_FIELDS]
    if not dynamic_fields:
        raise ValueError("No dynamic login fields were found")

    email_field = forced_email_field or detect_login_email_field(soup, dynamic_fields)
    if email_field not in dynamic_fields:
        raise ValueError(
            f"Configured/detected e-mail field {email_field!r} is not present. "
            f"Available dynamic fields: {dynamic_fields}"
        )

    response_data = {name: "" for name in dynamic_fields}
    response_data[email_field] = email

    payload: dict[str, str] = {name: response_data[name] for name in dynamic_fields}
    payload[RESPONSE_DATA_FIELD] = json.dumps(response_data, separators=(",", ":"))
    payload[RETURN_URL_FIELD] = inputs.get(RETURN_URL_FIELD, "")
    payload[ID_FIELD] = inputs.get(ID_FIELD, "0")
    payload[REQUEST_VERIFICATION_FIELD] = inputs[REQUEST_VERIFICATION_FIELD]

    LOGGER.info("Stage 1 e-mail field: %s", email_field)
    return LoginStagePayload(data=payload, email_field=email_field)


def detect_login_email_field(soup: BeautifulSoup, dynamic_fields: list[str]) -> str:
    # Prefer semantic hints when present.
    for selector in [
        'input[type="email"]',
        'input[autocomplete="email"]',
        'input[autocomplete="username"]',
    ]:
        tag = soup.select_one(selector)
        if isinstance(tag, Tag) and tag.get("name") in dynamic_fields:
            return str(tag["name"])

    # Next, use labels/placeholders if the site exposes any.
    hints = ("email", "mail", "username", "login")
    for tag in soup.find_all("input"):
        if not isinstance(tag, Tag):
            continue
        name = str(tag.get("name") or "")
        if name not in dynamic_fields:
            continue
        haystack = " ".join(
            str(tag.get(attr) or "") for attr in ("id", "name", "placeholder", "aria-label")
        ).lower()
        if any(hint in haystack for hint in hints):
            return name

    # In the captured flow, only one random text field is visible while the rest
    # are decoys. When no reliable semantic hint exists, use the last dynamic
    # field. This matches the captured request where the e-mail field was the
    # final dynamic key in ResponseData.
    LOGGER.warning("Could not semantically detect e-mail field; falling back to last dynamic field")
    return dynamic_fields[-1]


def find_captcha_url(response_url: str, html: str, base_url: str) -> str | None:
    """Locate the captcha page URL after Stage 1.

    requests follows redirects by default, so response.url may already be the
    /Global/newcaptcha/logincaptcha URL. If not, inspect links in the response.
    """
    if "/Global/newcaptcha/logincaptcha" in response_url.lower():
        return response_url

    soup = soupify(html)
    for tag in soup.find_all(["a", "form"]):
        if not isinstance(tag, Tag):
            continue
        value = tag.get("href") or tag.get("action")
        if value and "/Global/newcaptcha/logincaptcha" in str(value).lower():
            return urljoin(base_url, str(value))
    return None
