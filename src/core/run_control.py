"""运行控制异常。

深层动作代码通过抛出轻量异常向外展开调用栈，从而协作式地立即响应暂停或停止。
"""

from __future__ import annotations


class PauseRequested(Exception):
    """请求暂停且当前动作应退出调用栈时抛出。"""


class StopRequested(Exception):
    """请求停止或退出且当前循环应退出调用栈时抛出。"""
