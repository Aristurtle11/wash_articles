"""Simple rate limiting utilities."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass


@dataclass(slots=True)
class RateLimiter:
    min_delay: float = 0.0
    max_delay: float = 0.0

    def __post_init__(self) -> None:
        if self.max_delay < self.min_delay:
            self.max_delay = self.min_delay

    def compute_delay(self) -> float:
        if self.max_delay <= 0:
            return max(self.min_delay, 0.0)
        low = max(self.min_delay, 0.0)
        high = max(self.max_delay, low)
        return random.uniform(low, high)

    def sleep(self) -> float:
        delay = self.compute_delay()
        if delay > 0:
            time.sleep(delay)
        return delay
