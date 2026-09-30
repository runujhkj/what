import os


def load_env(default_path: str = ".env") -> None:
    path = os.environ.get("WHAT_ENV_FILE", default_path)
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="ascii") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def get_env_int(name: str, default: int | None = None) -> int | None:
    value = get_env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def get_env_float(name: str, default: float | None = None) -> float | None:
    value = get_env(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default
