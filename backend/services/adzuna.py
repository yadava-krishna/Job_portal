"""Adzuna Jobs API client (official, key-based). https://developer.adzuna.com/"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx

log = logging.getLogger(__name__)
API = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


class AdzunaError(Exception):
    def __init__(self, message: str, *, transient: bool = False):
        super().__init__(message)
        self.transient = transient


@dataclass
class AdzunaJob:
    id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    created: date | None
    salary_min: float | None
    salary_max: float | None
    contract_time: str | None
    contract_type: str | None


class AdzunaClient:
    def __init__(self, app_id: str, app_key: str, country: str = "in", *, transport: httpx.BaseTransport | None = None):
        self.params = {"app_id": app_id, "app_key": app_key}
        self.country = country
        self.http = httpx.Client(timeout=20, transport=transport, headers={"Accept": "application/json"})

    def search(self, what: str, where: str | None, *, max_days_old: int = 1, results: int = 20) -> list[AdzunaJob]:
        params: dict[str, Any] = {**self.params, "what": what, "results_per_page": min(results, 50), "max_days_old": max_days_old,
                                  "sort_by": "date", "content-type": "application/json"}
        if where:
            params["where"] = where
        try:
            r = self.http.get(API.format(country=self.country, page=1), params=params)
        except httpx.HTTPError as exc:
            raise AdzunaError(f"Adzuna unreachable: {type(exc).__name__}", transient=True) from exc
        if r.status_code in (401, 403):
            raise AdzunaError("Adzuna rejected the API credentials.")
        if r.status_code == 429 or r.status_code >= 500:
            raise AdzunaError(f"Adzuna temporarily unavailable (HTTP {r.status_code}).", transient=True)
        if r.status_code >= 400:
            raise AdzunaError(f"Adzuna request failed (HTTP {r.status_code}).")
        return [self._job(x) for x in r.json().get("results", [])]

    @staticmethod
    def _job(x: dict[str, Any]) -> AdzunaJob:
        created = None
        if x.get("created"):
            try:
                created = datetime.fromisoformat(x["created"].replace("Z", "+00:00")).date()
            except ValueError:
                created = None
        return AdzunaJob(
            id=str(x.get("id")), title=(x.get("title") or "").strip(), company=((x.get("company") or {}).get("display_name") or "").strip(),
            location=((x.get("location") or {}).get("display_name") or "").strip(), description=(x.get("description") or "").strip(),
            url=x.get("redirect_url") or "", created=created, salary_min=x.get("salary_min"), salary_max=x.get("salary_max"),
            contract_time=x.get("contract_time"), contract_type=x.get("contract_type"),
        )
