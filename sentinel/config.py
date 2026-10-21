"""Per-repository settings, read from `[tool.sentinel]` in the target repo's pyproject.toml.

Every team tunes its own bar; nothing here is specific to one project.

    [tool.sentinel]
    min_diff_coverage = 80
    min_mutation_score = 70
    max_complexity = 8
    allowed_packages = ["requests"]            # approved even if not in [project] dependencies
    sensitive_paths = ["migrations/", "auth/"] # any change here always needs a human
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Config:
    min_diff_coverage: float = 80.0
    min_mutation_score: float = 70.0
    max_complexity: int = 8
    max_depth: int = 3
    max_function_lines: int = 40
    max_mutants: int = 20
    allowed_packages: list[str] = field(default_factory=list)
    sensitive_paths: list[str] = field(default_factory=list)
    declared_dependencies: list[str] = field(default_factory=list)
    has_ruff_config: bool = False
    has_mypy_config: bool = False


def _dist_name(requirement: str) -> str:
    """'requests>=2.0 ; python_version>"3.8"' -> 'requests'"""
    return re.split(r"[\s<>=!~;\[(]", requirement.strip(), maxsplit=1)[0].lower().replace("_", "-")


def load(root: Path) -> Config:
    cfg = Config()
    pyproject = root / "pyproject.toml"
    data: dict[str, Any] = tomllib.loads(pyproject.read_text()) if pyproject.exists() else {}

    project = data.get("project", {})
    deps = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        deps.extend(extra)
    for group in data.get("dependency-groups", {}).values():
        deps.extend(d for d in group if isinstance(d, str))
    cfg.declared_dependencies = sorted({_dist_name(d) for d in deps if d})

    tool = data.get("tool", {})
    cfg.has_ruff_config = "ruff" in tool or (root / "ruff.toml").exists() or (root / ".ruff.toml").exists()
    cfg.has_mypy_config = "mypy" in tool or (root / "mypy.ini").exists()

    for key, value in tool.get("sentinel", {}).items():
        attr = key.replace("-", "_")
        if hasattr(cfg, attr):
            setattr(cfg, attr, value)
    return cfg
