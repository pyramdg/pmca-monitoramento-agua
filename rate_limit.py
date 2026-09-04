from collections import defaultdict, deque
from threading import Lock
from time import monotonic


class FailureRateLimiter:
    """Limite simples por processo para reduzir tentativas repetidas de senha."""

    def __init__(self, max_failures: int, window_seconds: int):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _remove_expired(self, key: str, now: float) -> deque[float]:
        failures = self._failures[key]
        cutoff = now - self.window_seconds
        while failures and failures[0] <= cutoff:
            failures.popleft()
        return failures

    def retry_after(self, key: str) -> int:
        now = monotonic()
        with self._lock:
            failures = self._remove_expired(key, now)
            if len(failures) < self.max_failures:
                return 0
            return max(1, int(self.window_seconds - (now - failures[0])))

    def record_failure(self, key: str) -> None:
        now = monotonic()
        with self._lock:
            self._remove_expired(key, now).append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
