"""Resume Studio API: templates, versions (create from profile, autosave, clone/restore, delete), PDF preview,
cached exports and downloads, feedback and suggest-only improvements."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.api.deps import CurrentUser, DbSession, SettingsDep
from backend.services import studio_service as ss
from backend.services.storage import get_storage
from backend.services.studio_render import TEMPLATES

router = APIRouter(prefix="/studio", tags=["resume studio"])
TemplateKey = Literal["ats_simple", "modern_professional", "technical", "finance", "graduate", "international"]


@router.get("/templates")
def templates(user: CurrentUser, db: DbSession) -> list[dict]:
    ss.ensure_templates(db)
    return [{"key": k, "name": t["name"], "category": t["category"], "ats_safe": t["ats_safe"], "columns": t["columns"],
             "description": t["description"], "max_pages": t.get("max_pages", 2), "supports_docx": True} for k, t in TEMPLATES.items()]


@router.get("/versions")
def versions(user: CurrentUser, db: DbSession) -> list[dict]:
    return [{k: v for k, v in ss.version_out(x).items() if k != "sections"} for x in ss.list_versions(db, user)]


class CreateIn(BaseModel):
    name: str = Field(default="My resume", max_length=120)
    template_key: TemplateKey = "ats_simple"
    target_user_job_id: int | None = None


@router.post("/versions", status_code=status.HTTP_201_CREATED)
def create(body: CreateIn, user: CurrentUser, db: DbSession) -> dict:
    return ss.version_out(ss.create_from_profile(db, user, body.name, body.template_key, body.target_user_job_id))


@router.get("/versions/{version_id}")
def get_version(version_id: int, user: CurrentUser, db: DbSession) -> dict:
    return ss.version_out(ss.owned_version(db, user, version_id))


class SaveIn(BaseModel):
    revision: int | None = None
    name: str | None = Field(default=None, max_length=120)
    template_key: TemplateKey | None = None
    settings: dict[str, Any] | None = None
    sections: list[dict[str, Any]] | None = Field(default=None, max_length=30)


@router.put("/versions/{version_id}")
def save(version_id: int, body: SaveIn, user: CurrentUser, db: DbSession) -> dict:
    return ss.version_out(ss.save(db, user, ss.owned_version(db, user, version_id), body.model_dump(exclude_none=True)))


class CloneIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    target_user_job_id: int | None = None


@router.post("/versions/{version_id}/clone", status_code=status.HTTP_201_CREATED)
def clone(version_id: int, body: CloneIn, user: CurrentUser, db: DbSession) -> dict:
    return ss.version_out(ss.clone(db, user, ss.owned_version(db, user, version_id), body.name, body.target_user_job_id))


@router.delete("/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(version_id: int, user: CurrentUser, db: DbSession) -> None:
    ss.delete(db, user, ss.owned_version(db, user, version_id))


def _file(data: bytes, fmt: str, name: str, inline: bool) -> Response:
    media = "application/pdf" if fmt == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    disp = "inline" if inline else "attachment"
    return Response(data, media_type=media, headers={"Content-Disposition": f'{disp}; filename="{name}"', "Cache-Control": "private, no-store"})


@router.get("/versions/{version_id}/preview.pdf")
def preview(version_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep) -> Response:
    """The live preview is the real PDF (cached per content checksum), so it always matches the export."""
    v = ss.owned_version(db, user, version_id)
    e = ss.export(db, settings, user, v, "pdf")
    r = _file(get_storage().get(e.file_key), "pdf", ss.download_name(v, "pdf"), inline=True)
    r.headers["X-Page-Count"] = str(e.page_count or "")
    return r


class ExportIn(BaseModel):
    format: Literal["pdf", "docx"] = "pdf"


@router.post("/versions/{version_id}/export")
def export(version_id: int, body: ExportIn, user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict:
    v = ss.owned_version(db, user, version_id)
    e = ss.export(db, settings, user, v, body.format)
    return {"id": e.id, "format": e.format, "checksum": e.checksum, "file_sha256": e.file_sha256, "size_bytes": e.size_bytes,
            "page_count": e.page_count, "created_at": e.created_at, "note": getattr(e, "note", None),
            "download_url": f"/studio/exports/{e.id}/download"}


@router.get("/exports/{export_id}/download")
def download(export_id: int, user: CurrentUser, db: DbSession) -> Response:
    e = ss.owned_export(db, user, export_id)
    v = ss.owned_version(db, user, e.resume_version_id)
    return _file(get_storage().get(e.file_key), e.format, ss.download_name(v, e.format), inline=False)


@router.get("/versions/{version_id}/feedback")
def feedback(version_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep, user_job_id: int | None = None) -> dict:
    return ss.feedback(db, settings, user, ss.owned_version(db, user, version_id), user_job_id)


@router.get("/versions/{version_id}/suggestions")
def suggestions(version_id: int, user: CurrentUser, db: DbSession, user_job_id: int | None = None) -> list[dict]:
    return ss.suggestions(db, user, ss.owned_version(db, user, version_id), user_job_id)
