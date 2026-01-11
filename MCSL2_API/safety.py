from __future__ import annotations

from typing import Any
from typing import Callable
from typing import Optional
from typing import TypeVar


T = TypeVar("T")


def _log_error(plugin_label: str, err: BaseException) -> None:
    try:
        from MCSL2Lib.utils import MCSL2Logger  # type: ignore

        MCSL2Logger.error(exc=err)
        MCSL2Logger.error(msg=f"[MCSL2_API:{plugin_label}] 插件异常已被隔离")
        return
    except Exception:
        pass

    try:
        print(f"[MCSL2_API:{plugin_label}] 插件异常已被隔离: {err!r}")
    except Exception:
        return


def guard(plugin_label: str, fn: Callable[..., T]) -> Callable[..., Optional[T]]:
    def wrapped(*args: Any, **kwargs: Any) -> Optional[T]:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            _log_error(plugin_label, e)
            return None

    return wrapped
