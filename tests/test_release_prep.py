"""The release script decides what gets published, so it gets tests too."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "tools" / "release_prep.py"


def make_repo(tmp_path, changelog: str, version: str = "0.1.0") -> pathlib.Path:
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "figkit"\nversion = "{version}"\n')
    (tmp_path / "CHANGELOG.md").write_text(changelog)
    return tmp_path


def run(root, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args, "--root", str(root)],
                          capture_output=True, text=True)


UNRELEASED = """# Changelog

Preamble that mentions no version.

## [Unreleased]

- Added a thing.

## [0.1.0] — 2026-08-21

- First release.
"""


def test_bumps_version_and_dates_the_changelog(tmp_path):
    root = make_repo(tmp_path, UNRELEASED)
    out = tmp_path / "notes.md"
    r = run(root, "0.2.0", "--date", "2026-09-01", "--notes-out", str(out))
    assert r.returncode == 0, r.stderr

    assert 'version = "0.2.0"' in (root / "pyproject.toml").read_text()
    text = (root / "CHANGELOG.md").read_text()
    assert "## [0.2.0] — 2026-09-01" in text
    assert "Unreleased" not in text
    # The older section keeps its own heading.
    assert "## [0.1.0] — 2026-08-21" in text
    assert out.read_text().strip() == "- Added a thing."


def test_accepts_a_section_already_named_for_the_version(tmp_path):
    root = make_repo(tmp_path, "# Changelog\n\n## [0.2.0] — unreleased\n\n- New.\n")
    r = run(root, "0.2.0", "--date", "2026-09-01")
    assert r.returncode == 0, r.stderr
    assert "## [0.2.0] — 2026-09-01" in (root / "CHANGELOG.md").read_text()


def test_refuses_when_the_entry_was_never_written(tmp_path):
    root = make_repo(tmp_path, "# Changelog\n\n## [0.1.0] — 2026-08-21\n\n- Old.\n")
    r = run(root, "0.2.0")
    assert r.returncode != 0
    assert "write the entry first" in r.stderr
    # Nothing is touched when it refuses.
    assert 'version = "0.1.0"' in (root / "pyproject.toml").read_text()


@pytest.mark.parametrize("bad", ["0.2", "banana", "1.0.0.0", ""])
def test_rejects_versions_that_are_not_versions(tmp_path, bad):
    root = make_repo(tmp_path, UNRELEASED)
    r = run(root, bad)
    assert r.returncode != 0


def test_accepts_a_leading_v_and_prereleases(tmp_path):
    root = make_repo(tmp_path, UNRELEASED)
    r = run(root, "v0.2.0rc1")
    assert r.returncode == 0, r.stderr
    assert 'version = "0.2.0rc1"' in (root / "pyproject.toml").read_text()
