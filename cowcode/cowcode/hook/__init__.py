"""Hook 生命周期挂钩系统。"""

from cowcode.hook.engine import DispatchResult, Engine
from cowcode.hook.event import Event
from cowcode.hook.loader import load

__all__ = ["DispatchResult", "Engine", "Event", "load"]
