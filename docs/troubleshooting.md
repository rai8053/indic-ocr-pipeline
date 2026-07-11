# Troubleshooting

## JSON Parse Errors / Truncated Responses

Reduce `--batch-size` for that provider, or check `max_tokens` in `core/config.py`.

## "annotation_quality": "degraded_text_only_fallback"

The page was processed by a text-only fallback (OpenRouter/Groq). It won't have LaTeX or reliable relations. Reprocess when a vision-capable provider has quota.

## Windows Unicode Error

Update to the latest version which includes ASCII-safe logging for terminal output.

## Provider Timeouts

- Gemini: Check quota (daily reset, America/Los_Angeles)
- GLM: Image payloads may time out — try text-only mode
- OpenRouter: Free model is rate-limited — wait or use a paid model
