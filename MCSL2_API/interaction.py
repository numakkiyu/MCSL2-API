"""
多模态交互抽象（MCSL2_API.interaction）。

核心目的：
- API 层不直接调用 GUI 弹窗（避免 headless/脚本模式崩溃）
- API 只调用 interaction.notify(...)，由不同 Provider 决定表现形式

线程要求：
- QtInteraction 必须在 GUI 主线程执行。若从后台线程调用，会自动封送到主线程。
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
import json
from typing import Any
from typing import Callable
from typing import Dict
from typing import Iterable
from typing import Optional

from .utils.threading import run_on_ui_thread


class InteractionProvider(ABC):
    """交互提供者抽象基类。"""

    @abstractmethod
    def notify(self, message: str, title: Optional[str] = None, level: str = "info") -> None:
        """
        发送一条用户可感知的提示信息。

        Args:
            message: 文本内容（建议纯文本）。
            title: 可选标题。
            level: info/warning/error 等，具体表现由实现决定。
        """


class HeadlessInteraction(InteractionProvider):
    """
    无界面交互实现：默认打印到 stdout（可被日志系统接管）。
    """

    def notify(self, message: str, title: Optional[str] = None, level: str = "info") -> None:
        prefix = f"[{level.upper()}]"
        if title:
            print(f"{prefix} {title}: {message}")
        else:
            print(f"{prefix} {message}")


class QtInteraction(InteractionProvider):
    """
    GUI 交互实现：使用 PyQt5 QMessageBox。

    注意：
    - 该实现严格运行在 Qt 主线程。
    - 若从后台线程调用，会自动封送到主线程。
    """

    def __init__(self, parent=None) -> None:
        self._parent = parent

    def notify(self, message: str, title: Optional[str] = None, level: str = "info") -> None:
        def _show() -> None:
            from PyQt5.QtWidgets import QMessageBox

            t = title or "MCSL2_API"
            lvl = (level or "info").lower()
            if lvl in ("warn", "warning"):
                QMessageBox.warning(self._parent, t, message)
            elif lvl in ("error", "critical"):
                QMessageBox.critical(self._parent, t, message)
            else:
                QMessageBox.information(self._parent, t, message)

        run_on_ui_thread(_show, wait=False)


class FluentInteraction(InteractionProvider):
    def __init__(self, parent=None) -> None:
        self._parent = parent

    def notify(self, message: str, title: Optional[str] = None, level: str = "info") -> None:
        def _show() -> None:
            parent = self._parent
            try:
                from PyQt5.QtWidgets import QApplication

                if parent is None:
                    app = QApplication.instance()
                    if app is not None:
                        parent = app.activeWindow()
            except Exception:
                parent = self._parent

            t = title or "MCSL2_API"
            lvl = (level or "info").lower()
            if lvl in ("warn", "warning"):
                t = f"{t}（警告）"
            elif lvl in ("error", "critical"):
                t = f"{t}（错误）"

            try:
                from qfluentwidgets import MessageBox  # type: ignore

                box = MessageBox(t, message, parent=parent)
                box.yesButton.setText("了解")
                try:
                    box.cancelButton.setParent(None)  # type: ignore[attr-defined]
                    box.cancelButton.deleteLater()  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    box.exec()
                except Exception:
                    box.exec_()
                return
            except Exception:
                pass

            try:
                from PyQt5.QtWidgets import QMessageBox

                if lvl in ("warn", "warning"):
                    QMessageBox.warning(parent, t, message)
                elif lvl in ("error", "critical"):
                    QMessageBox.critical(parent, t, message)
                else:
                    QMessageBox.information(parent, t, message)
            except Exception:
                return

        run_on_ui_thread(_show, wait=False)


class CompositeInteraction(InteractionProvider):
    def __init__(self, providers: Iterable[InteractionProvider]) -> None:
        self._providers = list(providers)

    def notify(self, message: str, title: Optional[str] = None, level: str = "info") -> None:
        for p in list(self._providers):
            try:
                p.notify(message, title=title, level=level)
            except Exception:
                continue

    def add(self, provider: InteractionProvider) -> None:
        self._providers.append(provider)


class CallableInteraction(InteractionProvider):
    def __init__(self, fn: Callable[[str, Optional[str], str], Any]) -> None:
        self._fn = fn

    def notify(self, message: str, title: Optional[str] = None, level: str = "info") -> None:
        self._fn(message, title, level)


class HttpInteraction(InteractionProvider):
    def __init__(self, endpoint: str, *, timeout_s: float = 3.0) -> None:
        self._endpoint = str(endpoint)
        self._timeout_s = float(timeout_s)

    def notify(self, message: str, title: Optional[str] = None, level: str = "info") -> None:
        payload: Dict[str, Any] = {
            "message": message,
            "title": title,
            "level": level,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        def _post() -> None:
            try:
                import requests  # type: ignore

                requests.post(
                    self._endpoint,
                    data=body,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                    timeout=self._timeout_s,
                )
            except Exception:
                return

        run_on_ui_thread(_post, wait=False)
