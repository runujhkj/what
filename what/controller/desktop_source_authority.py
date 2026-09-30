from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class DesktopDeviceRow:
    selector: str
    label: str
    label_lower: str
    is_mic_like: bool
    is_what_target: bool
    is_loopback_like: bool


def parse_desktop_device_rows(rows: list[str]) -> list[DesktopDeviceRow]:
    out: list[DesktopDeviceRow] = []
    for raw in rows or []:
        text = str(raw or "").strip()
        if not text:
            continue
        selector = _parse_selector(text)
        if not selector:
            continue
        label = text
        m = re.match(r"^\s*\d+\s*:\s*(.+?)\s*$", text)
        if m:
            label = m.group(1).strip()
        low = label.lower()
        is_mic = (
            ("microphone" in low)
            or (" mic" in low)
            or ("mic " in low)
            or ("input" in low)
            or ("airpods" in low)
            or ("earbuds" in low)
            or ("hands-free" in low)
            or ("headset" in low)
        )
        is_what = ("what-desktop" in low) or low.startswith("what-")
        is_loopback = (
            ("blackhole" in low)
            or ("loopback" in low)
            or ("soundflower" in low)
            or ("vb-cable" in low)
        )
        out.append(
            DesktopDeviceRow(
                selector=selector,
                label=label,
                label_lower=low,
                is_mic_like=is_mic,
                is_what_target=is_what,
                is_loopback_like=is_loopback,
            )
        )
    return out


def resolve_desktop_roles(
    rows: list[str],
    *,
    current_output_target: str | None,
    current_capture_input: str | None,
    legacy_desktop_device: str | None,
) -> tuple[str, str]:
    parsed = parse_desktop_device_rows(rows)

    output_target = _resolve_output_target(parsed, current_output_target)
    capture_input = _resolve_capture_input(
        parsed,
        current_capture_input=current_capture_input,
        legacy_desktop_device=legacy_desktop_device,
        output_target=output_target,
    )
    return output_target, capture_input


def _parse_selector(raw: str | None) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if text.startswith(":"):
        return text
    m = re.match(r"^\s*(\d+)\s*:", text)
    if m:
        return f":{m.group(1)}"
    return text


def _resolve_output_target(rows: list[DesktopDeviceRow], current_output_target: str | None) -> str:
    cur = str(current_output_target or "").strip().lower()
    if cur:
        for row in rows:
            if row.label_lower == cur:
                return row.label
    for row in rows:
        if row.is_what_target:
            return row.label
    return ""


def _resolve_capture_input(
    rows: list[DesktopDeviceRow],
    *,
    current_capture_input: str | None,
    legacy_desktop_device: str | None,
    output_target: str,
) -> str:
    cur_sel = _parse_selector(current_capture_input)
    legacy_sel = _parse_selector(legacy_desktop_device)
    output_sel = _resolve_output_selector(rows, output_target)
    output_row = None
    if output_sel:
        for row in rows:
            if row.selector == output_sel:
                output_row = row
                break

    # Authoritative rule: when routed desktop output target is a what-* device,
    # capture should bind to that same what-* selector.
    if output_row is not None and not output_row.is_mic_like and output_row.is_what_target:
        return output_row.selector

    if cur_sel:
        for row in rows:
            if row.selector == cur_sel and not row.is_mic_like:
                return row.selector
    if legacy_sel:
        for row in rows:
            if row.selector == legacy_sel and not row.is_mic_like:
                return row.selector

    # Prefer capturing from the active what-* aggregate/output target when
    # available. In current macOS topology this is the authoritative desktop
    # source and avoids true-zero captures seen on loopback-only selectors.
    if output_sel:
        for row in rows:
            if row.selector != output_sel or row.is_mic_like:
                continue
            if row.is_what_target:
                return row.selector

    for row in rows:
        if row.is_mic_like:
            continue
        if row.is_what_target:
            return row.selector

    for row in rows:
        if row.is_mic_like:
            continue
        if row.is_loopback_like:
            return row.selector

    for row in rows:
        if row.is_mic_like:
            continue
        if output_sel and row.selector == output_sel:
            continue
        return row.selector

    return ""


def _resolve_output_selector(rows: list[DesktopDeviceRow], output_target: str | None) -> str:
    target = str(output_target or "").strip().lower()
    if not target:
        return ""
    parsed = _parse_selector(target)
    if parsed.startswith(":"):
        return parsed
    for row in rows:
        if row.label_lower == target:
            return row.selector
    return ""
