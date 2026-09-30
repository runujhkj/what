import secrets

from .runtime import ServiceRuntime


def mint_token(runtime: ServiceRuntime) -> str:
    token = secrets.token_urlsafe(12)
    with runtime.token_lock:
        runtime.issued_tokens.add(token)
    return token


def consume_token(runtime: ServiceRuntime, token: str) -> bool:
    with runtime.token_lock:
        if token in runtime.issued_tokens:
            runtime.issued_tokens.remove(token)
            return True
    return False
