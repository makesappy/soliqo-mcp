#!/usr/bin/env python3
"""MCP server for Soliqo pipeline operations."""

import json
import math
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from mcp.server.fastmcp import FastMCP


API_BASE = os.getenv("SOLIQO_API_BASE", "https://api.soliqo.online").rstrip("/")
API_KEY = os.getenv("SOLIQO_MCP_API_KEY", "").strip()
REQUEST_TIMEOUT_SECONDS = float(os.getenv("SOLIQO_MCP_TIMEOUT", "180"))
MIN_AUDIO_CHUNK_SIZE_BYTES = 512 * 1024
MAX_AUDIO_CHUNK_SIZE_BYTES = int(
    os.getenv("SOLIQO_MCP_MAX_CHUNK_BYTES", str(5 * 1024 * 1024))
)

if not API_BASE.startswith("http"):
    raise RuntimeError("SOLIQO_API_BASE must be an absolute URL")

if not API_KEY:
    raise RuntimeError("SOLIQO_MCP_API_KEY is required")

mcp = FastMCP("soliqo-mcp")

VALID_SOURCE_TYPES = ("audio", "youtube", "pdf", "podcast")
SUPPORTED_LANGUAGES = ("en", "uk", "ru", "cs", "es", "de", "fr")


def _require_task_id(task_id: str) -> str:
    task_id = (task_id or "").strip()
    if (
        not task_id
        or len(task_id) > 128
        or any(ch in task_id for ch in "/?#& \t\r\n")
    ):
        raise RuntimeError("task_id must be a bare task identifier, not a URL or path")
    return task_id


def _validate_source_type(source_type: str) -> Optional[str]:
    source_type = (source_type or "").strip().lower()
    if source_type and source_type not in VALID_SOURCE_TYPES:
        raise RuntimeError(
            f"source_type must be one of: {', '.join(VALID_SOURCE_TYPES)} (or empty)"
        )
    return source_type or None


def _validate_language(language: str) -> Optional[str]:
    language = (language or "").strip().lower()
    if language and language not in SUPPORTED_LANGUAGES:
        raise RuntimeError(
            f"language must be one of: {', '.join(SUPPORTED_LANGUAGES)} (or empty)"
        )
    return language or None


async def _api_request(
    method: str,
    path: str,
    **kwargs: Any,
) -> Dict[str, Any]:
    headers = {"X-API-Key": API_KEY}
    files = kwargs.pop("files", None)
    data = kwargs.pop("data", None)
    json_payload = kwargs.pop("json", None)
    params = kwargs.pop("params", None)

    async with httpx.AsyncClient(
        base_url=API_BASE,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    ) as client:
        response = await client.request(
            method=method,
            url=path,
            files=files,
            data=data,
            params=params,
            json=json_payload,
            **kwargs,
        )

    if response.status_code >= 400:
        try:
            payload = response.json()
        except ValueError:
            raise RuntimeError(response.text or f"Backend returned HTTP {response.status_code}")
        detail = payload.get("error") or payload.get("detail") or payload
        if isinstance(detail, (dict, list)):
            detail = json.dumps(detail, ensure_ascii=False)
        raise RuntimeError(f"Backend error {response.status_code}: {detail}")

    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


async def _start_audio_upload(
    file_path: Path,
    language: Optional[str] = None,
    chunk_size_bytes: int = 5 * 1024 * 1024,
) -> Dict[str, Any]:
    file_path = file_path.expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        raise RuntimeError(f"File does not exist: {file_path}")
    if chunk_size_bytes < MIN_AUDIO_CHUNK_SIZE_BYTES:
        raise RuntimeError("chunk_size_mb must be at least 0.5")
    if chunk_size_bytes > MAX_AUDIO_CHUNK_SIZE_BYTES:
        max_mb = MAX_AUDIO_CHUNK_SIZE_BYTES / (1024 * 1024)
        raise RuntimeError(f"chunk_size_mb must be <= {max_mb:.1f}")

    total_size = file_path.stat().st_size
    if total_size <= 0:
        raise RuntimeError(f"Empty file: {file_path}")

    total_chunks = int(math.ceil(total_size / chunk_size_bytes))
    upload_id = str(uuid.uuid4())

    with file_path.open("rb") as fp:
        for chunk_number in range(total_chunks):
            chunk = fp.read(chunk_size_bytes)
            if not chunk:
                break

            response = await _api_request(
                "POST",
                "/api/audio/upload/chunk",
                data={
                    "upload_id": upload_id,
                    "chunk_number": str(chunk_number),
                    "total_chunks": str(total_chunks),
                    "total_size": str(total_size),
                    "filename": file_path.name,
                    "language": language or "",
                },
                files={"file": (file_path.name, chunk, "application/octet-stream")},
            )
            if not response.get("upload_id"):
                raise RuntimeError(f"Unexpected upload-chunk response for chunk {chunk_number}")

    complete_payload = {"upload_id": upload_id}
    completed = await _api_request(
        "POST",
        "/api/audio/upload/complete",
        data=complete_payload,
    )
    return {
        "upload_id": upload_id,
        "task_id": completed.get("task_id"),
        "message": completed.get("message"),
        "locked": completed.get("locked"),
    }


@mcp.tool()
async def audio_process_file(
    file_path: str,
    language: str = "",
    chunk_size_mb: float = 5.0,
) -> Dict[str, Any]:
    """Upload a local audio file through chunked backend API and start processing."""
    chunk_size_bytes = int(chunk_size_mb * 1024 * 1024)
    return await _start_audio_upload(
        Path(file_path),
        language=language or None,
        chunk_size_bytes=max(chunk_size_bytes, 1),
    )


