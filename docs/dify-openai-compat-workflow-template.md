<!-- markdownlint-disable MD013 -->

# Dify workflow provider

This document describes how to connect `iSponsorBlockTV` directly to the Dify Workflow API.

The simple path is:

```text
iSponsorBlockTV
  -> Dify Workflow API: POST /v1/workflows/run
    -> Gemini or other workflow nodes
    -> result_json
  -> iSponsorBlockTV validates and caches the segments
```

Dify is the stable I/O boundary. The external model does not need to be the API contract.

## 1) iSponsorBlockTV configuration

```json
{
  "segment_provider": "sponsorblock_then_ai",
  "ai_provider": "dify_workflow",
  "dify_base_url": "https://api.dify.ai",
  "dify_api_key": "replace-with-dify-workflow-api-key",
  "dify_response_mode": "blocking",
  "dify_user": "isponsorblocktv",
  "ai_timeout_seconds": 25,
  "ai_cache_dir": "ai_segment_cache",
  "ai_min_confidence": 0.85
}
```

`dify_base_url` is the Dify API base URL only. The app appends `/v1/workflows/run`.

## 2) Request sent to Dify

```http
POST https://api.dify.ai/v1/workflows/run
Authorization: Bearer <DIFY_API_KEY>
Content-Type: application/json
Accept: application/json
```

Example body:

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

## 3) Dify workflow I/O

Keep the Dify workflow I/O fixed. The workflow can do anything internally, but the caller depends on a small stable contract.

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

## 4) Example workflow: Gemini with a YouTube URL

A simple Dify workflow can look like this:

```text
Start
  -> LLM node: Gemini
      input: youtube_url, allowed_categories, min_confidence
      task: inspect the YouTube video and suggest skip ranges
      output: natural-language analysis or structured draft
  -> LLM or code node: normalize
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

The Gemini node may answer naturally, for example:

```text
The first 72 seconds look like an opening sequence.
The section after 22:40 appears to be an ending and next-video preview.
```

Then the normalize node converts that into `result_json`.

## 5) Failure behavior

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

## 6) OpenAI-compatible adapter mode

Use an OpenAI-compatible adapter only when the caller must keep the OpenAI chat/completions request shape.

The official Dify app API uses Dify-native endpoints such as:

- `/v1/workflows/run`
- `/v1/chat-messages`
- `/v1/completion-messages`

It is not the same request shape as OpenAI `/v1/chat/completions`.

If an adapter is used, it translates:

```text
OpenAI chat/completions request
  -> Dify /v1/workflows/run request
  -> Dify result_json
  -> OpenAI chat/completions response
```

For this project, direct Dify workflow mode is simpler when Dify is the chosen backend.
