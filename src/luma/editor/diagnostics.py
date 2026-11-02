import statistics
import time

MIN_MOVES_TO_REPORT = 5
MIN_SAMPLES_FOR_PERCENTILE = 20


def describe(samples):
    """mean / 95th percentile / max of timings given in seconds, as milliseconds."""
    if not samples:
        return "n/a"
    milliseconds = [value * 1000 for value in samples]
    if len(milliseconds) >= MIN_SAMPLES_FOR_PERCENTILE:
        p95 = statistics.quantiles(milliseconds, n=20)[-1]
    else:
        p95 = max(milliseconds)
    return f"{statistics.fmean(milliseconds):.1f} / {p95:.1f} / {max(milliseconds):.1f} ms"


class InteractionStats:
    """Timings of one capture session, so lag can be diagnosed from the log instead of guessed."""

    def __init__(self):
        self.moves = 0
        self.intervals = []
        self.handlers = []
        self.paints = []
        self.latencies = []
        self.last_move = None
        self.waiting_since = None

    def mouse_moved(self):
        now = time.perf_counter()
        if self.last_move is not None:
            self.intervals.append(now - self.last_move)
        self.last_move = now
        self.moves += 1
        if self.waiting_since is None:
            self.waiting_since = now
        return now

    def handler_done(self, started):
        self.handlers.append(time.perf_counter() - started)

    def paint_started(self):
        return time.perf_counter()

    def painted(self, started):
        finished = time.perf_counter()
        self.paints.append(finished - started)
        if self.waiting_since is not None:
            self.latencies.append(finished - self.waiting_since)
            self.waiting_since = None

    def has_data(self):
        return self.moves >= MIN_MOVES_TO_REPORT

    def summary(self):
        return (
            f"{self.moves} mouse moves | between moves {describe(self.intervals)} | "
            f"handler {describe(self.handlers)} | paint x{len(self.paints)} {describe(self.paints)} | "
            f"move-to-screen {describe(self.latencies)}  (mean / p95 / max)"
        )
