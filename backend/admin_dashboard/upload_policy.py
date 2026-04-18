"""Validate student uploads against SystemSettings (size + extensions)."""
from __future__ import annotations

import os
from typing import Iterable

from django.core.files.uploadedfile import UploadedFile


def _normalized_extensions(raw: str) -> set[str]:
    parts = {p.strip().lower() for p in (raw or "").split(",") if p.strip()}
    out = set()
    for p in parts:
        if not p.startswith("."):
            p = "." + p
        out.add(p)
    return out or {".py", ".java", ".zip"}


def validate_submission_upload(
    *,
    uploaded_files: Iterable[UploadedFile],
    monaco_files: list[dict],
    allowed_language: str,
    max_mb: int,
    extensions_csv: str,
) -> tuple[bool, str]:
    max_bytes = max(1, int(max_mb)) * 1024 * 1024
    allowed = _normalized_extensions(extensions_csv)

    total = 0
    for f in uploaded_files:
        total += int(f.size or 0)
        name = (f.name or "").lower()
        ext = os.path.splitext(name)[1]
        if ext and ext not in allowed:
            return False, f"File type {ext} is not allowed for uploads. Allowed: {', '.join(sorted(allowed))}."

    for mf in monaco_files:
        name = (mf.get("name") or "").lower()
        content = mf.get("content") or ""
        if isinstance(content, str):
            total += len(content.encode("utf-8"))
        else:
            total += len(content)
        ext = os.path.splitext(name)[1]
        if name and ext and ext not in allowed:
            return False, f"Editor file type {ext} is not allowed. Allowed: {', '.join(sorted(allowed))}."

    if total > max_bytes:
        return False, f"Upload exceeds the maximum size of {max_mb} MB."

    if not list(uploaded_files) and monaco_files:
        default_ext = ".java" if allowed_language == "java" else ".py"
        if default_ext not in allowed:
            return False, f"Pasted code must be allowed as {default_ext}; adjust allowed extensions in admin settings."

    return True, ""
