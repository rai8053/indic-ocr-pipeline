"""Performance benchmarking utilities for pipeline stages."""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any


class Benchmark:
    """Simple wall-clock benchmark for timing pipeline stages.

    Attributes:
        timings: Dict mapping stage names to accumulated seconds.
    """

    def __init__(self) -> None:
        self.timings: dict[str, float] = {}
        self._starts: dict[str, float] = {}

    @contextmanager
    def measure(self, stage: str) -> Generator[None, Any, None]:
        """Context manager that times a named stage.

        Usage::

            bench = Benchmark()
            with bench.measure("ocr"):
                run_vision_ocr(...)

        Args:
            stage: Name for this measurement.
        """
        t0 = time.time()
        try:
            yield
        finally:
            elapsed = time.time() - t0
            self.timings[stage] = self.timings.get(stage, 0) + elapsed

    def start(self, stage: str) -> None:
        """Manually start a timing measurement."""
        self._starts[stage] = time.time()

    def stop(self, stage: str) -> float:
        """Manually stop a timing measurement and return elapsed seconds."""
        t0 = self._starts.pop(stage, None)
        if t0 is None:
            return 0.0
        elapsed = time.time() - t0
        self.timings[stage] = self.timings.get(stage, 0) + elapsed
        return elapsed

    def summary(self) -> dict[str, float]:
        """Return a copy of all accumulated timings."""
        return dict(self.timings)

    def reset(self) -> None:
        """Clear all timings."""
        self.timings.clear()
        self._starts.clear()
