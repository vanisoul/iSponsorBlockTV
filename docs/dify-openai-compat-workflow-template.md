<!-- markdownlint-disable MD013 -->

# Dify / Gateway mode

This document describes the Dify-based mode.

The important boundary is simple:

```text
iSponsorBlockTV
  -> OpenAI-compatible gateway: POST /v1/chat/completions
    -> Dify workflow API
      -> any model or tool chain, for example Gemini with a YouTube URL
    -> normalized segment JSON
  -> iSponsorBlockTV validates and caches the segments
```

`iSponsorBlockTV` does not need to know how the workflow works internally. It only talks to an OpenAI-compatible endpoint.

---

## 1) Public endpoint seen by iSponsorBlockTV

Expose a gateway URL such as:

```text
https://skip-ai.example.com/v1/chat/completions
```

Then configure `iSponsorBlockTV` with the base URL only:

```json
{
  "segment_provider": "sponsorblock_then_ai",
  "ai_base_url": "https://skip-ai.example.com",
  "ai_api_key": "replace-with-gateway-token-if-needed",
  "ai_model": "dify-skip-workflow",
  "ai_timeout_seconds": 25,
  "ai_cache_dir": "ai_segment_cache",
  "ai_min_confidence": 0.85
}
```

The client appends `/v1/chat/completions` by itself.

So do **not** set `ai_base_url` to the full Dify workflow URL. Set it to the gateway base URL.

---

## 2) Gateway to Dify workflow API

The gateway receives an OpenAI chat/completions request from `iSponsorBlockTV`, extracts the video context, and calls Dify.

Typical Dify workflow API shape:

```http
POST https://api.dify.ai/v1/workflows/run
Authorization: Bearer <DIFY_API_KEY>
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

If the gateway uses Dify streaming mode instead, it should read the stream until the workflow is finished, then take the final output field and convert it into the same OpenAI-compatible response.

---

## 3) Dify workflow I/O

Keep the Dify workflow I/O fixed. The workflow can do anything internally, but the gateway should depend on a small stable contract.

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
  "source": "dify_gateway",
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

`iSponsorBlockTV` only needs this final normalized result. It does not care whether the model produced natural language, JSON, tool output, or multiple intermediate answers inside Dify.

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

The key point: **external AI does not have to be the stable API contract. Dify/Gateway is the stable API contract.**

---

## 5) Gateway response back to iSponsorBlockTV

The gateway must wrap the final `result_json` in an OpenAI-compatible chat/completions response:

```json
{
  "id": "chatcmpl-skip-abc123",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"schema_version\":\"1.0\",\"video_id\":\"abc123\",\"source\":\"dify_gateway\",\"status\":\"ok\",\"segments\":[] ,\"warnings\":[]}"
      },
      "finish_reason": "stop"
    }
  ]
}
```

The `content` value is a JSON string. `iSponsorBlockTV` parses and validates that string.

---

## 6) Failure behavior

If Dify, Gemini, transcript lookup, or any internal step fails, return a valid no-op result:

```json
{
  "schema_version": "1.0",
  "video_id": "abc123",
  "source": "dify_gateway",
  "status": "fallback",
  "segments": [],
  "warnings": ["dify_failed"]
}
```

Playback should never be blocked by AI errors.

---

## 7) What to configure in iSponsorBlockTV

For a mounted config file under the app data directory, add these keys:

```json
{
  "segment_provider": "sponsorblock_then_ai",
  "ai_base_url": "https://skip-ai.example.com",
  "ai_api_key": "replace-with-gateway-token-if-needed",
  "ai_model": "dify-skip-workflow",
  "ai_timeout_seconds": 25,
  "ai_cache_dir": "ai_segment_cache",
  "ai_min_confidence": 0.85
}
```

Docker example:

```yaml
services:
  iSponsorBlockTV:
    image: ghcr.io/dmunozv04/isponsorblocktv
    volumes:
      - /path/to/data:/app/data
```

The config file should live inside the mounted data directory used by the container.

---

## 8) One-line summary

`iSponsorBlockTV` calls one OpenAI-compatible URL. The gateway calls Dify. Dify can call Gemini with the YouTube URL. Only the final gateway response must be normalized into segment JSON.
