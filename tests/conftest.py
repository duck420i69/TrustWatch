"""Shared pytest fixtures for the TrustWatch test suite.

None of these fixtures require third-party packages (opencv, numpy, mss,
requests). Everything runs on the standard library plus pytest.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trustwatch.config import Config


# Absolute path to the repo root (tests/ lives directly under it).
REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_CONFIG = REPO_ROOT / "config.example.json"


@pytest.fixture
def config(tmp_path):
    """A Config whose data_dir is an isolated temp directory.

    Directories are created so storage/monitor code can write immediately.
    """
    cfg = Config(data_dir=str(tmp_path))
    cfg.ensure_dirs()
    return cfg
