# Dify：用「OpenAI 相容 API」做 iSponsorBlockTV AI 跳過判決（模板）

這份文件是給東政留存用：目標是讓 Dify 背後可以接任何 LLM（Gemini / OpenAI / 其他），
但對 iSponsorBlockTV 來說只需要一個 *OpenAI-compatible* 的 base URL。

> iSponsorBlockTV 會呼叫：`{ai_base_url}/v1/chat/completions`

---

## 1) iSponsorBlockTV 端期待的輸出（嚴格 JSON）

模型/工作流最後要輸出「只包含 JSON」的字串（不要 markdown），格式建議：

```json
{
  "schema_version": "1.0",
  "video_id": "abc123",
  "source": "dify_openai_compat",
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

保守規則（務必做到）：
- 不確定就回 `segments: []`
- 不要負數時間
- `end > start`
- 不要 overlap
- 不能超過 duration（若 duration 不明就更保守）

---

## 2) 在 Dify 建工作流：建議輸入/輸出欄位

### Inputs（建議）
讓你未來可以從不同上游（或你手動測試）丟資料：

- `video_id` (string)
- `context_json` (string)  ← 這裡放「影片資訊（title/chapters/transcript...）」的 JSON 字串
- `duration` (number, optional)
- `min_confidence` (number, default 0.85)
- `categories_json` (string, optional) 例如 `["opening","ending","preview","recap"]`

> 你要從哪裡抓 context 都可以：
> - 由 iSponsorBlockTV 端抓（未來若裝 yt-dlp / transcript）
> - 或由你在 Dify 外面做一層 gateway/collector 先整理好再送進工作流

### Outputs（建議）
請讓 workflow 最終輸出以下其中一種（擇一即可）：
- `result_json`：*字串*，內容就是上面那個嚴格 JSON（最推薦）
- 或 `result`：*物件*（Dify 若能直接輸出 object）

---

## 3) 兩種部署形態（你提到的「要能串接其他 API」）

### 方案 A（最簡單、最常用）：Dify 工作流 + 小轉接服務
- iSponsorBlockTV → 打你的小 proxy（OpenAI 相容）
- proxy → 呼叫 Dify workflow run
- proxy → 把輸出包成 OpenAI chat/completions 回應

優點：
- Dify 不用硬改成 OpenAI 介面
- 你可以在 proxy 內做快取、熔斷、重試、fallback

### 方案 B：你有 API Gateway 能直接回 OpenAI 相容
- iSponsorBlockTV → 直接打 gateway 的 `/v1/chat/completions`
- gateway 內部再去跑 Dify workflow / 其他 API

優點：
- iSponsorBlockTV 端最乾淨

---

## 4) 你要「第二次要擋」的建議（兩段式保守防呆）

如果你擔心 LLM 太激進，可以做兩段式：

1) **第一次：產生候選 segments**（寧可多、但要在合理範圍內）
2) **第二次：審核/縮減 segments**（更保守，確保不會跳到主內容）

第二段審核可以用更嚴的規則：
- 只允許落在 0~120 秒（opening/recap）或最後 120 秒（ending）等硬範圍
- 或要求章節標題包含 opening/ending/recap 類關鍵字才可過

最後只輸出審核通過的 segments。

---

## 5) 與 iSponsorBlockTV 的設定對應（提醒）

iSponsorBlockTV 的 config.json 你會設：
- `segment_provider`: `"sponsorblock_then_ai"`
- `ai_base_url`: `"https://<你的 openai-compat 入口>"`
- `ai_api_key`: `"<token 或空字串>"`
- `ai_model`: `"<你在 gateway/dify 端對應的 model 名稱>"`

> 注意：iSponsorBlockTV 不會直接懂 Dify workflow 的 `/v1/workflows/run`，
> 所以你要嘛做「方案 A 的 proxy」，要嘛做「方案 B 的 gateway」。
