"""AI-backed skip segment inference (OpenAI-compatible API).

This module is intentionally conservative: any error returns an empty segment set.
It is designed to be used as a fallback when SponsorBlock has no segments.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiohttp import ClientSession, ClientTimeout

MAX_DESCRIPTION_CHARS = 4000
MAX_TRANSCRIPT_CHARS = 12000


def trim_text(text: str | None, *, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return "." * max_chars
    return text[: max_chars - 3] + "..."


def _try_fetch_metadata(video_id: str) -> dict[str, Any] | None:
    """Best-effort YouTube metadata via yt-dlp (optional dependency)."""

    try:
        from yt_dlp import YoutubeDL  # type: ignore
    except Exception:
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": False,
        "noplaylist": True,
    }
    try:
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception:
        return None


def _try_fetch_transcript(video_id: str) -> list[dict[str, Any]] | None:
    """Best-effort transcript via youtube-transcript-api (optional dependency)."""

    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    except Exception:
        return None

    try:
        transcript = YouTubeTranscriptApi.get_transcript(
            video_id,
            languages=["zh-TW", "zh-Hant", "zh", "ja", "en"],
        )
    except Exception:
        return None
    return list(transcript or [])


def _normalize_chapters(raw_chapters: Any) -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    if not isinstance(raw_chapters, list):
        return chapters
    for chapter in raw_chapters:
        if not isinstance(chapter, dict):
            continue
        start = chapter.get("start_time", chapter.get("start"))
        end = chapter.get("end_time", chapter.get("end"))
        try:
            normalized = {
                "start": float(start),
                "end": None if end in (None, "") else float(end),
                "title": str(chapter.get("title") or ""),
            }
        except (TypeError, ValueError):
            continue
        chapters.append(normalized)
    return chapters


def _normalize_transcript(raw_transcript: Any) -> tuple[list[dict[str, Any]], str]:
    entries: list[dict[str, Any]] = []
    if not isinstance(raw_transcript, list):
        return entries, ""
    lines: list[str] = []
    for entry in raw_transcript:
        if not isinstance(entry, dict):
            continue
        try:
            start = float(entry.get("start", 0))
            duration = float(entry.get("duration", 0))
        except (TypeError, ValueError):
            start = 0.0
            duration = 0.0
        text = str(entry.get("text") or "").replace("\n", " ").strip()
        if not text:
            continue
        entries.append({"start": start, "duration": duration, "text": text})
        lines.append(f"[{start:.1f}] {text}")
    return entries, trim_text("\n".join(lines), max_chars=MAX_TRANSCRIPT_CHARS)


def build_video_context(video_id: str) -> dict[str, Any]:
    """Build best-effort context for AI inference.

    If optional deps are missing, returns minimal context with warnings.
    """

    warnings: list[str] = []
    metadata = _try_fetch_metadata(video_id)
    if not metadata:
        return {"ok": False, "video_id": video_id, "warnings": ["metadata_unavailable"]}

    chapters = _normalize_chapters(metadata.get("chapters"))
    if not chapters:
        warnings.append("chapters_unavailable")

    raw_transcript = _try_fetch_transcript(video_id)
    transcript, transcript_text = _normalize_transcript(raw_transcript)
    if not transcript:
        warnings.append("transcript_unavailable")

    duration_value = metadata.get("duration")
    try:
        duration = None if duration_value in (None, "") else float(duration_value)
    except (TypeError, ValueError):
        duration = None
        warnings.append("duration_unavailable")

    return {
        "ok": True,
        "video_id": video_id,
        "title": metadata.get("title"),
        "channel": metadata.get("channel") or metadata.get("uploader"),
        "duration": duration,
        "description": trim_text(metadata.get("description"), max_chars=MAX_DESCRIPTION_CHARS),
        "chapters": chapters,
        "transcript": transcript,
        "transcript_text": transcript_text,
        "warnings": warnings,
    }


@dataclass
class AiConfig:
    base_url: str
    api_key: str | None
    model: str
    timeout_seconds: int = 25
    min_confidence: float = 0.85


@dataclass
class DifyConfig:
    base_url: str
    api_key: str | None
    timeout_seconds: int = 25
    min_confidence: float = 0.85
    response_mode: str = "blocking"
    user: str = "isponsorblocktv"


ALLOWED_AI_CATEGORIES = ["opening", "ending", "preview", "recap"]


def _fallback_response(video_id: str, source: str, warning: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "video_id": video_id,
        "source": source,
        "status": "fallback",
        "segments": [],
        "warnings": [warning],
    }


def _cache_path(cache_dir: Path, video_id: str) -> Path:
    safe_id = "".join(ch for ch in str(video_id) if ch.isalnum() or ch in "_-")
    if not safe_id:
        raise ValueError("video_id is required")
    return cache_dir / f"{safe_id}.json"


def load_cached_response(cache_dir: Path, video_id: str) -> dict[str, Any] | None:
    path = _cache_path(cache_dir, video_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_cached_response(cache_dir: Path, video_id: str, response: dict[str, Any]) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, video_id)
    path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except Exception:
        pass
    return path


def _validate_segments(
    video_id: str, response: dict[str, Any], *, min_confidence: float
) -> dict[str, Any]:
    """Validate + normalize a response into the minimal schema ApiHelper expects."""

    duration = response.get("duration")
    try:
        duration_f = None if duration in (None, "") else float(duration)
    except (TypeError, ValueError):
        duration_f = None

    raw_segments = response.get("segments") or []
    if not isinstance(raw_segments, list):
        raw_segments = []

    segments: list[dict[str, Any]] = []
    for seg in raw_segments:
        if not isinstance(seg, dict):
            continue
        if seg.get("action", "skip") != "skip":
            continue
        try:
            start = float(seg["start"])
            end = float(seg["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if start < 0 or end <= start:
            continue
        if duration_f is not None and end > duration_f + 1.0:
            continue
        try:
            conf = float(seg.get("confidence", 1.0))
        except (TypeError, ValueError):
            continue
        if conf < min_confidence:
            continue
        segments.append(
            {
                "start": start,
                "end": end,
                "category": seg.get("category"),
                "action": "skip",
                "confidence": conf,
                "reason": seg.get("reason"),
            }
        )

    segments.sort(key=lambda s: s["start"])
    # reject overlapping segments conservatively
    last_end = -1.0
    for seg in segments:
        if seg["start"] < last_end:
            return {
                "schema_version": "1.0",
                "video_id": video_id,
                "source": response.get("source", "ai"),
                "status": "fallback",
                "segments": [],
                "warnings": ["segment_overlap_rejected"],
            }
        last_end = float(seg["end"])

    return {
        "schema_version": "1.0",
        "video_id": video_id,
        "source": response.get("source", "ai"),
        "status": response.get("status", "ok"),
        "duration": duration_f,
        "segments": segments,
        "warnings": response.get("warnings") or [],
    }


def _build_prompt(video_id: str, context: dict[str, Any], *, min_confidence: float) -> str:
    categories = ALLOWED_AI_CATEGORIES
    duration = context.get("duration")
    return (
        "You are a conservative YouTube skip-segment detector.\n\n"
        f"video_id: {video_id}\n"
        f"duration_seconds: {duration}\n"
        f"minimum_confidence: {min_confidence}\n"
        f"allowed_categories_json: {json.dumps(categories, ensure_ascii=False)}\n\n"
        "video_context_json:\n"
        f"{json.dumps(context, ensure_ascii=False)}\n\n"
        "Return ONLY strict JSON (no markdown). Schema:\n"
        "{\n"
        '  "schema_version": "1.0",\n'
        '  "video_id": "...",\n'
        '  "source": "openai_compat",\n'
        '  "status": "ok",\n'
        '  "duration": 0.0,\n'
        '  "segments": [\n'
        '    {"start": 0.0, "end": 42.0, "category": "opening", "action": "skip", "confidence": 0.91, "reason": "short reason"}\n'
        "  ],\n"
        '  "warnings": []\n'
        "}\n\n"
        "Rules:\n"
        "- Be conservative; if unsure, return empty segments.\n"
        "- Only skip opening/ending/preview/recap/end-screen ranges; do not skip main content.\n"
        "- No negative times; end must be > start; no overlaps; do not exceed duration.\n"
        f"- Only include segments with confidence >= {min_confidence}.\n"
    )


async def infer_segments_openai_compatible(
    session: ClientSession,
    video_id: str,
    *,
    cfg: AiConfig,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Call an OpenAI-compatible Chat Completions endpoint and return validated JSON."""

    logger = logging.getLogger(__name__)
    url = cfg.base_url.rstrip("/") + "/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    payload = {
        "model": cfg.model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "You output strict JSON only."},
            {
                "role": "user",
                "content": _build_prompt(video_id, context, min_confidence=cfg.min_confidence),
            },
        ],
    }

    timeout = ClientTimeout(total=cfg.timeout_seconds)
    try:
        async with session.post(url, json=payload, headers=headers, timeout=timeout) as resp:
            text = await resp.text()
            if resp.status >= 400:
                logger.warning("AI endpoint HTTP %s for %s: %s", resp.status, video_id, text[:400])
                return {
                    "schema_version": "1.0",
                    "video_id": video_id,
                    "source": "openai_compat",
                    "status": "fallback",
                    "segments": [],
                    "warnings": [f"ai_http_{resp.status}"],
                }
            raw = json.loads(text)
    except Exception as exc:
        logger.warning("AI endpoint request failed for %s: %s", video_id, exc)
        return {
            "schema_version": "1.0",
            "video_id": video_id,
            "source": "openai_compat",
            "status": "fallback",
            "segments": [],
            "warnings": [f"ai_request_failed:{type(exc).__name__}"],
        }

    content: str | None = None
    try:
        content = raw["choices"][0]["message"]["content"]
    except Exception:
        content = None

    if not content or not str(content).strip():
        return _fallback_response(video_id, "openai_compat", "ai_empty_content")
    try:
        parsed = json.loads(content)
    except Exception:
        return _fallback_response(video_id, "openai_compat", "ai_non_json_content")

    if not isinstance(parsed, dict):
        return _fallback_response(video_id, "openai_compat", "ai_json_not_object")

    # Ensure video_id is set
    parsed.setdefault("video_id", video_id)
    parsed.setdefault("source", "openai_compat")
    return _validate_segments(video_id, parsed, min_confidence=cfg.min_confidence)


