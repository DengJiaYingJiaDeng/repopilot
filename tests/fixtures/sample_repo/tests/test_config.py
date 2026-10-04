from config import load_environment_config


def test_default_name() -> None:
    assert load_environment_config()["server_name"]
