# Docker

## Building

```bash
docker build -t indic-ocr-pipeline .
```

## Running

```bash
docker run --rm -v ./.env:/app/.env -v ./input.pdf:/app/input.pdf -v ./output:/app/output indic-ocr-pipeline --pdf input.pdf --lang odia --out output --level 4
```

## Docker Compose

```bash
docker-compose up
```

This starts the pipeline service and optionally the FastAPI server.
