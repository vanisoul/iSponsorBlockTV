<!-- markdownlint-disable MD013 -->

# Dify mode

This document describes how to connect `iSponsorBlockTV` to Dify.

There are two valid ways to do it:

1. **Dify direct**: `iSponsorBlockTV` calls the Dify Workflow API directly.
2. **Adapter mode**: a thin adapter exposes `/v1/chat/completions` in front of Dify.

Dify's published application API uses Dify-native endpoints such as `/v1/workflows/run`, `/v1/chat-messages`, and `/v1/completion-messages`. It is not the same request shape as OpenAI chat/completions.

---

## 1) Recommended simple mode: Dify direct

Use this mode when the deployment target is Dify and the workflow API is acceptable as the public contract.

```text
iSponsorBlockTV
  -> Dify Workflow API: POST /v1/workflows/run
    -> Gemini / other internal workflow nodes
    -> result_json
  -> iSponsorBlockTV validates and caches the segments
```

In this mode, Dify is the stable I/O boundary.

`iSponsorBlockTV` sends a YouTube video ID and URL to Dify. Dify can then use Gemini, tools, code nodes, or any other workflow steps to decide the skip ranges.

---

## 2) Dify direct request shape

Typical Dify workflow API shape:

```http
POST https://api.dify.ai/v1/workflows/run
Authorization: Bearer ***
Content-Type: application/json
```

Example request body:

```json
{
  "inputs": {
    "video_id": "abc123",
    "youtube_url": "https://www.youtube.com/watch?v=abc123",
    "min_confidence": 0.85,
    "allowed_categories": ["opening", "ending", "preview", "recap"]
  },
  "response_mode": "blocking",
  "user": "isponsorblocktv"
}
```

If streaming mode is used, the client must read the stream until the workflow is finished and then take the final output.

---

## 3) Dify workflow I/O

Keep the Dify workflow I/O fixed. The workflow can do anything internally, but the caller should depend on a small stable contract.

### Inputs

- `video_id`: YouTube video ID
- `youtube_url`: full YouTube URL
- `min_confidence`: minimum confidence for auto-skip
- `allowed_categories`: categories that may be skipped

### Output

Recommended final output variable:

- `result_json`: a string containing the final segment JSON

Example `result_json` content:

```json
{
  "schema_version": "1.0",
  "video_id": "abc123",
  "source": "dify",
  "status": "ok",
  "duration": 1420.5,
  "segments": [
    {
      "start": 0.0,
      "end": 72.0,
      "category": "opening",
      "action": "skip",
      "confidence": 0.9,
      "reason": "opening section before the main content"
    }
  ],
  "warnings": []
}
```

`iSponsorBlockTV` only needs this final normalized result. It does not care whether the workflow used natural language, JSON, tool output, or multiple intermediate answers inside Dify.

---

## 4) Example workflow: Gemini with a YouTube URL

A simple Dify workflow can look like this:

```text
Start
  -> LLM node: Gemini
      input: youtube_url, allowed_categories, min_confidence
      task: inspect the YouTube video and suggest skip ranges
      output: natural-language analysis or structured draft
  -> LLM / code node: normalize
      input: Gemini analysis
      task: convert candidate ranges into result_json
  -> End
      output: result_json
```

Example Gemini prompt:

```text
You are analyzing a YouTube video for automatic skip ranges.

Video URL:
{{ youtube_url }}

Find only these skippable categories:
{{ allowed_categories }}

Return candidate ranges for opening, ending, preview, recap, or end screen.
Do not skip main content. If uncertain, say that no safe segment is available.
Include start time, end time, category, confidence, and a short reason.
```

The Gemini node is allowed to answer naturally, for example:

```text
The first 72 seconds look like an opening sequence. The section after 22:40 appears to be an ending and next-video preview.
```

Then the normalize node converts that into `result_json`.

The key point: external AI does not have to be the stable API contract. Dify is the stable API contract.

---

## 5) Alternative: adapter mode

Use this mode only if something in front of Dify accepts OpenAI chat/completions requests:

```text
POST /v1/chat/completions
```

The official Dify app API does not publish this as the normal workflow input shape. If the caller must speak OpenAI chat/completions, the adapter translates:

```text
OpenAI chat/completions request
  -> Dify /v1/workflows/run request
  -> Dify result_json
  -> OpenAI chat/completions response
```

Then configure `iSponsorBlockTV` with the adapter's OpenAI-compatible base URL:

```json
{
  "segment_provider": "sponsorblock_then_ai",
  "ai_base_url": "https://skip-ai.example.com",
  "ai_api_key": "replace-with-token-if-needed",
  "ai_model": "dify-skip-workflow",
  "ai_timeout_seconds": 25,
  "ai_cache_dir": "ai_segment_cache",
  "ai_min_confidence": 0.85
}
```

The client appends `/v1/chat/completions` by itself.

This mode is useful only when OpenAI-compatible input is required by the caller. If the app can call Dify directly, Dify direct is simpler than adding an adapter just to translate formats.

---

## 6) OpenAI-compatible response shape

If using the OpenAI-compatible path, the final `result_json` must be wrapped in a chat/completions response:

```json
{
  "id": "chatcmpl-skip-abc123",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"schema_version\":\"1.0\",\"video_id\":\"abc123\",\"source\":\"dify\",\"status\":\"ok\",\"segments\":[],\"warnings\":[]}"
      },
      "finish_reason": "stop"
    }
  ]
}
```

The `content` value is a JSON string. `iSponsorBlockTV` parses and validates that string.

---

## 7) Failure behavior

If Dify, Gemini, transcript lookup, or any internal step fails, return a valid no-op result:

```json
{
  "schema_version": "1.0",
  "video_id": "abc123",
  "source": "dify",
  "status": "fallback",
  "segments": [],
  "warnings": ["dify_failed"]
}
```

Playback should never be blocked by AI errors.

---

## 8) One-line summary

If Dify is the chosen backend, call Dify directly. Only use an OpenAI-compatible adapter when the caller must keep the OpenAI chat/completions request shape.
