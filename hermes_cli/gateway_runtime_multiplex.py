"""Which daemon a named-profile client must start when nothing serves its home.

A ``<root>/profiles/<name>`` home that the default multiplexer serves has no daemon of its own.
When the multiplexer is down (restart, update, crash) the profile looks ``absent`` and the ensure
loop would spawn a per-profile gateway for it — a second owner that answers this client and then
blocks the multiplexer's next all-or-nothing reserve (``Cannot reserve gateway profiles``). The
client must start the multiplexer instead, so the start target is decided here from the same facts
the multiplexer boots on (``gateway_multiplex_mode.host_serves_named_profile``): a profile's own
``gateway.standalone: true``, the default profile's explicit ``true``, or — when the flag is unset or
the retired ``false`` that boot settles like unset — the served set the last multiplexer recorded in
the root's ``gateway_state.json`` (a standalone default gateway clears it).
"""
from __future__ import annotations

from pathlib import Path


def multiplexer_root_for(home: Path) -> Path | None:
    """Default root that may multiplex *home*, when *home* is a named profile under it."""
    from hermes_constants import named_profile_home
    if named_profile_home(home) is not None:
        root = home.parent.parent
        return root if root != home else None
    return _root_of_linked_profile(Path(home))


def _root_of_linked_profile(home: Path) -> Path | None:
    """The candidate root whose ``profiles/<name>`` entry resolves to *home*, else None.

    A named profile whose home is a symlink outside ``<root>/profiles/`` (an encrypted or
    off-disk home) resolves to a path that no longer carries the ``<root>/profiles/<name>``
    shape, so root inference by spelling loses it and its clients can never find the
    multiplexer that serves it. Find the root by identity instead: scan the candidate roots'
    ``profiles`` listings for a linked entry that resolves to *home*.
    """
    from hermes_constants import get_default_hermes_root, get_process_hermes_home
    try:
        target = Path(home).resolve(strict=False)
    except OSError:
        return None
    try:
        candidates = [get_default_hermes_root(), get_process_hermes_home()]
    except OSError:
        return None
    seen: set[str] = set()
    for base in candidates:
        profiles = Path(base) / "profiles"
        if str(profiles) in seen or not profiles.is_dir():
            continue
        seen.add(str(profiles))
        try:
            entries = list(profiles.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_symlink() and entry.resolve(strict=False) == target:
                    return Path(base)
            except OSError:
                continue
    return None


def implied_host_root(home: Path) -> Path | None:
    """The root whose gateway must serve named profile *home* when nothing records a verdict.

    ``hermes gateway run`` refuses a ``profiles/<name>`` home a gateway of its own unless it authored
    ``gateway.standalone: true`` (or passes ``--force``); the retired ``multiplex_profiles: false``
    no longer opts out, so only a standalone profile keeps its own daemon.
    """
    root = multiplexer_root_for(home)
    if root is None:
        return None
    from hermes_cli.gateway_multiplex_mode import host_serves_named_profile
    return None if host_serves_named_profile(root, home) is False else root


def multiplexer_serves_home(home: Path) -> Path | None:
    """The root whose (possibly stopped) multiplexer serves *home*, else None.

    ``hermes_cli.gateway.named_profile_served_by_running_multiplexer`` answers the live question;
    this is its offline twin for the moment no gateway runs, deciding from the boot policy
    (:func:`hermes_cli.gateway_multiplex_mode.host_serves_named_profile`): a standalone secondary is
    never served, an explicit ``true`` serves the rest, and an unset or retired ``false`` flag falls
    back to the ``served_profiles`` the last multiplexer recorded. No evidence keeps it unanswered.
    """
    root = multiplexer_root_for(home)
    if root is None:
        return None
    from hermes_cli.gateway_multiplex_mode import host_serves_named_profile
    verdict = host_serves_named_profile(root, home)
    if verdict is not None:
        return root if verdict else None
    from gateway.status import read_runtime_status
    from hermes_cli.profiles import normalize_profile_name
    served = (read_runtime_status(root / "gateway_state.json") or {}).get("served_profiles")
    if not isinstance(served, list):
        return None
    names = {normalize_profile_name(str(p)) for p in served if p}
    return root if normalize_profile_name(home.name) in names else None
