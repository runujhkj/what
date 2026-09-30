"""
LLM-based transcript cleanup.

Backend-agnostic: MlxCleanupBackend runs locally on Apple Silicon via mlx-lm.
Future backends (ctranslate2, etc.) implement the same clean(text) -> str interface.

Install the mlx backend:
    pip install 'what[cleanup]'
"""

from __future__ import annotations

import logging
import threading
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You clean speech transcripts. "
    "Remove filler words (um, uh, like, you know, sort of, basically, I mean). "
    "Fix capitalization and punctuation. "
    "Output ONLY the cleaned text — no labels, no explanations, no new content."
)

# Markers that indicate the model started looping (reproducing the prompt).
# Truncate output at the first occurrence of any of these.
_LOOP_MARKERS = ("Input:", "Output:", "Example:", "Now clean")

_DEFAULT_MODEL = "mlx-community/Qwen2.5-0.5B-Instruct-4bit"


@runtime_checkable
class CleanupBackend(Protocol):
    def clean(self, text: str) -> str: ...
    @property
    def available(self) -> bool: ...


class NullCleanupBackend:
    """Fallback when no backend is installed — returns text unchanged."""

    @property
    def available(self) -> bool:
        return False

    def clean(self, text: str) -> str:
        return text


class MlxCleanupBackend:
    """Apple Silicon backend using mlx-lm. Lazy-loads on first call."""

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None
        self._tokenizer = None
        self._load_lock = threading.Lock()
        self._load_error: Exception | None = None

    @property
    def available(self) -> bool:
        try:
            import mlx_lm  # noqa: F401
            return True
        except ImportError:
            return False

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            if self._load_error is not None:
                raise self._load_error
            try:
                import mlx_lm
                from huggingface_hub import snapshot_download
                logger.info("llm_cleanup: loading %s", self.model_name)
                # The credential stored in ~/.cache/huggingface/token may be
                # stale/invalid and causes a 401 on public repos.  By calling
                # snapshot_download ourselves with token=False we force anonymous
                # access (bypassing every stored credential, env-var or file),
                # then pass the local cache path to mlx_lm.load which skips the
                # download entirely when the path already exists on disk.
                local_path = snapshot_download(
                    repo_id=self.model_name,
                    token=False,
                    allow_patterns=[
                        "*.json",
                        "model*.safetensors",
                        "*.py",
                        "tokenizer.model",
                        "*.tiktoken",
                        "tiktoken.model",
                        "*.txt",
                        "*.jsonl",
                        "*.jinja",
                    ],
                )
                logger.info("llm_cleanup: model cached at %s — loading weights", local_path)
                model, tokenizer = mlx_lm.load(local_path)
                self._model = model
                self._tokenizer = tokenizer
                logger.info("llm_cleanup: model ready")
            except Exception as exc:
                logger.error("llm_cleanup: failed to load model: %s", exc, exc_info=True)
                self._load_error = exc
                raise

    def clean(self, text: str) -> str:
        self._ensure_loaded()
        import mlx_lm

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
        try:
            prompt = self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception:
            prompt = self._tokenizer.apply_chat_template(
                [{"role": "user", "content": f"{_SYSTEM_PROMPT}\n\n{text}"}],
                tokenize=False,
                add_generation_prompt=True,
            )

        # max_tokens: allow roughly the same number of tokens as the input
        # (cleanup should not expand) but cap at 600 to avoid runaway generation.
        input_word_count = len(text.split())
        max_tokens = max(80, min(600, input_word_count * 2))

        from mlx_lm.sample_utils import make_logits_processors, make_sampler
        result = mlx_lm.generate(
            self._model,
            self._tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            sampler=make_sampler(temp=0.1),
            # repetition_penalty > 1 discourages the looping/repeating behaviour
            # common in small models; passed via logits_processors, not as a kwarg.
            logits_processors=make_logits_processors(repetition_penalty=1.3),
            verbose=False,
        )
        cleaned = result.strip()
        # Truncate at the first sign the model started looping (reproducing
        # the prompt structure).
        for marker in _LOOP_MARKERS:
            idx = cleaned.find(marker)
            if idx > 0:
                cleaned = cleaned[:idx].strip()
        return cleaned


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_backend: CleanupBackend | None = None
_backend_lock = threading.Lock()


def get_backend(model_name: str = _DEFAULT_MODEL) -> CleanupBackend:
    global _backend
    if _backend is not None:
        return _backend
    with _backend_lock:
        if _backend is not None:
            return _backend
        candidate = MlxCleanupBackend(model_name)
        if candidate.available:
            _backend = candidate
            logger.info("llm_cleanup: using MlxCleanupBackend (%s)", model_name)
        else:
            _backend = NullCleanupBackend()
            logger.warning(
                "llm_cleanup: mlx-lm not installed — cleanup disabled. "
                "Run: pip install 'what[cleanup]'"
            )
        return _backend
