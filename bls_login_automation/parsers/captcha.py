from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from bs4 import Tag

from bls_login_automation.constants import (
    ID_FIELD,
    PARAM_FIELD,
    REQUEST_VERIFICATION_FIELD,
    RESPONSE_DATA_FIELD,
    RETURN_URL_FIELD,
    SELECTED_IMAGES_FIELD,
)
from bls_login_automation.models.payloads import CaptchaStagePayload
from bls_login_automation.utils.html import css_metric, extract_css_rules, form_inputs, is_hidden_by_css, soupify

LOGGER = logging.getLogger(__name__)
SPECIAL_FIELDS = {
    REQUEST_VERIFICATION_FIELD,
    RESPONSE_DATA_FIELD,
    RETURN_URL_FIELD,
    ID_FIELD,
    PARAM_FIELD,
    SELECTED_IMAGES_FIELD,
}


@dataclass(frozen=True)
class CaptchaImageCandidate:
    image_id: str
    left: int
    top: int
    z_index: int


def build_stage2_payload(
    html: str,
    *,
    password: str,
    captcha_url: str,
    forced_password_field: str | None = None,
) -> CaptchaStagePayload:
    """Build the captcha submit payload without solving the captcha.

    The assignment explicitly says to assume all 9 images are selected. We parse
    the 9 currently visible captcha image IDs and submit all of them in
    SelectedImages as comma-separated values.
    """
    soup = soupify(html)
    inputs = form_inputs(soup)
    if REQUEST_VERIFICATION_FIELD not in inputs:
        raise ValueError("Stage 2 anti-forgery token not found in captcha page HTML")

    dynamic_fields = [name for name in inputs if name not in SPECIAL_FIELDS]
    if not dynamic_fields:
        raise ValueError("No dynamic password fields were found on captcha page")

    password_field = forced_password_field or detect_password_field(soup, dynamic_fields)
    if password_field not in dynamic_fields:
        raise ValueError(
            f"Configured/detected password field {password_field!r} is not present. "
            f"Available dynamic fields: {dynamic_fields}"
        )

    image_ids = extract_visible_captcha_image_ids(html)
    if len(image_ids) != 9:
        LOGGER.warning("Expected 9 visible captcha images, extracted %d: %s", len(image_ids), image_ids)
    if not image_ids:
        raise ValueError("No captcha image IDs were extracted")

    response_data = {name: "" for name in dynamic_fields}
    response_data[password_field] = password

    payload: dict[str, str] = {name: response_data[name] for name in dynamic_fields}
    payload[SELECTED_IMAGES_FIELD] = ",".join(image_ids)
    payload[ID_FIELD] = inputs.get(ID_FIELD, "")
    payload[RETURN_URL_FIELD] = inputs.get(RETURN_URL_FIELD, "")
    payload[RESPONSE_DATA_FIELD] = json.dumps(response_data, separators=(",", ":"))
    payload[PARAM_FIELD] = inputs.get(PARAM_FIELD) or extract_param_from_url(captcha_url)
    payload[REQUEST_VERIFICATION_FIELD] = inputs[REQUEST_VERIFICATION_FIELD]

    LOGGER.info("Stage 2 password field: %s", password_field)
    LOGGER.info("Stage 2 selected image ids: %s", image_ids)
    return CaptchaStagePayload(data=payload, password_field=password_field, selected_images=image_ids)


def detect_password_field(soup, dynamic_fields: list[str]) -> str:
    tag = soup.select_one('input[type="password"]')
    if isinstance(tag, Tag) and tag.get("name") in dynamic_fields:
        return str(tag["name"])

    for tag in soup.find_all("input"):
        if not isinstance(tag, Tag):
            continue
        name = str(tag.get("name") or "")
        if name not in dynamic_fields:
            continue
        haystack = " ".join(
            str(tag.get(attr) or "") for attr in ("id", "name", "placeholder", "aria-label")
        ).lower()
        if "password" in haystack or "pwd" in haystack:
            return name

    # The observed captcha request has 10 dynamic fields, only one visible input
    # receives the password. If semantic detection is unavailable, use the third
    # dynamic field, matching the captured order. Users can override with
    # BLS_STAGE2_PASSWORD_FIELD if the site changes.
    LOGGER.warning("Could not semantically detect password field; falling back to third dynamic field")
    if len(dynamic_fields) >= 3:
        return dynamic_fields[2]
    return dynamic_fields[0]


def extract_visible_captcha_image_ids(html: str) -> list[str]:
    soup = soupify(html)
    css_rules = extract_css_rules(soup)
    candidates: list[CaptchaImageCandidate] = []

    for img in soup.select("img.captcha-img"):
        if not isinstance(img, Tag):
            continue
        onclick = str(img.get("onclick") or "")
        match = re.search(r"Select\('([^']+)'", onclick)
        if not match:
            continue
        image_id = match.group(1)
        parent = img.find_parent("div")
        if not isinstance(parent, Tag):
            continue
        if is_hidden_by_css(parent, css_rules):
            continue

        left = css_metric(parent, css_rules, "left")
        top = css_metric(parent, css_rules, "top")
        z_index = css_metric(parent, css_rules, "z_index") or 0
        # Captcha grid uses 0/110/220 for left and top. If position is absent,
        # keep candidate but place it after positioned ones.
        candidates.append(
            CaptchaImageCandidate(
                image_id=image_id,
                left=left if left is not None else 9999,
                top=top if top is not None else 9999,
                z_index=z_index,
            )
        )

    if not candidates:
        return []

    # There are many fake/overlaid captcha elements. For each grid cell, the
    # rendered element is the non-hidden candidate with the highest z-index.
    by_position: dict[tuple[int, int], CaptchaImageCandidate] = {}
    for candidate in candidates:
        key = (candidate.left, candidate.top)
        if key not in by_position or candidate.z_index > by_position[key].z_index:
            by_position[key] = candidate

    visible = list(by_position.values())
    visible_grid = [c for c in visible if c.left != 9999 and c.top != 9999]
    if len(visible_grid) >= 9:
        selected = sorted(visible_grid, key=lambda c: (c.top, c.left))[:9]
    else:
        # Fallback for markup variants: use first 9 non-hidden images.
        selected = candidates[:9]

    return [c.image_id for c in selected]


def extract_param_from_url(captcha_url: str) -> str:
    parsed = urlparse(captcha_url)
    query = parse_qs(parsed.query)
    return query.get("data", [""])[0]
