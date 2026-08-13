"""Regression test for the v1 cleanup fix: nothing in the app ever called
load_dotenv(), despite python-dotenv being a dependency and README.md
instructing `cp .env.example .env` as the setup step - a fresh clone
following the README's own instructions only ever saw real OS environment
variables, never anything set purely in .env.

This must run against a fresh subprocess, not in-process: config.py's
Config classes read os.environ.get(...) at class-definition time, i.e. the
moment config.py is first imported - which has already happened by the
time any in-process pytest test runs (conftest.py already imported `app`,
which imports `config`). Re-importing the already-cached module wouldn't
re-trigger that class-body code, so only a cold subprocess actually proves
load_dotenv() fires early enough to matter, the same way a real fresh
`python app.py` launch would.
"""
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")
MARKER_VALUE = "ausvia-dotenv-test-marker-4f2c9d"


def test_a_value_set_only_in_dotenv_is_picked_up_by_config():
    # Defensive backup/restore around the real project .env, if one exists
    # in whatever environment this happens to run in - this test must never
    # permanently alter or lose a developer's real .env content.
    had_existing = os.path.exists(ENV_PATH)
    original_content = None
    if had_existing:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            original_content = f.read()

    try:
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            if original_content:
                f.write(original_content.rstrip("\n") + "\n")
            f.write(f"AUSVIA_DOTENV_TEST_VAR={MARKER_VALUE}\n")

        # A fresh interpreter with AUSVIA_DOTENV_TEST_VAR deliberately absent
        # from its real environment - the only way it can end up set is if
        # config.py's own load_dotenv() call picks it up from .env.
        env = {k: v for k, v in os.environ.items() if k != "AUSVIA_DOTENV_TEST_VAR"}
        result = subprocess.run(
            [sys.executable, "-c", "import config; import os; print(os.environ.get('AUSVIA_DOTENV_TEST_VAR', ''))"],
            cwd=BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == MARKER_VALUE
    finally:
        if had_existing:
            with open(ENV_PATH, "w", encoding="utf-8") as f:
                f.write(original_content)
        else:
            os.remove(ENV_PATH)


def test_real_environment_variables_still_take_precedence_over_dotenv():
    """load_dotenv()'s default behavior (override=False) must be preserved -
    a real OS/deployment env var should never be silently shadowed by
    whatever happens to be sitting in a checked-in-adjacent .env file."""
    had_existing = os.path.exists(ENV_PATH)
    original_content = None
    if had_existing:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            original_content = f.read()

    try:
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            if original_content:
                f.write(original_content.rstrip("\n") + "\n")
            f.write("AUSVIA_DOTENV_TEST_VAR=from-dotenv\n")

        env = {k: v for k, v in os.environ.items() if k != "AUSVIA_DOTENV_TEST_VAR"}
        env["AUSVIA_DOTENV_TEST_VAR"] = "from-real-environment"
        result = subprocess.run(
            [sys.executable, "-c", "import config; import os; print(os.environ.get('AUSVIA_DOTENV_TEST_VAR', ''))"],
            cwd=BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "from-real-environment"
    finally:
        if had_existing:
            with open(ENV_PATH, "w", encoding="utf-8") as f:
                f.write(original_content)
        else:
            os.remove(ENV_PATH)
