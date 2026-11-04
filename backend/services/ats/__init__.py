"""Official public job-board APIs (Greenhouse, Lever, Ashby).

These are the read-only endpoints employers publish so their own careers pages can list openings. They need no
login and no cookies; JobPilot only reads them. Nothing is scraped and nothing is submitted.
"""

from __future__ import annotations

from backend.services.ats.base import AtsError, BoardResult, fetch_board, parse_board_url
from backend.services.ats.cache import board_cache

__all__ = ["AtsError", "BoardResult", "board_cache", "fetch_board", "parse_board_url"]
