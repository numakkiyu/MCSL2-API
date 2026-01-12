from __future__ import annotations

import traceback
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


def guard(
    plugin_label: str,
    fn: Callable[..., T],
    *,
    interaction: Any = None,
    enable_ai_analyze: bool = True,
) -> Callable[..., Optional[T]]:
    def wrapped(*args: Any, **kwargs: Any) -> Optional[T]:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            _log_error(plugin_label, e)
            tb = traceback.format_exc()

            provider = interaction
            if provider is None:
                try:
                    from .core import APICore

                    provider = APICore().interaction
                except Exception:
                    provider = None
            try:
                if provider is None:
                    from PyQt5.QtCore import QCoreApplication

                    if QCoreApplication.instance() is not None:
                        from .interaction import FluentInteraction

                        provider = FluentInteraction()
            except Exception:
                pass

            try:
                if provider is not None:
                    provider.notify(
                        tb,
                        title=f"插件异常：{plugin_label}",
                        level="error",
                    )
            except Exception:
                pass

            if enable_ai_analyze:
                try:
                    from .core import APICore

                    core = APICore()
                    if core.get_mcsl2_version() == "2.3.0.0" and core.get_ai_api_key():
                        fut = core.threading.submit(core.ai_analyze_plugin_error, tb)

                        def _done(f):
                            try:
                                text = f.result()
                            except Exception as ee:
                                text = "AI 分析失败：\n" + str(ee)
                            try:
                                core.interaction.notify(
                                    text,
                                    title=f"AI 报错分析：{plugin_label}",
                                    level="info",
                                )
                            except Exception:
                                return

                        fut.add_done_callback(_done)
                except Exception:
                    pass
            return None

    return wrapped
