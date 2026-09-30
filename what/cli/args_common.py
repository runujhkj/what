import argparse


def add_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=None)
    parser.add_argument("--preset", default=None, choices=["fast", "accurate"])
    parser.add_argument("--profile", default=None)


def add_input_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", default=None, choices=["mic", "file", "stdin", "desktop"])
    parser.add_argument("--stream-tag", default=None, choices=["mic", "desktop", "mixed"],
                        help="override the reported input_source_id regardless of --input "
                             "(e.g. feed mic via stdin but tag it 'mic')")
    parser.add_argument("--file", default=None)
    parser.add_argument("--mic-backend", default=None, choices=["pulse", "alsa", "avfoundation", "dshow"])
    parser.add_argument("--mic-device", default=None)
    parser.add_argument("--mic-enabled", action="store_true")
    parser.add_argument("--no-mic", action="store_true")
    parser.add_argument("--desktop-backend", default=None,
                        choices=["auto", "avfoundation", "pulse", "wasapi"])
    parser.add_argument("--desktop-device", default=None)
    parser.add_argument("--desktop-enabled", action="store_true")
    parser.add_argument("--no-desktop", action="store_true")
    parser.add_argument("--stdin-raw", action="store_true")
    parser.add_argument("--realtime", action="store_true", help="play file input in realtime")


def add_asr_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--engine", choices=["auto", "faster_whisper", "whisperkit", "whisper_cpp"], default=None)
    parser.add_argument("--lang", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--model-path", default=None, help="native engine model directory or identifier")
    parser.add_argument("--worker-path", default=None, help="local native ASR worker executable")
    parser.add_argument("--compute-type", default=None)
    parser.add_argument("--beam-size", type=int, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--device-index", type=int, default=None)
    parser.add_argument("--no-speech-threshold", type=float, default=None)
    parser.add_argument("--logprob-threshold", type=float, default=None)
    parser.add_argument("--compression-ratio-threshold", type=float, default=None)
    parser.add_argument("--condition-on-previous-text", action="store_true")


def add_audio_tuning_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--chunk-ms", type=int, default=None)
    parser.add_argument("--overlap-ms", type=int, default=None)
    parser.add_argument("--frame-ms", type=int, default=None)
    parser.add_argument("--boundary-candidate-points", type=int, default=None)


def add_vad_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--vad-mode", type=int, default=None)
    parser.add_argument("--vad-speech-ratio", type=float, default=None)
    parser.add_argument("--no-vad", action="store_true")


def add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--text-stream", action="store_true")
    parser.add_argument("--no-text-stream", action="store_true")
    parser.add_argument("--text-mode", default=None, choices=["delta", "block", "line"])
    parser.add_argument("--text-window-segments", type=int, default=None)
    parser.add_argument("--text-window-chars", type=int, default=None)
    parser.add_argument("--text-block-clear", action="store_true")
    parser.add_argument("--no-text-block-clear", action="store_true")
    parser.add_argument("--text-normalize", action="store_true")
    parser.add_argument("--no-text-normalize", action="store_true")
    parser.add_argument("--jsonl-log", default=None)
    parser.add_argument("--jsonl-dir", default=None)
