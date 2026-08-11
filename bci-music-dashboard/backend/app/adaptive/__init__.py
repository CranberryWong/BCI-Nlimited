"""Adaptive BCI-led composition runtime.

The package is deliberately isolated from the legacy generator so the new
contracts can be adopted incrementally without breaking recorded sessions.
"""

from .config import AdaptiveConfigStore
from .runtime import AdaptivePerformanceRuntime

__all__ = ["AdaptiveConfigStore", "AdaptivePerformanceRuntime"]
