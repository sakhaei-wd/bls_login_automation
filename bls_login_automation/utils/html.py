from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag


@dataclass(frozen=True)
class CssRule:
    display_none: bool = False
    z_index: int | None = None
    left: int | None = None
    top: int | None = None


def soupify(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def extract_css_rules(soup: BeautifulSoup) -> dict[str, CssRule]:
    """Extract only the CSS features we need from inline <style> blocks.

    The captcha page contains many randomly named classes. Some are decoys with
    display:none; some specify z-index or grid coordinates. This parser does not
    try to be a full CSS engine; it extracts the stable properties observed in
    DevTools captures.
    """
    css = "\n".join(style.get_text("\n") for style in soup.find_all("style"))
    rules: dict[str, CssRule] = {}

    for match in re.finditer(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", css, flags=re.S):
        class_name, body = match.group(1), match.group(2)
        display_none = bool(re.search(r"display\s*:\s*none", body, flags=re.I))
        z_index = _int_prop(body, "z-index")
        left = _px_prop(body, "left")
        top = _px_prop(body, "top")
        rules[class_name] = CssRule(
            display_none=display_none,
            z_index=z_index,
            left=left,
            top=top,
        )
    return rules


def is_hidden_by_css(tag: Tag, css_rules: dict[str, CssRule]) -> bool:
    classes = tag.get("class") or []
    return any(css_rules.get(cls, CssRule()).display_none for cls in classes)


def css_metric(tag: Tag, css_rules: dict[str, CssRule], name: str) -> int | None:
    values: list[int] = []
    for cls in tag.get("class") or []:
        rule = css_rules.get(cls)
        value = getattr(rule, name, None) if rule else None
        if value is not None:
            values.append(value)

    style = tag.get("style") or ""
    if name == "left":
        inline = _px_prop(style, "left")
    elif name == "top":
        inline = _px_prop(style, "top")
    elif name == "z_index":
        inline = _int_prop(style, "z-index")
    else:
        inline = None
    if inline is not None:
        values.append(inline)

    if not values:
        return None
    # For z-index use max; for coordinates the site sets only one useful value.
    return max(values)


def find_first_input_value(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("input", {"name": name})
    return tag.get("value", "") if isinstance(tag, Tag) else ""


def form_inputs(soup: BeautifulSoup) -> dict[str, str]:
    inputs: dict[str, str] = {}
    for tag in soup.find_all("input"):
        if not isinstance(tag, Tag):
            continue
        name = tag.get("name")
        if name:
            inputs[str(name)] = str(tag.get("value", ""))
    return inputs


def _int_prop(css_body: str, prop: str) -> int | None:
    match = re.search(rf"{re.escape(prop)}\s*:\s*(-?\d+)", css_body, flags=re.I)
    return int(match.group(1)) if match else None


def _px_prop(css_body: str, prop: str) -> int | None:
    match = re.search(rf"{re.escape(prop)}\s*:\s*(-?\d+)px", css_body, flags=re.I)
    return int(match.group(1)) if match else None
