from __future__ import annotations


def _routing_detail_line(result: dict) -> str:
    detail = result.get("routing_detail") or {}
    if not isinstance(detail, dict):
        return ""
    derr = str(detail.get("stderr") or detail.get("detail") or "").strip()
    dstdout = str(detail.get("stdout") or "").strip()
    if derr:
        return f"ui: desktop manager api: routing detail: {derr}"
    if dstdout:
        return f"ui: desktop manager api: routing detail: {dstdout}"
    return ""


def _manual_step_lines(result: dict, *, limit: int = 5) -> list[str]:
    steps = result.get("manual_steps") or []
    if not isinstance(steps, list):
        return []
    out: list[str] = []
    for step in steps[: max(0, int(limit))]:
        out.append(f"ui: desktop manager api: next-step: {step}")
    return out


def build_install_log_lines(result: dict, *, configure_routing: bool) -> list[str]:
    lines: list[str] = []
    if result.get("ok"):
        if result.get("routing_ok", True):
            if configure_routing:
                lines.append("ui: desktop manager api: install complete")
            else:
                lines.append("ui: desktop manager api: install complete (driver-only)")
        else:
            err = str(result.get("routing_error") or "routing_failed")
            lines.append(f"ui: desktop manager api: install partial (routing not ready: {err})")
            detail_line = _routing_detail_line(result)
            if detail_line:
                lines.append(detail_line)
            lines.extend(_manual_step_lines(result))
        return lines

    lines.append(f"ui: desktop manager api: install failed ({result.get('error', 'unknown')})")
    detail_line = _routing_detail_line(result)
    if detail_line:
        lines.append(detail_line)

    install_err = str(result.get("stderr") or "").strip()
    install_out = str(result.get("stdout") or "").strip()
    install_code = result.get("code")
    if install_err:
        lines.append(f"ui: desktop manager api: install detail: {install_err}")
    elif install_out:
        lines.append(f"ui: desktop manager api: install detail: {install_out}")
    if install_code is not None:
        lines.append(f"ui: desktop manager api: install code: {install_code}")
    lines.extend(_manual_step_lines(result))
    return lines


def build_uninstall_log_lines(result: dict) -> list[str]:
    lines: list[str] = []
    if result.get("ok"):
        if result.get("routing_ok", True):
            lines.append("ui: desktop manager api: uninstall complete")
        else:
            err = str(result.get("routing_error") or "routing_restore_failed")
            lines.append(f"ui: desktop manager api: uninstall partial (routing restore not ready: {err})")
            detail_line = _routing_detail_line(result)
            if detail_line:
                lines.append(detail_line)
        return lines

    lines.append(f"ui: desktop manager api: uninstall failed ({result.get('error', 'unknown')})")
    detail_line = _routing_detail_line(result)
    if detail_line:
        lines.append(detail_line)
    lines.extend(_manual_step_lines(result))
    return lines

