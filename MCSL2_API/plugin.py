from __future__ import annotations

import inspect
from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import Optional
from typing import Type
from typing import TypeVar

from .core import APICore
from .manifest import PluginManifest
from .safety import guard


@dataclass(frozen=True)
class PluginContext:
    core: APICore
    manifest: PluginManifest
    plugin_name: str

    @property
    def backend_window(self) -> Any:
        return self.core.backend_window

    @property
    def interaction(self):
        return self.core.interaction


TPlugin = TypeVar("TPlugin", bound="Plugin")


def entrypoint(*, manifest: PluginManifest, plugin_name: Optional[str] = None):
    def decorator(cls: Type[TPlugin]) -> Type[TPlugin]:
        cls.export(manifest=manifest, plugin_name=plugin_name)
        return cls

    return decorator


class Plugin(ABC):
    manifest: PluginManifest

    def __init__(self, manifest: PluginManifest) -> None:
        self.manifest = manifest

    @abstractmethod
    def on_load(self, context: PluginContext) -> None: ...

    @abstractmethod
    def on_enable(self, context: PluginContext) -> None: ...

    @abstractmethod
    def on_disable(self, context: PluginContext) -> None: ...

    def _register_decorated_subscribers(self, *, context: PluginContext) -> None:
        bus = context.core.events
        for name in dir(self):
            try:
                attr = getattr(self, name)
            except Exception:
                continue
            metas = getattr(attr, "__mcsl2_api_subscribe__", None)
            if not metas:
                continue
            for meta in list(metas):
                try:
                    event_type = meta.get("event_type")
                    background = bool(meta.get("background", True))
                    priority = int(meta.get("priority", 0))
                    bus.subscribe(
                        attr,
                        event_type=event_type,
                        background=background,
                        priority=priority,
                    )
                except Exception:
                    continue

    @classmethod
    def subscribe(
        cls,
        fn: Optional[Callable[..., Any]] = None,
        *,
        event_type: Optional[Type[Any]] = None,
        background: bool = True,
        priority: int = 0,
    ):
        def decorator(real_fn: Callable[..., Any]):
            metas = getattr(real_fn, "__mcsl2_api_subscribe__", None)
            if metas is None:
                metas = []
                setattr(real_fn, "__mcsl2_api_subscribe__", metas)
            metas.append(
                {
                    "event_type": event_type,
                    "background": bool(background),
                    "priority": int(priority),
                }
            )
            return real_fn

        if fn is None:
            return decorator
        return decorator(fn)

    @classmethod
    def export(
        cls: Type[TPlugin],
        *,
        manifest: PluginManifest,
        plugin_name: Optional[str] = None,
    ) -> Any:
        frame = inspect.currentframe()
        caller = None if frame is None else frame.f_back
        module_globals = {} if caller is None else caller.f_globals

        inferred_name = plugin_name or _infer_plugin_name(module_globals)
        label = manifest.id or inferred_name or cls.__name__

        instance = cls(manifest)
        context = PluginContext(
            core=APICore(),
            manifest=manifest,
            plugin_name=inferred_name or label,
        )

        try:
            from Adapters.Plugin import Plugin as LegacyPlugin  # type: ignore
        except Exception:
            legacy = object()
            module_globals[inferred_name or "PluginEntry"] = legacy
            return legacy

        legacy = LegacyPlugin()

        def _load() -> None:
            instance._register_decorated_subscribers(context=context)
            _call_lifecycle(instance.on_load, context)

        def _enable() -> None:
            instance._register_decorated_subscribers(context=context)
            _call_lifecycle(instance.on_enable, context)

        def _disable() -> None:
            _call_lifecycle(instance.on_disable, context)

        legacy.register_loadFunc(guard(label, _load))
        legacy.register_enableFunc(guard(label, _enable))
        legacy.register_disableFunc(guard(label, _disable))

        if inferred_name:
            module_globals[inferred_name] = legacy
        else:
            module_globals["PluginEntry"] = legacy

        return legacy


def _infer_plugin_name(module_globals: dict) -> Optional[str]:
    try:
        mod_name = str(module_globals.get("__name__", ""))
        parts = [p for p in mod_name.split(".") if p]
        if len(parts) >= 1:
            return parts[-1]
    except Exception:
        return None
    return None


def _call_lifecycle(fn: Callable[..., Any], ctx: PluginContext) -> None:
    try:
        sig = inspect.signature(fn)
        if len(sig.parameters) == 0:
            fn()  # type: ignore[misc]
            return
        fn(ctx)
    except TypeError:
        fn(ctx)
