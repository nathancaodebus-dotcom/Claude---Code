"""Assembles the ToolRegistry, enabling each integration only if it's configured.

This is what makes 'add a new capability' a one-file change: implement a
Tool subclass, register it here behind whatever config check makes sense,
and it's immediately available to the agent loop and every interface.
"""
from __future__ import annotations

from core.config import config
from core.memory import Memory
from tools.base import ToolRegistry
from tools.memory_tool import RecallFactsTool, RememberFactTool


def build_registry(memory: Memory) -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(RememberFactTool(memory))
    registry.register(RecallFactsTool(memory))

    if config.google_credentials_path:
        try:
            from tools.calendar_tool import CreateEventTool, ListEventsTool
            from tools.gmail_tool import GmailReadTool, GmailSearchTool

            registry.register(GmailSearchTool())
            registry.register(GmailReadTool())
            registry.register(ListEventsTool())
            registry.register(CreateEventTool())
        except ImportError:
            pass  # google-api-python-client not installed; Gmail/Calendar tools stay disabled

    if config.home_assistant_url and config.home_assistant_token:
        from tools.home_assistant_tool import CallServiceTool, ListDevicesTool

        registry.register(ListDevicesTool())
        registry.register(CallServiceTool())

    return registry
