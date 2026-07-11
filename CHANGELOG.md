# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-07-11

### Added
- IAMHC relay provider as optional fallback
- Picture region detection (embedded PDF images + OpenCV contours)
- LLM-assigned Picture reclassification (tiny text blocks reverted to Text)
- Classes reordering fix for reading order permutation
- Repository metadata: LICENSE, CODE_OF_CONDUCT, CONTRIBUTING, SECURITY
- pyproject.toml with project metadata
- requirements-dev.txt for development dependencies
- .editorconfig, .gitattributes for consistent formatting
- Pre-commit hooks configuration

### Changed
- README with badges, architecture diagram, annotation levels table
- Comprehensive Annotation Levels section (1-4)
- Improved failover chain: gemini → glm → iamhc → openrouter → groq
- Tightened picture detection filters (50% area threshold)
- ASCII-safe logging for Odia text in terminal warnings

### Fixed
- Marker override in `_parse_batch_response` now works correctly with non-sequential reading order
- Windows UnicodeEncodeError crash when logging Odia characters
- Scan artifacts incorrectly classified as Picture blocks

## [0.1.0] - 2026-07-10

### Added
- Initial release
- Google Cloud Vision OCR integration
- Multi-provider LLM annotation (Gemini, GLM, OpenRouter, Groq)
- RFQ Level 4 annotation: classes, reading order, block relations, LaTeX
- Schema validation and quality scoring
- Visual QA overlays
- HTML report generation
- Usage tracking with free-tier quota enforcement
- Interactive CLI (run.py) with language detection
- Picture region detection via embedded PDF images
