import json
import os
import subprocess
import sys
from pathlib import Path


def _run_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONPATH": "backend/src",
        "EXAM_PREP_APP_ENV": "test",
        "EXAM_PREP_SQLITE_PATH": str(tmp_path / "cli.sqlite3"),
        "EXAM_PREP_MATERIAL_STORAGE_PATH": str(tmp_path / "materials"),
    }
    return subprocess.run(
        [sys.executable, "-m", "exam_prep.packages.cli", *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_package_cli_help_and_create_are_machine_readable(tmp_path: Path) -> None:
    help_result = _run_cli(tmp_path, "--help")
    assert help_result.returncode == 0
    assert "create" in help_result.stdout
    assert "validate" in help_result.stdout
    assert "export" in help_result.stdout

    create = _run_cli(
        tmp_path,
        "create",
        "--course-id",
        "course-1",
        "--title",
        "FRM Part I Offline Package",
    )
    assert create.returncode == 0
    payload = json.loads(create.stdout)
    assert payload["course_id"] == "course-1"
    assert payload["status"] == "draft"


def test_package_cli_missing_package_returns_concise_error(tmp_path: Path) -> None:
    result = _run_cli(tmp_path, "validate", "--package-id", "missing")

    assert result.returncode == 2
    assert "Package not found: missing" in result.stderr