@mcp.tool()
async def youtube_process(url: str, language: str = "") -> Dict[str, Any]:
    """Submit a YouTube URL for summarization."""
    payload: Dict[str, str] = {"url": url}
    if language:
        payload["language"] = language
    return await _api_request("POST", "/api/youtube/process", json=payload)


@mcp.tool()
async def pdf_process(file_path: str, language: str = "") -> Dict[str, Any]:
    """Upload a PDF file and start summarization."""
    target = Path(file_path).expanduser().resolve()
    if not target.exists() or not target.is_file():
        raise RuntimeError(f"File does not exist: {target}")

    with target.open("rb") as fp:
        data = {"language": language} if language else {}
        return await _api_request(
            "POST",
            "/api/pdf/upload",
            data=data,
            files={"file": (target.name, fp, "application/pdf")},
        )


@mcp.tool()
async def tasks_get_status(task_id: str) -> Dict[str, Any]:
    """Get task status/result by ID. Returns title, summary, transcript, edit state when completed."""
    return await _api_request("GET", f"/api/audio/{_require_task_id(task_id)}")


@mcp.tool()
async def tasks_get_pipeline(task_id: str) -> Dict[str, Any]:
    """Get pipeline execution metadata by task ID."""
    return await _api_request("GET", f"/api/audio/{_require_task_id(task_id)}/pipeline")


@mcp.tool()
async def tasks_delete(task_id: str) -> Dict[str, Any]:
    """Delete a completed or failed task."""
    return await _api_request("DELETE", f"/api/audio/{_require_task_id(task_id)}")


@mcp.tool()
async def notes_list(
    page: int = 1,
    page_size: int = 20,
    source_type: str = "",
) -> Dict[str, Any]:
    """List notes (processed summaries) with pagination, newest first.

    source_type optionally filters by source: audio, youtube, pdf or podcast.
    """
    if page < 1 or page_size < 1 or page_size > 100:
        raise RuntimeError("page must be >= 1 and page_size in 1..100")
    params: Dict[str, Any] = {"page": page, "page_size": page_size}
    source = _validate_source_type(source_type)
    if source:
        params["type"] = source
    return await _api_request("GET", "/api/audio/history", params=params)


@mcp.tool()
async def notes_list_all(source_type: str = "") -> Dict[str, Any]:
    """List every note without pagination (for full-sync style queries)."""
    params: Dict[str, Any] = {}
    source = _validate_source_type(source_type)
    if source:
        params["type"] = source
    return await _api_request("GET", "/api/audio/history/all", params=params)


@mcp.tool()
async def note_get(task_id: str) -> Dict[str, Any]:
    """Get full note detail by task ID: title, summary, transcript, language, edit state."""
    return await _api_request("GET", f"/api/audio/{_require_task_id(task_id)}")


@mcp.tool()
async def note_get_transcription(task_id: str) -> Dict[str, Any]:
    """Get the full transcript of a note by task ID."""
    result = await _api_request("GET", f"/api/audio/{_require_task_id(task_id)}")
    payload = {
        "task_id": result.get("task_id", task_id),
        "status": result.get("status"),
        "language": result.get("language"),
        "transcript": result.get("transcript"),
        "speaker_segments": result.get("speaker_segments"),
    }
    if payload["transcript"] is None:
        payload["hint"] = (
            "No transcript yet: the task may still be processing, have failed, "
            "or be locked. Check note_get for the current status."
        )
    return payload


@mcp.tool()
async def note_edit_summary(task_id: str, instruction: str) -> Dict[str, Any]:
    """Edit a note's summary with a natural-language instruction.

    Asynchronous: returns immediately; poll note_get until summary_edit_state
    is no longer "processing".
    """
    instruction = (instruction or "").strip()
    if not instruction:
        raise RuntimeError("instruction is required")
    return await _api_request(
        "POST",
        f"/api/audio/{_require_task_id(task_id)}/edit-summary",
        json={"instruction": instruction},
    )


@mcp.tool()
async def note_reset_summary(task_id: str) -> Dict[str, Any]:
    """Restore a note's original AI-generated summary, discarding manual edits."""
    return await _api_request("POST", f"/api/audio/{_require_task_id(task_id)}/reset-summary")


@mcp.tool()
async def note_translate(task_id: str, target_language: str) -> Dict[str, Any]:
    """Translate a note's summary. Supported: en, uk, ru, cs, es, de, fr."""
    target = _validate_language(target_language)
    if not target:
        raise RuntimeError("target_language is required")
    return await _api_request(
        "POST",
        f"/api/audio/{_require_task_id(task_id)}/translate",
        json={"target_language": target},
    )


@mcp.tool()
async def podcast_platforms() -> Dict[str, Any]:
    """List podcast platforms supported for URL processing."""
    return await _api_request("GET", "/api/podcasts/platforms")


@mcp.tool()
async def podcast_process(url: str, language: str = "") -> Dict[str, Any]:
    """Submit a podcast episode URL for summarization."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise RuntimeError("url must be an absolute http(s) URL")
    payload: Dict[str, str] = {"url": url}
    language_value = _validate_language(language)
    if language_value:
        payload["language"] = language_value
    return await _api_request("POST", "/api/podcasts/process", json=payload)


if __name__ == "__main__":
    mcp.run()
