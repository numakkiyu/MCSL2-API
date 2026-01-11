from __future__ import annotations

import time

from MCSL2_API import API
from MCSL2_API import Event


_target_server_name: str = ""
_restart_cooldown_s: float = 3.0
_last_restart_at: float = 0.0


@Event.on(Event.ServerExit)
def _on_server_exit(event) -> None:
    global _last_restart_at

    if _target_server_name and event.server_name != _target_server_name:
        return
    if int(event.exit_code) == 0:
        return

    now = time.time()
    if now - _last_restart_at < _restart_cooldown_s:
        return
    _last_restart_at = now

    API.server.start(_target_server_name)


def enable(window_instance, server_name: str) -> None:
    global _target_server_name

    _target_server_name = server_name
    from MCSL2_API import core

    core.inject_backend(window_instance)
    core.events.install_hooks()
    API.server.start(server_name)
