from pathlib import Path

from dotenv import dotenv_values

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def test_example_environment_keeps_debug_off():
    # With DEBUG on, Django serves HTML debug pages instead of the JSON 404/500 errors.
    assert dotenv_values(ENV_EXAMPLE)["DJANGO_DEBUG"] == "0"
