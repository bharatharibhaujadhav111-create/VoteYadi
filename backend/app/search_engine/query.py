"""Structured search query – the contract between the AI parser and the engine."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class SearchQuery:
    name: str = ""            # voter name (may be partial / misspelt)
    relation_name: str = ""   # father's / husband's name
    relation_type: str = ""   # father | husband | mother | other
    epic: str = ""            # EPIC / voter id
    any_text: str = ""        # free text that may match either name field
    part: str = ""
    page: int | None = None
    gender: str = ""
    age: int | None = None
    pdf: str = ""
    village: str = ""      # restrict to one village's PDFs ("" = all)
    raw: str = ""
    source: str = "rules"    # rules | llm
    notes: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any([self.name, self.relation_name, self.epic, self.any_text, self.part, self.pdf])

    def has_filters(self) -> bool:
        return bool(self.part or self.pdf or self.page or self.gender or self.age is not None)

    def to_dict(self) -> dict:
        return asdict(self)
