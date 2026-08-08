"""Runtime checkout discovery that is safe in a source checkout and an image."""

from pathlib import Path


def collector_repository_root(script_path: Path) -> Path:
    """Return the git checkout when present, otherwise the packaged app root."""

    resolved = script_path.resolve()
    for parent in resolved.parents:
        if (parent / ".git").exists():
            return parent
    for parent in resolved.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return resolved.parent
