from what.controller.desktop_source_authority import (
    parse_desktop_device_rows,
    resolve_desktop_roles,
)


def test_parse_rows_and_classification():
    rows = parse_desktop_device_rows([
        "0: what-desktop",
        "1: BlackHole 2ch",
        "2: Built-in Microphone",
    ])
    assert [r.selector for r in rows] == [":0", ":1", ":2"]
    assert rows[0].is_what_target is True
    assert rows[1].is_loopback_like is True
    assert rows[2].is_mic_like is True


def test_resolve_roles_prefers_what_output_and_what_capture():
    output_target, capture_input = resolve_desktop_roles(
        [
            "0: what-desktop",
            "1: BlackHole 2ch",
            "2: Built-in Microphone",
        ],
        current_output_target="",
        current_capture_input="",
        legacy_desktop_device="",
    )
    assert output_target == "what-desktop"
    assert capture_input == ":0"


def test_resolve_roles_keeps_existing_valid_capture():
    output_target, capture_input = resolve_desktop_roles(
        [
            "0: what-desktop",
            "1: BlackHole 2ch",
            "2: Built-in Microphone",
        ],
        current_output_target="what-desktop",
        current_capture_input=":0",
        legacy_desktop_device=":1",
    )
    assert output_target == "what-desktop"
    assert capture_input == ":0"


def test_resolve_roles_falls_back_to_non_mic_when_no_loopback():
    output_target, capture_input = resolve_desktop_roles(
        [
            "0: what-desktop",
            "2: Built-in Microphone",
            "3: Display Audio",
        ],
        current_output_target="what-desktop",
        current_capture_input="",
        legacy_desktop_device="",
    )
    assert output_target == "what-desktop"
    assert capture_input == ":0"


def test_resolve_roles_legacy_mic_selector_is_rejected():
    output_target, capture_input = resolve_desktop_roles(
        [
            "0: what-desktop",
            "1: BlackHole 2ch",
            "2: Built-in Microphone",
        ],
        current_output_target="",
        current_capture_input="",
        legacy_desktop_device=":2",
    )
    assert output_target == "what-desktop"
    assert capture_input == ":0"
