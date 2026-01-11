"""
线程与 UI 封送工具（MCSL2_API.utils.threading）。

关键目标：
1) GUI 主线程绝不阻塞：耗时操作必须在后台线程执行。
2) 任何需要触碰 PyQt 对象（特别是 QWidget/QObject/QProcess）的操作必须回到主线程。
3) 事件回调必须可跨线程安全传递，且默认不应阻塞主线程。

实现方式：
- ThreadManager: ThreadPoolExecutor + 装饰器 @run_in_background
- run_on_ui_thread: 将 callable 封送到 Qt 主线程执行（可选择等待返回）

注意：
这里不 import MCSL2Lib；仅依赖 PyQt5（由 MCSL2 项目提供）。
"""

from __future__ import annotations

import functools
import threading
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from typing import Callable
from typing import Optional
from typing import TypeVar
from typing import Union

from PyQt5.QtCore import QObject
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import QThread
from PyQt5.QtCore import Qt
from PyQt5.QtCore import pyqtSignal


T = TypeVar("T")


class _MainThreadInvoker(QObject):
    """
    一个驻留在 Qt 主线程的“函数执行器”。

    背景线程通过 emit 信号把 callable 交给主线程执行，执行结果写入 Future。
    """

    invoke = pyqtSignal(object, object)  # (callable, Future)

    def __init__(self) -> None:
        super().__init__()
        self.invoke.connect(self._run, type=Qt.QueuedConnection)

    def _run(self, fn: Callable[[], Any], fut: Future) -> None:
        if fut.cancelled():
            return
        try:
            fut.set_result(fn())
        except Exception as e:
            fut.set_exception(e)


_invoker: Optional[_MainThreadInvoker] = None
_invoker_lock = threading.Lock()


def _get_invoker() -> _MainThreadInvoker:
    global _invoker

    app = QCoreApplication.instance()
    if app is None:
        raise RuntimeError("Qt application is not initialized yet.")

    if _invoker is None:
        with _invoker_lock:
            if _invoker is None:
                inv = _MainThreadInvoker()
                inv.moveToThread(app.thread())
                _invoker = inv
    return _invoker


def is_ui_thread() -> bool:
    """判断当前线程是否为 Qt 主线程。"""

    app = QCoreApplication.instance()
    if app is None:
        return True
    return QThread.currentThread() == app.thread()


def ensure_ui_ready() -> None:
    app = QCoreApplication.instance()
    if app is None:
        return
    if is_ui_thread():
        _get_invoker()


def run_on_ui_thread(
    func: Callable[..., T], *args: Any, wait: bool = True, **kwargs: Any
) -> Union[T, Future]:
    """
    将函数封送到 Qt 主线程执行。

    Args:
        func: 需要在 UI 线程执行的函数。
        *args/**kwargs: 传参。
        wait: True 表示阻塞当前调用线程直到得到返回值（只会阻塞后台线程，不会阻塞 UI 线程）。

    Returns:
        - wait=True: 返回 func 的返回值
        - wait=False: 返回 concurrent.futures.Future
    """

    if is_ui_thread():
        return func(*args, **kwargs)

    fut: Future = Future()

    def thunk() -> T:
        return func(*args, **kwargs)

    _get_invoker().invoke.emit(thunk, fut)
    return fut.result() if wait else fut


class ThreadManager:
    """
    MCSL2_API 的后台线程管理器。

    推荐用法：
    - 对外 API 函数加 @core.threading.run_in_background，自动放到线程池执行。
    - 需要操作 Qt 对象时，在函数内部用 run_on_ui_thread(...) 进行封送。
    """

    def __init__(self, max_workers: int = 4, thread_name_prefix: str = "MCSL2_API") -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )
        ensure_ui_ready()

    def submit(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> Future:
        return self._executor.submit(fn, *args, **kwargs)

    def run_in_background(self, fn: Callable[..., T]) -> Callable[..., Future]:
        """
        装饰器：让函数自动在线程池中执行。

        注意：被装饰函数返回值会变成 Future。
        """

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Future:
            return self.submit(fn, *args, **kwargs)

        return wrapper
