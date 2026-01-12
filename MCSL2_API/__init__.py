"""
MCSL2_API 对外入口。

对插件/AI 侧建议只 import 这里的符号：

    from MCSL2_API import API, Event, core
    from MCSL2Lib.windowInterface import Window

    core.inject_backend(Window())
    API.server.start("生存服")  # 不阻塞 UI（返回 Future）

    @Event.on(Event.Log)
    def on_log(e):
        ...
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapters.download import DownloadAdapter
from .adapters.server import ServerAdapter
from .adapters.ui import UIAdapter
from .core import APICore
from .core import UnsafeAccess
from .manifest import PluginManifest
from .models import LogEvent
from .models import ServerExitEvent
from .models import ServerInfo
from .models import ServerStatus
from .models import State
from .plugin import Plugin
from .plugin import PluginContext


core = APICore()
Context = PluginContext

get_mcsl2_version = core.get_mcsl2_version
get_ai_analyzer_config = core.get_ai_analyzer_config
get_ai_api_key = core.get_ai_api_key
ai_analyze_plugin_error = core.ai_analyze_plugin_error
load_nested_plugin = core.load_nested_plugin


@dataclass(frozen=True)
class _EventNamespace:
    """给插件侧提供 Event.Log/Event.ServerExit 这样的命名空间。"""

    Log = LogEvent
    ServerExit = ServerExitEvent
    ServerStop = ServerExitEvent

    def on(self, event_type, *, background: bool = True):
        return core.events.on(event_type, background=background)

    def subscribe(self, fn=None, *, event_type=None, background: bool = True, priority: int = 0):
        return core.events.subscribe(
            fn,
            event_type=event_type,
            background=background,
            priority=priority,
        )


@dataclass
class _APINamespace:
    """Facade：把 core/adapters/events 组合成稳定 API 入口。"""

    server: ServerAdapter
    download: DownloadAdapter
    ui: UIAdapter

    @property
    def interaction(self):
        return core.interaction

    @property
    def backend_window(self) -> Any:
        return core.backend_window

    @property
    def unsafe_access(self) -> UnsafeAccess:
        return core.unsafe_access


Event = _EventNamespace()
API = _APINamespace(
    server=ServerAdapter(core),
    download=DownloadAdapter(core),
    ui=UIAdapter(core),
)

__all__ = [
    "API",
    "Event",
    "APICore",
    "UnsafeAccess",
    "UIAdapter",
    "Plugin",
    "PluginManifest",
    "PluginContext",
    "Context",
    "LogEvent",
    "ServerExitEvent",
    "ServerInfo",
    "ServerStatus",
    "State",
    "core",
    "get_mcsl2_version",
    "get_ai_analyzer_config",
    "get_ai_api_key",
    "ai_analyze_plugin_error",
    "load_nested_plugin",
]
