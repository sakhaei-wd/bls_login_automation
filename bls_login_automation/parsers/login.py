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
from bls_login_automation.utils.html import css_metric, extract_css_rules, form_inputs, is_hidden_by_css, soupify

LOGGER = logging.getLogger(__name__)
SPECIAL_FIELDS = {REQUEST_VERIFICATION_FIELD, RESPONSE_DATA_FIELD, RETURN_URL_FIELD, ID_FIELD}


def get_stage1_dynamic_fields(html: str) -> list[str]:
    """Return the random login-stage field names in server order."""
    soup = soupify(html)
    inputs = form_inputs(soup)
    return [name for name in inputs if name not in SPECIAL_FIELDS]


def build_stage1_payload(html: str, *, email: str, forced_email_field: str | None = None) -> LoginStagePayload:
    """Build the first login POST payload.

    Observed flow:
      - The form contains multiple random field names.
      - Exactly one dynamic field receives the e-mail address; the rest are decoys.
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
    candidates = rank_login_email_candidates(soup, dynamic_fields)
    if candidates:
        return candidates[0]

    LOGGER.warning("Could not detect e-mail field; falling back to last dynamic field")
    return dynamic_fields[-1]


def rank_login_email_candidates(soup: BeautifulSoup, dynamic_fields: list[str]) -> list[str]:
    """Return best-effort candidate field order for BLS' obfuscated login form.

    BLS renders several random text inputs and only one is the real e-mail field.
    Some pages expose semantic hints; other pages only reveal the correct field
    through CSS visibility/z-index. This function ranks likely fields first but
    main.py can still retry every candidate with fresh tokens if the first guess
    leads to the server-side error URL.
    """
    css_rules = extract_css_rules(soup)
    scored: list[tuple[int, int, str]] = []

    for order, name in enumerate(dynamic_fields):
        tag = soup.find("input", {"name": name})
        if not isinstance(tag, Tag):
            scored.append((0, order, name))
            continue

        score = 0
        input_type = str(tag.get("type") or "").lower()
        if input_type == "email":
            score += 1000
        if input_type in {"text", "email", ""}:
            score += 100

        haystack = " ".join(
            str(tag.get(attr) or "") for attr in ("id", "name", "placeholder", "aria-label", "autocomplete")
        ).lower()
        for hint in ("email", "mail", "username", "login"):
            if hint in haystack:
                score += 500

        # Penalise inputs hidden directly or through their closest container.
        if is_hidden_by_css(tag, css_rules):
            score -= 1000
        parent = tag.find_parent("div")
        if isinstance(parent, Tag):
            if is_hidden_by_css(parent, css_rules):
                score -= 1000
            z_index = css_metric(parent, css_rules, "z_index") or 0
            score += min(z_index, 3000) // 10
            parent_text = parent.get_text(" ", strip=True).lower()
            if "email" in parent_text or "mail" in parent_text:
                score += 300

        # Previous captures often place the active input late in the dynamic list,
        # so use order as a tie-breaker while still allowing better CSS/semantic
        # evidence to win.
        scored.append((score, order, name))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    ranked = [name for _score, _order, name in scored]
    LOGGER.debug("Ranked Stage 1 email candidates: %s", ranked)
    return ranked


def find_captcha_url(response_url: str, html: str, base_url: str) -> str | None:
    """Locate the captcha page URL after Stage 1.

    requests follows redirects by default, so response.url may already be the
    /Global/newcaptcha/logincaptcha URL. If not, inspect links in the response.
    """
    if "/global/newcaptcha/logincaptcha" in response_url.lower():
        return response_url

    soup = soupify(html)
    for tag in soup.find_all(["a", "form", "script"]):
        if not isinstance(tag, Tag):
            continue
        values = [tag.get("href"), tag.get("action"), tag.get_text(" ")]
        for value in values:
            if value and "/global/newcaptcha/logincaptcha" in str(value).lower():
                return urljoin(base_url, str(value))
    return None
