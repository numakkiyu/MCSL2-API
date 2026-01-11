"""
下载适配器（MCSL2_API.adapters.download）。

基于 MCSL2Lib.ProgramControllers.downloadController.DownloadTask。
"""

from __future__ import annotations

from typing import Any
from typing import Optional
from typing import Tuple

from ..core import APICore
from ..utils.threading import run_on_ui_thread


class DownloadAdapter:
    """下载相关 API（线程安全入口）。"""

    def __init__(self, core: Optional[APICore] = None) -> None:
        self._core = core or APICore()

    def start_task(
        self,
        url: str,
        *,
        file_path: Optional[str] = None,
        file_name: Optional[str] = None,
        file_size: int = -1,
        extra_data: Optional[Tuple[Any, ...]] = None,
    ) -> Any:
        def _create_on_ui() -> Any:
            try:
                from MCSL2Lib.ProgramControllers.downloadController import DownloadTask
            except Exception:
                return None

            task = DownloadTask(
                url=url,
                file_path=file_path,
                file_name=file_name,
                file_size=file_size,
                extra_data=extra_data,
            )
            task.start_download()
            return task

        try:
            task = run_on_ui_thread(_create_on_ui, wait=True)
            if task is None:
                self._core.interaction.notify(
                    "当前环境未加载 MCSL2Lib，无法创建下载任务。",
                    level="warning",
                )
            return task
        except Exception:
            self._core.interaction.notify("创建下载任务失败。", level="error")
            return None
