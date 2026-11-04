"""Skill taxonomy: finds canonical skills in free text using configured aliases."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SkillHit:
    skill: str
    alias: str
    snippet: str


class SkillTaxonomy:
    def __init__(self, mapping: dict[str, list[str]]):
        self.mapping = {canonical: list(dict.fromkeys([canonical, *aliases])) for canonical, aliases in mapping.items()}
        self._patterns: list[tuple[str, str, re.Pattern[str]]] = []
        for canonical, aliases in self.mapping.items():
            for alias in sorted(aliases, key=len, reverse=True):
                self._patterns.append((canonical, alias, _alias_pattern(alias)))
        self._lookup = {a.lower(): c for c, al in self.mapping.items() for a in al}

    @classmethod
    def from_file(cls, path: Path) -> "SkillTaxonomy":
        return _load(str(path))

    def canonical(self, name: str) -> str | None:
        """Map a skill name or alias to its canonical name, if known."""
        key = name.strip().lower()
        if key in self._lookup:
            return self._lookup[key]
        hits = self.find(name)
        return hits[0].skill if len(hits) == 1 else None

    def find(self, text: str) -> list[SkillHit]:
        """Return one hit per canonical skill found in `text`, in order of first appearance."""
        if not text:
            return []
        found: dict[str, tuple[int, SkillHit]] = {}
        for canonical, alias, pattern in self._patterns:
            m = pattern.search(text)
            if not m:
                continue
            snippet = _snippet(text, m.start(), m.end())
            if canonical not in found or m.start() < found[canonical][0]:
                found[canonical] = (m.start(), SkillHit(canonical, alias, snippet))
        return [hit for _, hit in sorted(found.values(), key=lambda t: t[0])]

    def skills_in(self, text: str) -> list[str]:
        return [h.skill for h in self.find(text)]


def _snippet(text: str, start: int, end: int, radius: int = 60) -> str:
    """Context around a match, trimmed to whole words."""
    lo, hi = max(0, start - radius), min(len(text), end + radius)
    if lo > 0:
        nxt = text.find(" ", lo, start)
        lo = nxt + 1 if nxt != -1 else lo
    if hi < len(text):
        prev = text.rfind(" ", end, hi)
        hi = prev if prev != -1 else hi
    return ("..." if lo > 0 else "") + " ".join(text[lo:hi].split()) + ("..." if hi < len(text) else "")


def _alias_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias).replace(r"\ ", r"[\s\-]+")
    if len(alias) <= 3:
        # Short acronyms (AR, AP, GL, MIS): exact case, whole word.
        return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])")
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


@lru_cache(maxsize=4)
def _load(path: str) -> SkillTaxonomy:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return SkillTaxonomy({str(k): [str(a) for a in (v or [])] for k, v in data.items()})


def normalize_text(value: str | None) -> str:
    """Lowercase, strip punctuation and collapse whitespace (used for keys and comparisons)."""
    if not value:
        return ""
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())
