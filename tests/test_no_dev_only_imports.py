"""graphifyy (the `graphify` package) is a dev-only code-graph CLI, kept out
of requirements.txt entirely (see requirements-dev.txt, DECISIONS.md's
2026-08-26 "graphify" entry) because Railway installs only from
requirements.txt. That split is only safe if nothing under app/ ever
imports it - an import of an untracked package would pass every other test
(the untracked package is right there in the local venv) and only fail in
production, the exact failure mode DEPLOYMENT.md's checklist exists to
catch for migrations, now checked here at the source-tree level instead of
waiting for a deploy to find it.
"""
import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
FORBIDDEN_DEV_ONLY = {"graphify", "graphifyy"}


def _top_level_import_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def test_app_never_imports_dev_only_graph_tool():
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found = _top_level_import_names(tree) & FORBIDDEN_DEV_ONLY
        if found:
            offenders.append(f"{path.relative_to(APP_DIR.parent)}: {sorted(found)}")

    assert not offenders, (
        "app/ must never import a package that isn't in requirements.txt - "
        "Railway installs only from requirements.txt, so this would pass "
        "locally (the package is in the dev venv) and 500 in production "
        "with no test catching it first. Offending file(s):\n" + "\n".join(offenders)
    )
