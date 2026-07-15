"""Structured agent-pipeline HTTP errors (detail / step / fallback_used)."""

from __future__ import annotations


class AgentPipelineHTTPError(Exception):
    """
    Raised by routers when a pipeline step fails.

    Rendered by main.py into:
      {"detail": "...", "step": "assembler", "fallback_used": false}
    """

    def __init__(
        self,
        detail: str,
        *,
        step: str,
        status_code: int = 400,
        fallback_used: bool = False,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.step = step
        self.status_code = status_code
        self.fallback_used = fallback_used
