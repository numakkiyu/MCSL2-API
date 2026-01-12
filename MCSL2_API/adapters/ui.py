from __future__ import annotations

from dataclasses import dataclass
import uuid
from typing import Any
from typing import Callable
from typing import Optional

from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QLayout
from PyQt5.QtWidgets import QWidget

from ..core import APICore
from ..utils.threading import run_on_ui_thread


def _is_layout(obj: Any) -> bool:
    try:
        return isinstance(obj, QLayout)
    except Exception:
        return False


def _is_widget(obj: Any) -> bool:
    try:
        return isinstance(obj, QWidget)
    except Exception:
        return False


@dataclass
class UIAdapter:
    core: APICore

    def _ensure_backend(self) -> Any:
        w = self.core.backend_window
        if w is not None:
            return w
        try:
            from MCSL2Lib.windowInterface import Window  # type: ignore

            win = Window()
            self.core.inject_backend(win)
            return win
        except Exception:
            raise RuntimeError("未注入 MCSL2 Window，无法进行 UI 注入。")

    def resolve(self, path: str) -> Any:
        root = self._ensure_backend()
        cur: Any = root
        p = (path or "").strip()
        if not p:
            return cur
        for part in p.split("."):
            name = part.strip()
            if not name:
                continue
            if not hasattr(cur, name):
                raise AttributeError(f"无法解析 UI 路径: {path}")
            cur = getattr(cur, name)
        return cur

    def add_to_layout(self, layout_path: str, widget: QWidget) -> QWidget:
        def _do() -> QWidget:
            layout = self.resolve(layout_path)
            if not _is_layout(layout):
                raise TypeError(f"目标不是 QLayout: {layout_path}")
            layout.addWidget(widget)  # type: ignore[attr-defined]
            return widget

        return run_on_ui_thread(_do, wait=True)

    def set_text(self, widget_path: str, text: str) -> None:
        def _do() -> None:
            w = self.resolve(widget_path)
            if hasattr(w, "setText"):
                w.setText(str(text))
                return
            raise TypeError(f"目标不支持 setText: {widget_path}")

        run_on_ui_thread(_do, wait=False)

    def add_button(
        self,
        layout_path: str,
        text: str,
        *,
        on_click: Optional[Callable[[], Any]] = None,
        primary: bool = True,
    ) -> QWidget:
        def _do() -> QWidget:
            try:
                if primary:
                    from qfluentwidgets import PrimaryPushButton  # type: ignore

                    btn: QWidget = PrimaryPushButton(str(text))
                else:
                    from qfluentwidgets import PushButton  # type: ignore

                    btn = PushButton(str(text))
            except Exception:
                from PyQt5.QtWidgets import QPushButton

                btn = QPushButton(str(text))

            if on_click is not None:
                try:
                    getattr(btn, "clicked").connect(on_click)  # type: ignore[attr-defined]
                except Exception:
                    pass

            self.add_to_layout(layout_path, btn)
            return btn

        return run_on_ui_thread(_do, wait=True)

    def add_line_edit(
        self,
        layout_path: str,
        *,
        placeholder: str = "",
        text: str = "",
        on_change: Optional[Callable[[str], Any]] = None,
    ) -> QWidget:
        def _do() -> QWidget:
            try:
                from qfluentwidgets import LineEdit  # type: ignore

                le: QWidget = LineEdit()
                if placeholder:
                    le.setPlaceholderText(str(placeholder))  # type: ignore[attr-defined]
                if text:
                    le.setText(str(text))  # type: ignore[attr-defined]
                if on_change is not None:
                    le.textChanged.connect(lambda s: on_change(str(s)))  # type: ignore[attr-defined]
            except Exception:
                from PyQt5.QtWidgets import QLineEdit

                le = QLineEdit()
                if placeholder:
                    le.setPlaceholderText(str(placeholder))
                if text:
                    le.setText(str(text))
                if on_change is not None:
                    le.textChanged.connect(lambda s: on_change(str(s)))

            self.add_to_layout(layout_path, le)  # type: ignore[arg-type]
            return le

        return run_on_ui_thread(_do, wait=True)

    def add_page(
        self,
        *,
        title: str,
        widget: QWidget,
        icon: Any = None,
        position: Any = None,
        object_name: Optional[str] = None,
    ) -> QWidget:
        def _do() -> QWidget:
            win = self._ensure_backend()
            if not _is_widget(win):
                raise RuntimeError("backend_window 不是 QWidget，无法添加页面。")
            name = object_name or f"MCSL2_API_{uuid.uuid4().hex}"
            try:
                widget.setObjectName(name)
            except Exception:
                pass

            ic = icon
            if ic is None:
                try:
                    from qfluentwidgets import FluentIcon as FIF  # type: ignore

                    ic = FIF.APPLICATION
                except Exception:
                    ic = None

            if position is None:
                try:
                    win.addSubInterface(widget, ic, str(title))
                except Exception:
                    win.stackedWidget.addWidget(widget)  # type: ignore[attr-defined]
            else:
                win.addSubInterface(widget, ic, str(title), position=position)
            return widget

        return run_on_ui_thread(_do, wait=True)

    def open_window(
        self,
        widget: QWidget,
        *,
        title: str = "MCSL2_API",
        modal: bool = False,
        parent_path: str = "",
    ) -> QDialog:
        def _do() -> QDialog:
            parent = None
            if parent_path:
                try:
                    parent = self.resolve(parent_path)
                except Exception:
                    parent = None
            dlg = QDialog(parent)
            dlg.setWindowTitle(str(title))
            try:
                from PyQt5.QtWidgets import QVBoxLayout

                layout = QVBoxLayout(dlg)
                layout.addWidget(widget)
                dlg.setLayout(layout)
            except Exception:
                pass
            dlg.setModal(bool(modal))
            dlg.show()
            return dlg

        return run_on_ui_thread(_do, wait=True)
