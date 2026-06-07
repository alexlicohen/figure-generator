"""Design Standards Engine: rule catalog (linter) + post-render enforcement (style_guard)."""

from .linter import RULES, Rule, RuleId
from .style_guard import StyleGuardBlocked, enforce

__all__ = ["RULES", "Rule", "RuleId", "StyleGuardBlocked", "enforce"]
