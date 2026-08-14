"""Regression tests for two related config-loading bugs, both requiring a
fresh subprocess to prove: config.py's Config classes read os.environ.get()
at class-definition time, i.e. the moment config.py is first imported -
which has already happened by the time any in-process pytest test runs
(conftest.py already imported `app`, which imports `config`). Re-importing
the already-cached module wouldn't re-trigger that class-body code, so only
a cold subprocess actually proves either fix fires the way a real fresh
`python app.py` launch would.

1. Nothing in the app ever called load_dotenv(), despite python-dotenv
   being a dependency and README.md instructing `cp .env.example .env` as
   the setup step - a fresh clone following the README's own instructions
   only ever saw real OS environment variables, never anything set purely
   in .env.
2. A *present-but-empty* value in .env (e.g. DATABASE_URL=, exactly what
   .env.example itself ships) wasn't treated the same as an absent one -
   os.environ.get(key, default) only falls back to default when the key is
   fully missing, not when it's set to "". Found by reproducing it for
   real: creating .env from the template broke every non-testing
   create_app() call with "Could not parse SQLAlchemy URL from given URL
   string", since SQLALCHEMY_DATABASE_URI silently became "" instead of
   the sqlite default (TestingConfig overrides that var directly, which is
   why the rest of the test suite's own DB was never affected).
"""
import os
import subprocess
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")
MARKER_VALUE = "ausvia-dotenv-test-marker-4f2c9d"


@pytest.fixture
def isolated_dotenv():
    """Backs up the real project .env (if any), lets the test write
    whatever content it needs, and restores the original afterward no
    matter what - this must never permanently alter or lose a developer's
    real .env content."""
    had_existing = os.path.exists(ENV_PATH)
    original_content = None
    if had_existing:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            original_content = f.read()

    def _write(content):
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(content)

    yield _write

    if had_existing:
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(original_content)
    else:
        os.remove(ENV_PATH)


def _run_subprocess(env_overrides, code):
    """env_overrides: {key: value} to set, or {key: None} to guarantee the
    key is genuinely absent - these are not the same thing (a key present
    but set to "" blocks load_dotenv()'s override=False from ever filling
    it in from .env), which is exactly the class of bug these tests exist
    to catch, so getting this helper's own semantics right matters."""
    env = {k: v for k, v in os.environ.items() if k not in env_overrides}
    for key, value in env_overrides.items():
        if value is not None:
            env[key] = value
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=BASE_DIR, env=env, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_a_value_set_only_in_dotenv_is_picked_up_by_config(isolated_dotenv):
    isolated_dotenv(f"AUSVIA_DOTENV_TEST_VAR={MARKER_VALUE}\n")
    # deliberately absent (not just blank - see _run_subprocess's docstring)
    # from the subprocess's real env, so the only way it can end up set is
    # if config.py's own load_dotenv() picked it up
    output = _run_subprocess(
        {"AUSVIA_DOTENV_TEST_VAR": None},
        "import config, os; print(os.environ.get('AUSVIA_DOTENV_TEST_VAR', ''))",
    )
    # os.environ.get with a blank real value would also print "" here, so
    # this alone wouldn't distinguish "loaded from .env" from "blanked by
    # the env dict trick" - the marker value itself proves which happened.
    assert output == MARKER_VALUE


def test_real_environment_variables_still_take_precedence_over_dotenv(isolated_dotenv):
    """load_dotenv()'s default behavior (override=False) must be preserved -
    a real OS/deployment env var should never be silently shadowed by
    whatever happens to be sitting in a checked-in-adjacent .env file."""
    isolated_dotenv("AUSVIA_DOTENV_TEST_VAR=from-dotenv\n")
    output = _run_subprocess(
        {"AUSVIA_DOTENV_TEST_VAR": "from-real-environment"},
        "import config, os; print(os.environ.get('AUSVIA_DOTENV_TEST_VAR', ''))",
    )
    assert output == "from-real-environment"


def test_blank_database_url_in_dotenv_falls_back_to_sqlite_default(isolated_dotenv):
    """The exact bug found live: .env.example (and a freshly-created .env)
    ships DATABASE_URL= with no value - that must behave identically to
    DATABASE_URL being absent entirely, not silently become an empty
    connection string."""
    isolated_dotenv("DATABASE_URL=\n")
    output = _run_subprocess(
        {"DATABASE_URL": ""},
        "import config; print(config.Config.SQLALCHEMY_DATABASE_URI)",
    )
    assert output != ""
    assert output.startswith("sqlite:///")
    assert "instance" in output and "app.db" in output


def test_testing_config_forces_mock_provider_even_with_a_real_env_configured(isolated_dotenv):
    """Found live, not theoretically: TestingConfig never explicitly forced
    AI_PROVIDER to "mock" - it inherited straight from Config, i.e. from
    whatever a developer's real .env happens to have. The moment a real
    .env with AI_PROVIDER=gemini and a real key existed on this machine, 14
    "mock mode is honest" tests across every AI feature started actually
    calling the live provider instead. Tests must never depend on, or
    spend, real API credits regardless of local configuration."""
    isolated_dotenv(
        "AI_PROVIDER=gemini\n"
        "GEMINI_API_KEY=fake-but-present-looking-real-key\n"
        "ANTHROPIC_API_KEY=fake-but-present-looking-real-key\n"
    )
    output = _run_subprocess(
        {"AI_PROVIDER": "gemini", "GEMINI_API_KEY": "fake-but-present-looking-real-key",
         "ANTHROPIC_API_KEY": "fake-but-present-looking-real-key"},
        "import config; c = config.TestingConfig; "
        "print(c.AI_PROVIDER, c.ANTHROPIC_API_KEY, c.GEMINI_API_KEY)",
    )
    assert output == "mock None None"


def test_blank_ai_provider_and_model_vars_fall_back_to_their_real_defaults(isolated_dotenv):
    """Same class of bug, for the other config vars with a real non-empty
    default (AI_PROVIDER, AI_MODEL, GEMINI_MODEL, RATELIMIT_STORAGE_URI) -
    a blank value for any of these must not silently become the empty
    string instead of the intended default."""
    isolated_dotenv("AI_PROVIDER=\nAI_MODEL=\nGEMINI_MODEL=\nRATELIMIT_STORAGE_URI=\n")
    output = _run_subprocess(
        {"AI_PROVIDER": "", "AI_MODEL": "", "GEMINI_MODEL": "", "RATELIMIT_STORAGE_URI": ""},
        "import config; c = config.Config; "
        "print(c.AI_PROVIDER, c.AI_MODEL, c.GEMINI_MODEL, c.RATELIMIT_STORAGE_URI)",
    )
    assert output == "mock claude-opus-5 gemini-3.6-flash memory://"
