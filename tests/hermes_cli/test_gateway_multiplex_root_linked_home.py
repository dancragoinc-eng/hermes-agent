"""Root inference for a profile home that is a symlink outside ``<root>/profiles/``.

A named profile's home may be a symlink to an encrypted or off-disk directory; its
resolved path carries none of the ``<root>/profiles/<name>`` shape, so root inference
by spelling loses it and clients can never find the multiplexer that serves it.
``multiplexer_root_for`` must find the root by identity instead (#149776).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="Symlinks require elevated privileges on Windows"
)


def _linked_layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / ".hermes"
    (root / "profiles").mkdir(parents=True)
    offdisk = tmp_path / "offdisk"
    offdisk.mkdir()
    link = root / "profiles" / "locked"
    link.symlink_to(offdisk)
    return root, offdisk, link


def _pin_roots(monkeypatch, tmp_path: Path, root: Path) -> None:
    import hermes_constants

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(root))
    monkeypatch.setattr(hermes_constants, "_default_hermes_root_memo", None)


def test_multiplexer_root_resolves_a_linked_home_by_identity(tmp_path, monkeypatch):
    from hermes_cli.gateway_runtime_multiplex import multiplexer_root_for

    root, offdisk, link = _linked_layout(tmp_path)
    _pin_roots(monkeypatch, tmp_path, root)

    # The resolved spelling (what discovery canonicalizes to) and the symlink
    # spelling both name the same root.
    assert multiplexer_root_for(offdisk) == root
    assert multiplexer_root_for(offdisk.resolve()) == root
    assert multiplexer_root_for(link) == root


def test_multiplexer_root_ignores_unregistered_paths(tmp_path, monkeypatch):
    from hermes_cli.gateway_runtime_multiplex import multiplexer_root_for

    root, _offdisk, _link = _linked_layout(tmp_path)
    _pin_roots(monkeypatch, tmp_path, root)

    assert multiplexer_root_for(tmp_path / "somewhere-else") is None
