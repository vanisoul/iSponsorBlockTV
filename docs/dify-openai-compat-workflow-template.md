# Dify：作為 OpenAI-compatible provider 的最小模板

這份文件只講一件事：

**Dify 可以放在背後自由編排流程，但對 iSponsorBlockTV 來說，它看見的永遠只是 OpenAI-compatible `/v1/chat/completions`。**

所以你要支援的其實只有兩種模式：

1. **直接 provider 模式**：iSponsorBlockTV 直接打真正的 OpenAI-compatible AI provider
2. **Dify 模式**：iSponsorBlockTV 打你包在外面的 OpenAI-compatible gateway，
   而 gateway 背後再去跑 Dify

---

## 1) 對 iSponsorBlockTV 來說，兩種模式完全一樣

iSponsorBlockTV 都是打：

`{ai_base_url}/v1/chat/completions`

都會送 OpenAI chat/completions 格式的 request。

所以 iSponsorBlockTV：

- 不需要知道背後是不是 Dify
- 不需要知道 workflow API 長怎樣
- 不需要知道你背後換了哪個模型

它只要求：

1. request 是 OpenAI 格式
2. response 也是 OpenAI 格式
3. `choices[0].message.content` 裡面放固定 JSON schema

---

## 2) 模式 A：直接 provider 模式

### 模式 A 適合情境

- 你有現成的 OpenAI-compatible provider
- 想最單純先跑通

### 模式 A 入口

- `POST /v1/chat/completions`

### 模式 A 行為

- iSponsorBlockTV 直接送 prompt
- provider 直接回答
- 回答中的 `choices[0].message.content` 內放 strict JSON

這種模式的好處是：

- 架構最單純
- 最容易先測通
- 不需要另外轉接 Dify workflow

---

## 3) 模式 B：Dify 模式

### 模式 B 適合情境

- 你想自己控 prompt
- 你想在背後加 workflow
- 你想自由切換不同 LLM / API
- 你想在背後做額外審核、fallback、cache、重試

### 模式 B 入口

對外還是：

- `POST /v1/chat/completions`

### 模式 B 行為

- iSponsorBlockTV 送來 OpenAI request
- 你的 gateway 收到後，自己去呼叫 Dify workflow
- Dify workflow 背後可以再串 Gemini / OpenAI / 其他 API
- gateway 最後再把結果包回 OpenAI response

也就是說：

```text
iSponsorBlockTV
  -> /v1/chat/completions
    -> your gateway
      -> Dify workflow
        -> LLM / other APIs
      -> OpenAI-compatible response
```

重點不是 Dify 本身，而是：
**你對外要維持 OpenAI-compatible 介面。**

---

## 4) 最終輸出要求

不管是模式 A 還是模式 B，最後都要讓 `choices[0].message.content` 包這種 strict JSON：

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
      "reason": "opening recap before main content"
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
- 不要超過 duration

---

## 5) Dify workflow 最小輸入/輸出建議

如果你走 Dify 模式，背後 workflow 可以很自由，但建議至少吃這些欄位：

### Inputs

- `video_id`
- `context_json`
- `duration`（optional）
- `min_confidence`

### Output

最後請輸出：

- `result_json`：字串，內容就是 strict JSON schema

這樣 gateway 只需要把它包回 OpenAI response 就好。

---

## 6) 你真正要記的範疇

不要把事情想複雜，核心就這兩句：

- **直接模式**：真的打 AI provider
- **Dify 模式**：打你自己的 OpenAI-compatible gateway，背後再跑 Dify

前面固定，後面自由。

這樣文件和實作都會乾淨很多。
