"""Structured logging and timing metrics for the pipeline."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional


class PipelineLogger:
    """Writes timestamped log entries and JSONL metrics to a log directory.

    Args:
        log_dir: Directory where ``pipeline.log`` and ``metrics.jsonl`` are stored.
    """

    def __init__(self, log_dir: Path) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file: Path = log_dir / "pipeline.log"
        self.metrics_file: Path = log_dir / "metrics.jsonl"
        self._stage_times: dict[str, float] = {}

        logging.basicConfig(
            filename=self.log_file,
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
        self._logger = logging.getLogger("pipeline")
        self._logger.info("Pipeline started")

    def log(self, message: str) -> None:
        """Log an info message to both file and stdout."""
        self._logger.info(message)
        print(message, flush=True)

    def error(self, message: str) -> None:
        """Log an error message to both file and stderr."""
        self._logger.error(message)
        print(f"[ERROR] {message}", flush=True)

    def start_stage(self, stage: str) -> None:
        """Record the start time of a named pipeline stage."""
        self._stage_times[stage] = time.time()

    def end_stage(self, stage: str) -> Optional[float]:
        """Record the end time of a named stage and write a metric.

        Args:
            stage: Stage name that was previously started.

        Returns:
            Elapsed seconds, or None if the stage was not started.
        """
        start = self._stage_times.pop(stage, None)
        if start is not None:
            elapsed = time.time() - start
            self._logger.info(f"Stage '{stage}' took {elapsed:.2f}s")
            self._write_metric({"stage": stage, "seconds": round(elapsed, 2)})
            return elapsed
        return None

    def _write_metric(self, metric: dict) -> None:
        """Append a JSON metric line to the metrics file."""
        with open(self.metrics_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(metric) + "\n")

    def log_retry(self, attempt: int, max_attempts: int, endpoint: str) -> None:
        """Log a retry event."""
        self._logger.warning(f"Retry {attempt}/{max_attempts} for {endpoint}")
        self._write_metric({"event": "retry", "attempt": attempt, "endpoint": endpoint})

    def log_error(self, stage: str, error: str) -> None:
        """Log an error that occurred in a specific stage."""
        self._logger.error(f"Error in {stage}: {error}")
        self._write_metric({"event": "error", "stage": stage, "error": error})

    def summary(self) -> dict[str, float]:
        """Read the metrics file and return stage timing summaries.

        Returns:
            Dict mapping stage names to elapsed seconds.
        """
        summary: dict[str, float] = {}
        if self.metrics_file.exists():
            stages: list[dict] = []
            with open(self.metrics_file) as f:
                for line in f:
                    try:
                        m = json.loads(line)
                        if "stage" in m:
                            stages.append(m)
                    except json.JSONDecodeError:
                        pass
            for s in stages:
                name: str = s["stage"]
                summary[name] = s["seconds"]
        return summary
