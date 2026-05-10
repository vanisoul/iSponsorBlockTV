# AI segment provider (OpenAI-compatible)

這個功能請直接理解成 **只有兩種模式**，不要再分太多層：

1. **直接打 OpenAI-compatible provider**
2. **打你自己的 Dify / Gateway，但外表一樣是 OpenAI-compatible provider**

對 `iSponsorBlockTV` 來說，兩種模式都一樣：

- 都是呼叫 `{ai_base_url}/v1/chat/completions`
- 都帶 OpenAI chat/completions 格式的 request
- 都期待固定 JSON schema 的回應

也就是說：
**iSponsorBlockTV 不需要知道後面是真 OpenAI、Gemini 相容服務、還是 Dify workflow。**

---

## 1) 什麼時候會用到 AI

建議模式：

```json
"segment_provider": "sponsorblock_then_ai"
```

流程很單純：

1. 先查 SponsorBlock
2. SponsorBlock 沒資料時，才打 AI provider
3. 驗證回應格式
4. 存進本地 cache
5. 下次同影片先查 cache

如果 AI 失敗、超時、格式錯，就直接當成沒 segments，不阻塞播放。

---

## 2) iSponsorBlockTV 的設定

```json
"segment_provider": "sponsorblock_then_ai",
"ai_base_url": "https://your-openai-compatible-base-url",
"ai_api_key": "",
"ai_model": "your-model-name",
"ai_timeout_seconds": 25,
"ai_cache_dir": "ai_segment_cache",
"ai_min_confidence": 0.85
```

---

## 3) 模式 A：直接打 AI provider

適合情境：

- 你本來就有 OpenAI-compatible API
- 例如 OpenAI、OpenRouter、vLLM、或其他相容服務

### iSponsorBlockTV 送出的 request 形狀

- URL: `{ai_base_url}/v1/chat/completions`
- Header:
  - `Content-Type: application/json`
  - `Authorization: Bearer <ai_api_key>`（如果有）

Request body 會是標準 OpenAI chat/completions 形式，大意像這樣：

```json
{
  "model": "your-model-name",
  "temperature": 0.2,
  "messages": [
    {"role": "system", "content": "You output strict JSON only."},
    {"role": "user", "content": "...prompt with video context..."}
  ]
}
```

### 模式 A 的重點

- 後端直接吃 OpenAI 格式
- prompt 由 iSponsorBlockTV 固定帶入
- 回傳內容只要照固定 schema 回來就好

---

## 4) 模式 B：打 Dify / 自訂 Gateway，但外部仍是 OpenAI-compatible

適合情境：

- 你想在背後改 workflow
- 你想串不同模型或 API
- 你想把 prompt、審核、fallback 都留在 Dify / gateway 端控制

### 這種模式的要求

對外仍然提供：

- `{ai_base_url}/v1/chat/completions`

也就是：

- `iSponsorBlockTV` 還是照 OpenAI request format 發送
- 你的 Dify / gateway 在背後自己轉接到 workflow、LLM、其他 API
- 但最後回給 `iSponsorBlockTV` 的仍然要是 OpenAI chat/completions response

### 模式 B 的重點

- 外部介面固定
- 內部流程自由
- iSponsorBlockTV 不需要知道 Dify 的 workflow API 細節

---

## 5) 兩種模式共同的回應要求

`choices[0].message.content` 裡必須是 **strict JSON only**，不要 markdown。

內容 schema：

```json
{
  "schema_version": "1.0",
  "video_id": "abc123",
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

保守規則：

- 不確定就回 `segments: []`
- 不要負數時間
- `end > start`
- 不要 overlap
- 不要超過影片 duration
- `confidence` 低於 `ai_min_confidence` 的會被丟掉

---

## 6) cache 行為

驗證通過的 AI 結果會存到：

- `<data_dir>/<ai_cache_dir>/<video_id>.json`

所以整體行為是：

- 第一次：SponsorBlock miss → AI → cache
- 第二次：直接 cache first

---

## 7) 最重要的一句

這份功能文件只要記住：

- **模式 A：直接打真正的 OpenAI-compatible provider**
- **模式 B：打 Dify / 自訂流程，但外面包成同一個 OpenAI-compatible provider**

對 `iSponsorBlockTV` 來說，這兩種沒有 API 形狀差別，只有背後實作差別。

---

## 8) 相關文件

如果你要用 Dify / gateway 模式，請看：

- `docs/dify-openai-compat-workflow-template.md`