def _extract_dify_result_json(raw: dict[str, Any]) -> Any:
    """Extract the normalized result from common Dify workflow response shapes."""

    outputs = raw.get("outputs")
    if not isinstance(outputs, dict):
        data = raw.get("data")
        if isinstance(data, dict):
            outputs = data.get("outputs")
    if not isinstance(outputs, dict):
        return None

    for key in ("result_json", "result", "answer", "text"):
        if key in outputs:
            return outputs[key]
    return None


async def infer_segments_dify_workflow(
    session: ClientSession,
    video_id: str,
    *,
    cfg: DifyConfig,
) -> dict[str, Any]:
    """Call Dify Workflow API directly and return validated segment JSON."""

    logger = logging.getLogger(__name__)
    url = cfg.base_url.rstrip("/") + "/v1/workflows/run"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    payload = {
        "inputs": {
            "video_id": video_id,
            "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
            "min_confidence": cfg.min_confidence,
            "allowed_categories": ALLOWED_AI_CATEGORIES,
        },
        "response_mode": cfg.response_mode,
        "user": cfg.user,
    }

    timeout = ClientTimeout(total=cfg.timeout_seconds)
    try:
        async with session.post(url, json=payload, headers=headers, timeout=timeout) as resp:
            text = await resp.text()
            if resp.status >= 400:
                logger.warning(
                    "Dify endpoint HTTP %s for %s: %s", resp.status, video_id, text[:400]
                )
                return _fallback_response(video_id, "dify", f"dify_http_{resp.status}")
            raw = json.loads(text)
    except Exception as exc:
        logger.warning("Dify endpoint request failed for %s: %s", video_id, exc)
        return _fallback_response(video_id, "dify", f"dify_request_failed:{type(exc).__name__}")

    if not isinstance(raw, dict):
        return _fallback_response(video_id, "dify", "dify_json_not_object")

    result_json = _extract_dify_result_json(raw)
    if result_json in (None, ""):
        return _fallback_response(video_id, "dify", "dify_empty_result_json")

    if isinstance(result_json, dict):
        parsed = result_json
    else:
        try:
            parsed = json.loads(str(result_json))
        except Exception:
            return _fallback_response(video_id, "dify", "dify_non_json_result")

    if not isinstance(parsed, dict):
        return _fallback_response(video_id, "dify", "dify_result_not_object")

    parsed.setdefault("video_id", video_id)
    parsed.setdefault("source", "dify")
    return _validate_segments(video_id, parsed, min_confidence=cfg.min_confidence)
