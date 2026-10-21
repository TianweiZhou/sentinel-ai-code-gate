"""What a pull request changed: files, added lines and per-file patches, from `git diff base...head`."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from sentinel.models import ChangedFile

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_MAX_PATCH_CHARS = 20_000


class GitError(RuntimeError):
    pass


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return path.startswith(("tests/", "test/")) or "/tests/" in path or name.startswith("test_") or name.endswith(
        "_test.py") or name == "conftest.py"


def changed_files(root: Path, base: str, head: str = "HEAD") -> list[ChangedFile]:
    """Files changed between the merge-base of `base` and `head` (what the PR introduces)."""
    status_lines = git(root, "diff", "--name-status", "--find-renames", f"{base}...{head}").splitlines()
    patch = git(root, "diff", "--unified=3", "--no-color", "--find-renames", f"{base}...{head}")
    patches = _split_patch(patch)

    files: list[ChangedFile] = []
    for line in status_lines:
        parts = line.split("\t")
        code, path = parts[0][0], parts[-1]
        status = {"A": "added", "D": "deleted", "R": "renamed"}.get(code, "modified")
        text = patches.get(path, "")
        files.append(ChangedFile(
            path=path, status=status,  # type: ignore[arg-type]
            added_lines=_added_lines(text), is_test=is_test_path(path), patch=text[:_MAX_PATCH_CHARS],
        ))
    return files


def _split_patch(patch: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in re.split(r"(?m)^diff --git ", patch)[1:]:
        m = re.search(r"(?m)^\+\+\+ b/(.+)$", chunk) or re.search(r"(?m)^diff --git a/.+ b/(.+)$", "diff --git " + chunk)
        if m:
            out[m.group(1).strip()] = "diff --git " + chunk
    return out


def _added_lines(patch: str) -> list[int]:
    lines: list[int] = []
    current = 0
    for row in patch.splitlines():
        m = _HUNK.match(row)
        if m:
            current = int(m.group(1))
            continue
        if not current or row.startswith(("+++", "---")):
            continue
        if row.startswith("+"):
            lines.append(current)
            current += 1
        elif row.startswith(" "):
            current += 1
    return lines


def added_text(file: ChangedFile) -> list[tuple[int, str]]:
    """(line number, text) of every added line, for pattern checks like secrets or suppressions."""
    rows: list[tuple[int, str]] = []
    current = 0
    for row in file.patch.splitlines():
        m = _HUNK.match(row)
        if m:
            current = int(m.group(1))
            continue
        if not current or row.startswith(("+++", "---")):
            continue
        if row.startswith("+"):
            rows.append((current, row[1:]))
            current += 1
        elif row.startswith(" "):
            current += 1
    return rows


def show(root: Path, ref: str, path: str) -> str | None:
    """File content at a revision, or None if it did not exist there."""
    try:
        return git(root, "show", f"{ref}:{path}")
    except GitError:
        return None


def merge_base(root: Path, base: str, head: str = "HEAD") -> str:
    return git(root, "merge-base", base, head).strip()


def first_party_packages(root: Path) -> set[str]:
    """Top-level importable names that live in this repository (so they are never 'hallucinated')."""
    names: set[str] = set()
    for top in (root, root / "src"):
        if not top.is_dir():
            continue
        for child in top.iterdir():
            if child.name.startswith((".", "_")) and child.name != "__init__.py":
                continue
            if child.is_dir() and (child / "__init__.py").exists():
                names.add(child.name)
            elif child.is_dir() and any(child.glob("*.py")) and child.name not in ("tests", "test"):
                names.add(child.name)  # namespace package
            elif child.suffix == ".py":
                names.add(child.stem)
    return names
