"""Prepare a release: set the version, date the changelog, extract the notes.

The version lives in ``figkit/__init__.py`` and ``pyproject.toml`` reads it
from there, so there is only ever one number to change.

Run by the ``publish`` workflow before it builds, and usable by hand:

    python tools/release_prep.py 0.1.1 --notes-out RELEASE_NOTES.md

The changelog's top-most section must be either the version being released or
an unreleased one; anything else means the entry hasn't been written yet, and
that is a mistake worth stopping for rather than papering over.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import pathlib
import re
import sys

DEFAULT_ROOT = pathlib.Path(__file__).resolve().parent.parent

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-.]?(?:a|b|rc|alpha|beta|dev)\.?\d*)?$")
HEADING_RE = re.compile(r"^## \[?(?P<version>[^\]\s]+)\]?(?:\s*[—-]\s*(?P<date>.+))?$")


def set_version(root: pathlib.Path, version: str) -> str:
    """Set ``figkit.__version__``, which is where pyproject reads it from."""
    init = root / "figkit" / "__init__.py"
    text = init.read_text()
    new, n = re.subn(r'^__version__ = ".*?"$', f'__version__ = "{version}"',
                     text, count=1, flags=re.M)
    if n != 1:
        sys.exit("release_prep: no __version__ found in figkit/__init__.py")
    init.write_text(new)
    return version


def date_changelog(root: pathlib.Path, version: str, date: str) -> tuple[str, str]:
    """Return the dated changelog and the top section's body as release notes.

    Nothing is written here: a release that is going to be refused should leave
    the checkout exactly as it found it.
    """
    changelog = root / "CHANGELOG.md"
    lines = changelog.read_text().splitlines()
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            break
    else:
        sys.exit("release_prep: no '## <version>' section in CHANGELOG.md")

    found = m.group("version")
    if found.lower() not in {version.lower(), "unreleased"}:
        sys.exit(f"release_prep: the top changelog section is [{found}], but "
                 f"{version} is being released — write the entry first")

    lines[i] = f"## [{version}] — {date}"

    end = len(lines)
    for j in range(i + 1, len(lines)):
        if HEADING_RE.match(lines[j]):
            end = j
            break
    notes = "\n".join(lines[i + 1:end]).strip()

    return "\n".join(lines) + "\n", notes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("version", help="version to release, e.g. 0.1.1")
    ap.add_argument("--date", default=_dt.date.today().isoformat())
    ap.add_argument("--notes-out", type=pathlib.Path,
                    help="write the changelog section for this version here")
    ap.add_argument("--root", type=pathlib.Path, default=DEFAULT_ROOT,
                    help="the checkout to operate on (default: this one)")
    args = ap.parse_args()

    version = args.version.lstrip("v").strip()
    if not VERSION_RE.match(version):
        sys.exit(f"release_prep: {version!r} is not a valid version")

    # Both checks run before either file is touched.
    changelog, notes = date_changelog(args.root, version, args.date)
    set_version(args.root, version)
    (args.root / "CHANGELOG.md").write_text(changelog)
    if args.notes_out:
        args.notes_out.write_text(notes + "\n")
    print(version)


if __name__ == "__main__":
    main()
