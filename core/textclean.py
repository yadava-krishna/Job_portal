"""Text normalisation for resume content (shared by the resume parser and Resume Studio).

Why it exists: resumes made in Word often draw bullets with the Symbol or Wingdings fonts. Their PDFs map those
glyphs to Private Use Area code points (U+F0B7 , U+F0A7 , U+F076 , U+F0D8 , U+F0FC ...) or to nothing, which
PDF text extraction returns as U+FFFD (�). Imported into a profile and printed again by Resume Studio, they became
black boxes: no font has a glyph for them (or the replacement character itself was drawn).

Rules (nothing that carries meaning is removed):
  * invisible characters (zero-width space/joiners, soft hyphen, BOM, word joiner) are dropped;
  * no-break and other Unicode spaces become a normal space, no-break hyphens a normal hyphen;
  * typographic ligatures (ﬁ ﬂ ﬀ ﬃ ﬄ) are expanded to their letters;
  * a Symbol/Wingdings bullet code point becomes "•"; one at the very start of a bullet is dropped (the renderer
    draws its own list marker);
  * U+FFFD and any other Private Use character are NOT guessed at: `unreadable()` reports them so the checker can
    show exactly where they are and the user decides (the export would otherwise print a box).
"""

from __future__ import annotations

import re
import unicodedata

# Symbol / Wingdings bullet glyphs as text extraction maps them (Private Use Area, F0xx).
PUA_BULLETS = frozenset("")
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­᠎"), None)
_SPACES = dict.fromkeys(map(ord, "              　"), " ")
_LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
_LEAD_MARK = re.compile("^[\\s" + "".join(sorted(PUA_BULLETS)) + "•●▪◦‣∙·*\\-]+(?=\\S)")
_UNREADABLE = re.compile("[�-]")


def clean(text: str | None, *, bullet: bool = False) -> str:
    """Normalised text (see module docstring). `bullet=True` also drops a leading bullet mark."""
    if not text:
        return "" if text is None else str(text)
    t = str(text).translate(_INVISIBLE).translate(_SPACES).replace("‑", "-")
    for lig, rep in _LIGATURES.items():
        t = t.replace(lig, rep)
    if bullet:
        t = _LEAD_MARK.sub("", t.lstrip())
    t = "".join("•" if ch in PUA_BULLETS else ch for ch in t)
    return t


def unreadable(text: str | None) -> list[str]:
    """Characters that can't be printed or read reliably (replacement character, Private Use code points)."""
    return sorted(set(_UNREADABLE.findall(text or "")))


def fold(text: str | None) -> str:
    """Comparison form: Unicode-compatible, case-folded, punctuation variants unified, whitespace collapsed. Used to
    check that exported text matches its source, so "–" vs "-" or "’" vs "'" never count as a difference."""
    t = unicodedata.normalize("NFKC", clean(text or ""))
    t = t.translate(str.maketrans({"–": "-", "—": "-", "−": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "•": " "}))
    return " ".join(t.casefold().split())
