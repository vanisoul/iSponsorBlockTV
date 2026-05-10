<!-- markdownlint-disable MD013 -->

# AI segment provider

This project can optionally use an AI decision endpoint to infer skip segments when SponsorBlock returns no segments.

## When to use

Use this when:

- SponsorBlock should stay the primary source.
- AI should be only a conservative fallback for openings, endings, recaps, or previews.
- No separate watcher or sidecar service should be required for the normal path.

## Provider modes

The skip source is controlled by `segment_provider`:

```json
{
  "segment_provider": "sponsorblock_then_ai"
}
```

Recommended value:

- `sponsorblock_then_ai`: query SponsorBlock first; when it returns no segments, query AI.

AI itself is controlled by `ai_provider`:

- `openai_compatible`: call `{ai_base_url}/v1/chat/completions`.
- `dify_workflow`: call `{dify_base_url}/v1/workflows/run` directly.

## OpenAI-compatible provider

Use this when the backend already accepts OpenAI chat/completions requests.

```json
{
  "segment_provider": "sponsorblock_then_ai",
  "ai_provider": "openai_compatible",
  "ai_base_url": "https://your-openai-compatible-base-url",
  "ai_api_key": "",
  "ai_model": "your-model-name",
  "ai_timeout_seconds": 25,
  "ai_cache_dir": "ai_segment_cache",
  "ai_min_confidence": 0.85
}
```

The app calls:

```text
POST {ai_base_url}/v1/chat/completions
```

It expects strict JSON inside `choices[0].message.content`.

## Dify workflow provider

Use this when Dify is the chosen backend and the app should call the Dify Workflow API directly.

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

The app calls:

```text
POST {dify_base_url}/v1/workflows/run
```

It sends these workflow inputs:

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

The Dify workflow may use Gemini or any other internal nodes to inspect the YouTube URL. The final workflow output should include `result_json`.

## Result JSON schema

Both providers must eventually produce the same normalized result JSON:

```json
{
  "schema_version": "1.0",
  "video_id": "abc123",
  "source": "dify",
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

For Dify, this JSON may be returned as `data.outputs.result_json` from the workflow run response.

## Cache behavior

Validated AI results are cached as JSON files under:

```text
<data_dir>/<ai_cache_dir>/<video_id>.json
```

On the next play, the cache is checked first.

## Safety and validation rules

The app drops or rejects unsafe output:

- negative times
- `end <= start`
- overlapping segments
- segments beyond known duration, when duration is known
- confidence below `ai_min_confidence`

If anything fails, such as network, parsing, or validation, the app returns no AI segments and does not block playback.

## Related document

For a Dify workflow template, see:

- `docs/dify-openai-compat-workflow-template.md`
