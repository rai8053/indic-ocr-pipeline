# FAQ

## How much does it cost?

All providers have free tiers. The pipeline pre-checks quota before each API call.

## Which provider is best?

Start with Gemini (~1,500 req/day free). The pipeline falls back automatically.

## Can I add a new language?

Add to `LANGUAGE_HINTS` in `core/config.py`. Google Vision supports major Indic scripts.

## What if all providers fail?

The page falls back to raw Vision OCR (Level 2) with classes set to "Text".

## Can I use my own LLM?

Yes. Any OpenAI-compatible endpoint can be added as a provider.
