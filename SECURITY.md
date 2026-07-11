# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| main    | ✅ Active |

## Reporting a Vulnerability

If you discover a security vulnerability, please send an email to the project maintainer.
Do **not** open a public GitHub issue.

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact

You can expect a response within 48 hours.

## Security Best Practices

- **API keys**: Always use `.env` files or environment variables. Never hardcode keys.
- **Document content**: The pipeline processes potentially sensitive documents.
  Be mindful of where output files are stored and who has access.
- **Dependencies**: Keep dependencies updated. Dependabot is enabled for this repository.
- **Input validation**: PDF files are processed with PyMuPDF which handles malformed
  files safely. All user-provided paths are validated before use.
