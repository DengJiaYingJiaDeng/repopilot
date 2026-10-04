"""Fixture validation helpers."""


def validate_server_config(config: dict[str, str]) -> bool:
    return bool(config.get("server_name"))
