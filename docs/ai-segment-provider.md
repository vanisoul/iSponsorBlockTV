# AI segment provider (OpenAI-compatible)

This project can optionally use an AI decision endpoint to infer skip segments when SponsorBlock returns no segments.

## When to use

Use this when:
- You still want SponsorBlock as the primary source.
- You want a conservative fallback for openings/endings/recaps/previews.
- You do **not** want to run a separate watcher/sidecar service.

## Configuration (config.json)

Recommended mode:

```json
"segment_provider": "sponsorblock_then_ai"
```

Required keys:

```json
"ai_base_url": "https://your-openai-compatible-base-url",
"ai_api_key": "",
"ai_model": "your-model-name",
"ai_timeout_seconds": 25,
"ai_cache_dir": "ai_segment_cache",
"ai_min_confidence": 0.85
```

### OpenAI-compatible contract

The app calls:

- `{ai_base_url}/v1/chat/completions`

It expects the model to return **strict JSON only** (no markdown) inside `choices[0].message.content`.

The JSON schema is:

```json
{
  "schema_version": "1.0",
  "video_id": "<id>",
  "source": "openai_compat",
  "status": "ok",
  "duration": 1420.5,
  "segments": [
    {
      "start": 30.0,
      "end": 60.0,
      "category": "opening",
      "action": "skip",
      "confidence": 0.91,
      "reason": "short reason"
    }
  ],
  "warnings": []
}
```

## Cache (DB-first behavior)

Validated AI results are cached as JSON files under:

- `<data_dir>/<ai_cache_dir>/<video_id>.json`

On the next play, the cache is checked first.

## Safety / validation rules

The app drops or rejects unsafe output:
- negative times
- `end <= start`
- overlapping segments
- segments beyond known duration (when duration is known)
- confidence below `ai_min_confidence`

If anything fails (network, parse, validation), it returns no segments.

## Dify notes

If you want Dify to sit behind this OpenAI-compatible interface, see:
- `docs/dify-openai-compat-workflow-template.md`
