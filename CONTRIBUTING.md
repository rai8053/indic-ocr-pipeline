# Contributing

Thank you for your interest in improving the Indic OCR Pipeline!

## Getting Started

1. Fork the repository
2. Create a virtual environment: `python -m venv .venv && .venv\Scripts\activate`
3. Install development dependencies: `pip install -r requirements-dev.txt`
4. Install pre-commit hooks: `pre-commit install`

## Development Workflow

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make your changes
3. Run tests: `pytest`
4. Run linters: `black . && ruff check . && mypy .`
5. Commit using conventional commits: `git commit -m "feat: add support for X"`
6. Push and open a pull request

## Code Standards

- Python 3.10+ with full type hints
- Google-style docstrings for all public functions
- Follow existing patterns for provider implementations
- Never hardcode API keys — use `.env` or environment variables
- Never commit real document content, output JSONs, or API keys

## Pull Request Checklist

- [ ] Type hints added
- [ ] Docstrings updated
- [ ] Tests pass
- [ ] Linters pass (black, ruff, mypy)
- [ ] No API keys or secrets in code
- [ ] CHANGELOG.md updated

## Adding a New Provider

1. Create the provider module in `indic_ocr_pipeline/providers/` following the existing pattern
2. Add API key constant in `indic_ocr_pipeline/utils/config.py`
3. Register in `run_proofread_batch` provider dict and failover chain in `indic_ocr_pipeline/providers/manager.py`
4. Add to `PROVIDER_INFO` in `indic_ocr_pipeline/utils/usage.py`
5. Add to CLI choices in argparse in `indic_ocr_pipeline/pipeline/runner.py`
6. Add to `.env.example`
7. Test with a sample page

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
