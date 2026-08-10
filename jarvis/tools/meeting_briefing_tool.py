"""Before a meeting, pull together what's publicly known about a person or
company plus any prior contact/email history — same composite pattern as
morning_briefing, just reusing whatever search/contacts/email tools are
already registered."""
from __future__ import annotations

from tools.base import Tool, ToolRegistry


class PrepareMeetingBriefingTool(Tool):
    name = "prepare_meeting_briefing"
    description = (
        "Prepare a briefing before a meeting: public web info about a person/company, plus prior "
        "email exchanges and contact info if available. Give a name and optionally a company."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "company": {"type": "string"},
        },
        "required": ["name"],
    }

    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    def run(self, name: str, company: str = "") -> str:
        sections = []
        query = f"{name} {company}".strip()

        if self._registry.get("web_search"):
            sections.append("WEB RESULTS:\n" + self._registry.dispatch("web_search", {"query": query, "max_results": 5}))

        if company and self._registry.get("wikipedia_summary"):
            sections.append("ABOUT THE COMPANY:\n" + self._registry.dispatch("wikipedia_summary", {"topic": company}))

        if self._registry.get("search_contacts"):
            sections.append("CONTACT INFO:\n" + self._registry.dispatch("search_contacts", {"query": name}))

        if self._registry.get("search_emails"):
            sections.append(
                "RECENT EMAIL HISTORY:\n"
                + self._registry.dispatch("search_emails", {"query": name, "max_results": 5})
            )

        if not sections:
            return "No briefing sources configured (web search should always be available — check registry)."
        return "\n\n".join(sections)
