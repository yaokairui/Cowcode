from __future__ import annotations

import shutil

from cowcode.team import BackendType
from cowcode.team.backend.detect import detect


def test_backend_detect_tmux_env(monkeypatch) -> None:
    monkeypatch.setenv("TMUX", "yes")
    assert detect() == BackendType.TMUX


def test_backend_detect_inprocess(monkeypatch) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert detect() == BackendType.IN_PROCESS


def test_backend_detect_iterm(monkeypatch) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    monkeypatch.setattr(
        shutil, "which", lambda name: "/usr/bin/it2" if name == "it2" else None
    )
    assert detect() == BackendType.ITERM2
