import logging
import time
import json
from pathlib import Path


class PipelineLogger:
    def __init__(self, log_dir: Path):
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = log_dir / "pipeline.log"
        self.metrics_file = log_dir / "metrics.jsonl"
        self.stage_times = {}

        logging.basicConfig(
            filename=self.log_file,
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
        self._logger = logging.getLogger("pipeline")
        self._logger.info("Pipeline started")

    def log(self, message: str):
        self._logger.info(message)
        print(message, flush=True)

    def error(self, message: str):
        self._logger.error(message)
        print(f"[ERROR] {message}", flush=True)

    def start_stage(self, stage: str):
        self.stage_times[stage] = time.time()

    def end_stage(self, stage: str):
        start = self.stage_times.pop(stage, None)
        if start:
            elapsed = time.time() - start
            self._logger.info(f"Stage '{stage}' took {elapsed:.2f}s")
            self._write_metric({"stage": stage, "seconds": round(elapsed, 2)})
            return elapsed
        return 0

    def _write_metric(self, metric: dict):
        with open(self.metrics_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(metric) + "\n")

    def log_retry(self, attempt: int, max_attempts: int, endpoint: str):
        self._logger.warning(f"Retry {attempt}/{max_attempts} for {endpoint}")
        self._write_metric({"event": "retry", "attempt": attempt, "endpoint": endpoint})

    def log_error(self, stage: str, error: str):
        self._logger.error(f"Error in {stage}: {error}")
        self._write_metric({"event": "error", "stage": stage, "error": error})

    def summary(self):
        summary = {}
        if self.metrics_file.exists():
            stages = []
            with open(self.metrics_file) as f:
                for line in f:
                    try:
                        m = json.loads(line)
                        if "stage" in m:
                            stages.append(m)
                    except json.JSONDecodeError:
                        pass
            if stages:
                for s in stages:
                    name = s["stage"]
                    summary[name] = s["seconds"]
        return summary
