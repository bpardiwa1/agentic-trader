# app/agents/__init__.py

from .auto_decider import decide_signal as decide_signal

# Explicit re-export for linting tools and clarity
__all__ = ["decide_signal"]
