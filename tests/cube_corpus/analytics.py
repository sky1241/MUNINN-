#!/usr/bin/env python3
"""
Analytics engine — time series processing, anomaly detection,
statistical aggregation, and streaming computation.
"""
import bisect
import collections
import hashlib
import heapq
import itertools
import math
import os
import statistics
import struct
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterator, Optional


# ─── Constants ──────────────────────────────────────────────────────

EPSILON = 1e-10
MAX_WINDOW_SIZE = 100_000
DEFAULT_PERCENTILES = [50, 75, 90, 95, 99]
ANOMALY_Z_THRESHOLD = 3.0
EMA_ALPHA_DEFAULT = 0.1
RESERVOIR_SIZE = 1000
HISTOGRAM_BINS = 50
BLOOM_FILTER_SIZE = 2**20
BLOOM_HASH_COUNT = 7


# ─── Enums ──────────────────────────────────────────────────────────

class AggregationType(Enum):
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    STDDEV = "stddev"
    MEDIAN = "median"
    P95 = "p95"
    P99 = "p99"
    RATE = "rate"
    DELTA = "delta"


class AnomalyType(Enum):
    SPIKE = "spike"
    DROP = "drop"
    TREND_BREAK = "trend_break"
    SEASONALITY = "seasonality"
    LEVEL_SHIFT = "level_shift"
    VARIANCE_CHANGE = "variance_change"


# ─── Data Types ─────────────────────────────────────────────────────

@dataclass
class DataPoint:
    timestamp: float
    value: float
    labels: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def __lt__(self, other):
        return self.timestamp < other.timestamp


@dataclass
class TimeRange:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    def contains(self, ts: float) -> bool:
        return self.start <= ts <= self.end

    def overlaps(self, other: 'TimeRange') -> bool:
        return self.start < other.end and other.start < self.end


@dataclass
class AnomalyEvent:
    timestamp: float
    value: float
    expected: float
    anomaly_type: AnomalyType
    severity: float  # 0.0 to 1.0
    context: dict = field(default_factory=dict)


@dataclass
class AggregateResult:
    name: str
    value: float
    count: int
    time_range: TimeRange
    labels: dict = field(default_factory=dict)


# ─── Streaming Statistics ───────────────────────────────────────────

class StreamingStats:
    """Welford's online algorithm for streaming mean/variance."""

    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self.m2 = 0.0
        self.min_val = float('inf')
        self.max_val = float('-inf')
        self.sum = 0.0

    def update(self, value: float):
        self.n += 1
        self.sum += value
        delta = value - self.mean
        self.mean += delta / self.n
        delta2 = value - self.mean
        self.m2 += delta * delta2
        self.min_val = min(self.min_val, value)
        self.max_val = max(self.max_val, value)

    @property
    def variance(self) -> float:
        if self.n < 2:
            return 0.0
        return self.m2 / (self.n - 1)

    @property
    def stddev(self) -> float:
        return math.sqrt(self.variance)

    def merge(self, other: 'StreamingStats') -> 'StreamingStats':
        """Merge two streaming stats (parallel computation)."""
        if other.n == 0:
            return self
        if self.n == 0:
            return other

        result = StreamingStats()
        result.n = self.n + other.n
        result.sum = self.sum + other.sum

        delta = other.mean - self.mean
        result.mean = (self.n * self.mean + other.n * other.mean) / result.n
        result.m2 = self.m2 + other.m2 + delta**2 * self.n * other.n / result.n
        result.min_val = min(self.min_val, other.min_val)
        result.max_val = max(self.max_val, other.max_val)
        return result

    def z_score(self, value: float) -> float:
        if self.stddev < EPSILON:
            return 0.0
        return (value - self.mean) / self.stddev

    def to_dict(self) -> dict:
        return {
            'count': self.n,
            'mean': self.mean,
            'stddev': self.stddev,
            'min': self.min_val,
            'max': self.max_val,
            'sum': self.sum,
            'variance': self.variance,
        }


# ─── Sliding Window ────────────────────────────────────────────────

class SlidingWindow:
    """Time-based sliding window with efficient aggregation."""

    def __init__(self, window_size: float, max_points: int = MAX_WINDOW_SIZE):
        self.window_size = window_size
        self.max_points = max_points
        self._points: collections.deque = collections.deque()
        self._stats = StreamingStats()
        self._sorted_values: list = []
        self._lock = threading.Lock()

    def add(self, point: DataPoint):
        with self._lock:
            self._points.append(point)
            bisect.insort(self._sorted_values, point.value)
            self._stats.update(point.value)
            self._evict(point.timestamp)

    def _evict(self, now: float):
        cutoff = now - self.window_size
        while self._points and self._points[0].timestamp < cutoff:
            old = self._points.popleft()
            idx = bisect.bisect_left(self._sorted_values, old.value)
            if idx < len(self._sorted_values) and self._sorted_values[idx] == old.value:
                self._sorted_values.pop(idx)

        # Also enforce max size
        while len(self._points) > self.max_points:
            old = self._points.popleft()
            idx = bisect.bisect_left(self._sorted_values, old.value)
            if idx < len(self._sorted_values) and self._sorted_values[idx] == old.value:
                self._sorted_values.pop(idx)

    def percentile(self, p: float) -> float:
        with self._lock:
            if not self._sorted_values:
                return 0.0
            idx = int(math.ceil(p / 100 * len(self._sorted_values))) - 1
            idx = max(0, min(idx, len(self._sorted_values) - 1))
            return self._sorted_values[idx]

    def rate(self) -> float:
        with self._lock:
            if len(self._points) < 2:
                return 0.0
            duration = self._points[-1].timestamp - self._points[0].timestamp
            if duration < EPSILON:
                return 0.0
            return len(self._points) / duration

    @property
    def count(self) -> int:
        return len(self._points)

    @property
    def empty(self) -> bool:
        return len(self._points) == 0

    def values(self) -> list:
        with self._lock:
            return [p.value for p in self._points]

    def last(self, n: int = 1) -> list:
        with self._lock:
            return list(itertools.islice(reversed(self._points), n))


# ─── Exponential Moving Average ─────────────────────────────────────

class EMA:
    """Exponential Moving Average with configurable alpha."""

    def __init__(self, alpha: float = EMA_ALPHA_DEFAULT):
        if not 0 < alpha <= 1:
            raise ValueError(f"Alpha must be in (0, 1], got {alpha}")
        self.alpha = alpha
        self._value: Optional[float] = None
        self._count = 0

    def update(self, value: float) -> float:
        self._count += 1
        if self._value is None:
            self._value = value
        else:
            self._value = self.alpha * value + (1 - self.alpha) * self._value
        return self._value

    @property
    def value(self) -> Optional[float]:
        return self._value

    def reset(self):
        self._value = None
        self._count = 0


# ─── Reservoir Sampling ─────────────────────────────────────────────

class ReservoirSampler:
    """Vitter's Algorithm R for uniform reservoir sampling."""

    def __init__(self, size: int = RESERVOIR_SIZE):
        self.size = size
        self.reservoir: list = []
        self.count = 0

    def add(self, item: Any):
        self.count += 1
        if len(self.reservoir) < self.size:
            self.reservoir.append(item)
        else:
            idx = int(self.count * (hash(str(item)) % 10000) / 10000) % self.count
            if idx < self.size:
                self.reservoir[idx] = item

    def sample(self, n: int = 10) -> list:
        if n >= len(self.reservoir):
            return list(self.reservoir)
        import random
        return random.sample(self.reservoir, n)

    @property
    def is_full(self) -> bool:
        return len(self.reservoir) >= self.size


# ─── Bloom Filter ───────────────────────────────────────────────────

class BloomFilter:
    """Space-efficient probabilistic set membership."""

    def __init__(self, size: int = BLOOM_FILTER_SIZE, hash_count: int = BLOOM_HASH_COUNT):
        self.size = size
        self.hash_count = hash_count
        self._bits = bytearray(size // 8 + 1)
        self._count = 0

    def _hashes(self, item: str) -> list:
        h1 = int(hashlib.md5(item.encode()).hexdigest(), 16)
        h2 = int(hashlib.sha1(item.encode()).hexdigest(), 16)
        return [(h1 + i * h2) % self.size for i in range(self.hash_count)]

    def add(self, item: str):
        for pos in self._hashes(item):
            byte_idx = pos // 8
            bit_idx = pos % 8
            self._bits[byte_idx] |= (1 << bit_idx)
        self._count += 1

    def __contains__(self, item: str) -> bool:
        return all(
            self._bits[pos // 8] & (1 << (pos % 8))
            for pos in self._hashes(item)
        )

    @property
    def false_positive_rate(self) -> float:
        if self._count == 0:
            return 0.0
        k = self.hash_count
        m = self.size
        n = self._count
        return (1 - math.exp(-k * n / m)) ** k

    def __len__(self) -> int:
        return self._count


# ─── Histogram ──────────────────────────────────────────────────────

class Histogram:
    """Fixed-bucket histogram for distribution analysis."""

    def __init__(self, min_val: float, max_val: float, bins: int = HISTOGRAM_BINS):
        if min_val >= max_val:
            raise ValueError("min_val must be less than max_val")
        self.min_val = min_val
        self.max_val = max_val
        self.bins = bins
        self.bin_width = (max_val - min_val) / bins
        self.counts = [0] * bins
        self.total = 0
        self.overflow = 0
        self.underflow = 0

    def add(self, value: float):
        self.total += 1
        if value < self.min_val:
            self.underflow += 1
        elif value >= self.max_val:
            self.overflow += 1
        else:
            idx = int((value - self.min_val) / self.bin_width)
            idx = min(idx, self.bins - 1)
            self.counts[idx] += 1

    def percentile(self, p: float) -> float:
        target = int(math.ceil(p / 100 * self.total))
        cumulative = self.underflow
        for i, count in enumerate(self.counts):
            cumulative += count
            if cumulative >= target:
                return self.min_val + (i + 0.5) * self.bin_width
        return self.max_val

    def density(self) -> list:
        if self.total == 0:
            return [(self.min_val + (i + 0.5) * self.bin_width, 0.0) for i in range(self.bins)]
        return [
            (self.min_val + (i + 0.5) * self.bin_width, count / (self.total * self.bin_width))
            for i, count in enumerate(self.counts)
        ]

    def entropy(self) -> float:
        if self.total == 0:
            return 0.0
        h = 0.0
        for count in self.counts:
            if count > 0:
                p = count / self.total
                h -= p * math.log2(p)
        return h

    def to_dict(self) -> dict:
        return {
            'min': self.min_val,
            'max': self.max_val,
            'bins': self.bins,
            'total': self.total,
            'overflow': self.overflow,
            'underflow': self.underflow,
            'counts': self.counts,
            'entropy': self.entropy(),
        }


# ─── Anomaly Detector ──────────────────────────────────────────────

class AnomalyDetector:
    """Multi-strategy anomaly detection on time series."""

    def __init__(self, z_threshold: float = ANOMALY_Z_THRESHOLD,
                 window_size: int = 100, sensitivity: float = 1.0):
        self.z_threshold = z_threshold * (1 / max(sensitivity, 0.1))
        self.window_size = window_size
        self._stats = StreamingStats()
        self._window: collections.deque = collections.deque(maxlen=window_size)
        self._ema = EMA(alpha=0.05)
        self._ema_variance = EMA(alpha=0.05)
        self._trend_window: collections.deque = collections.deque(maxlen=window_size)
        self._anomalies: list = []

    def check(self, point: DataPoint) -> Optional[AnomalyEvent]:
        self._window.append(point)
        self._stats.update(point.value)
        ema_val = self._ema.update(point.value)

        # Update variance EMA
        if ema_val is not None:
            deviation_sq = (point.value - ema_val) ** 2
            self._ema_variance.update(deviation_sq)

        if self._stats.n < 10:
            return None

        # Z-score anomaly
        z = self._stats.z_score(point.value)
        if abs(z) > self.z_threshold:
            anomaly_type = AnomalyType.SPIKE if z > 0 else AnomalyType.DROP
            severity = min(1.0, abs(z) / (self.z_threshold * 2))
            event = AnomalyEvent(
                timestamp=point.timestamp,
                value=point.value,
                expected=self._stats.mean,
                anomaly_type=anomaly_type,
                severity=severity,
                context={'z_score': z, 'mean': self._stats.mean, 'stddev': self._stats.stddev},
            )
            self._anomalies.append(event)
            return event

        # Trend break detection
        if len(self._window) >= self.window_size:
            trend_break = self._detect_trend_break()
            if trend_break:
                return trend_break

        # Variance change detection
        variance_change = self._detect_variance_change(point)
        if variance_change:
            return variance_change

        return None

    def _detect_trend_break(self) -> Optional[AnomalyEvent]:
        """Detect sudden change in trend direction."""
        if len(self._window) < 20:
            return None

        points = list(self._window)
        mid = len(points) // 2

        first_half = [p.value for p in points[:mid]]
        second_half = [p.value for p in points[mid:]]

        slope1 = self._linear_slope(first_half)
        slope2 = self._linear_slope(second_half)

        if slope1 is None or slope2 is None:
            return None

        # Significant direction change
        if abs(slope2 - slope1) > self._stats.stddev * 2:
            event = AnomalyEvent(
                timestamp=points[-1].timestamp,
                value=points[-1].value,
                expected=self._stats.mean,
                anomaly_type=AnomalyType.TREND_BREAK,
                severity=min(1.0, abs(slope2 - slope1) / (self._stats.stddev * 4)),
                context={'slope_before': slope1, 'slope_after': slope2},
            )
            self._anomalies.append(event)
            return event
        return None

    def _detect_variance_change(self, point: DataPoint) -> Optional[AnomalyEvent]:
        """Detect sudden change in variance (volatility)."""
        if self._ema_variance.value is None or self._stats.n < 30:
            return None

        expected_var = self._ema_variance.value
        actual_var = self._stats.variance

        if expected_var < EPSILON:
            return None

        ratio = actual_var / expected_var
        if ratio > 3.0 or ratio < 0.33:
            event = AnomalyEvent(
                timestamp=point.timestamp,
                value=point.value,
                expected=self._stats.mean,
                anomaly_type=AnomalyType.VARIANCE_CHANGE,
                severity=min(1.0, abs(math.log(ratio)) / 3.0),
                context={'variance_ratio': ratio, 'expected_var': expected_var, 'actual_var': actual_var},
            )
            self._anomalies.append(event)
            return event
        return None

    @staticmethod
    def _linear_slope(values: list) -> Optional[float]:
        n = len(values)
        if n < 3:
            return None
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        if abs(denominator) < EPSILON:
            return None
        return numerator / denominator

    @property
    def anomaly_count(self) -> int:
        return len(self._anomalies)

    def recent_anomalies(self, n: int = 10) -> list:
        return self._anomalies[-n:]


# ─── Time Series Aggregator ────────────────────────────────────────

class TimeSeriesAggregator:
    """Aggregate time series data into fixed intervals."""

    def __init__(self, interval: float):
        self.interval = interval
        self._buckets: dict = collections.defaultdict(list)

    def add(self, point: DataPoint):
        bucket_key = int(point.timestamp / self.interval) * self.interval
        self._buckets[bucket_key].append(point)

    def aggregate(self, agg_type: AggregationType) -> list:
        results = []
        for bucket_ts in sorted(self._buckets.keys()):
            points = self._buckets[bucket_ts]
            values = [p.value for p in points]

            value = self._compute_aggregation(values, agg_type, bucket_ts)
            results.append(AggregateResult(
                name=agg_type.value,
                value=value,
                count=len(values),
                time_range=TimeRange(bucket_ts, bucket_ts + self.interval),
            ))
        return results

    def _compute_aggregation(self, values: list, agg_type: AggregationType,
                             bucket_ts: float) -> float:
        if not values:
            return 0.0

        if agg_type == AggregationType.SUM:
            return sum(values)
        elif agg_type == AggregationType.AVG:
            return statistics.mean(values)
        elif agg_type == AggregationType.MIN:
            return min(values)
        elif agg_type == AggregationType.MAX:
            return max(values)
        elif agg_type == AggregationType.COUNT:
            return float(len(values))
        elif agg_type == AggregationType.STDDEV:
            return statistics.stdev(values) if len(values) > 1 else 0.0
        elif agg_type == AggregationType.MEDIAN:
            return statistics.median(values)
        elif agg_type == AggregationType.P95:
            return self._percentile(values, 95)
        elif agg_type == AggregationType.P99:
            return self._percentile(values, 99)
        elif agg_type == AggregationType.RATE:
            return len(values) / self.interval
        elif agg_type == AggregationType.DELTA:
            return values[-1] - values[0] if len(values) > 1 else 0.0
        else:
            return sum(values) / len(values)

    @staticmethod
    def _percentile(values: list, p: float) -> float:
        sorted_vals = sorted(values)
        idx = int(math.ceil(p / 100 * len(sorted_vals))) - 1
        return sorted_vals[max(0, min(idx, len(sorted_vals) - 1))]

    def clear(self):
        self._buckets.clear()


# ─── Pipeline Processing ───────────────────────────────────────────

class Pipeline:
    """Composable data processing pipeline."""

    def __init__(self):
        self._stages: list = []

    def add_stage(self, name: str, fn: Callable):
        self._stages.append((name, fn))
        return self

    def process(self, data: Iterator) -> Iterator:
        result = data
        for name, fn in self._stages:
            result = fn(result)
        return result

    def process_batch(self, items: list) -> list:
        result = items
        for name, fn in self._stages:
            result = list(fn(iter(result)))
        return result

    @property
    def stage_count(self) -> int:
        return len(self._stages)


def filter_stage(predicate: Callable) -> Callable:
    def stage(data: Iterator) -> Iterator:
        return filter(predicate, data)
    return stage


def map_stage(transform: Callable) -> Callable:
    def stage(data: Iterator) -> Iterator:
        return map(transform, data)
    return stage


def window_stage(size: int) -> Callable:
    def stage(data: Iterator) -> Iterator:
        window = collections.deque(maxlen=size)
        for item in data:
            window.append(item)
            if len(window) == size:
                yield list(window)
    return stage


def batch_stage(size: int) -> Callable:
    def stage(data: Iterator) -> Iterator:
        batch = []
        for item in data:
            batch.append(item)
            if len(batch) >= size:
                yield batch
                batch = []
        if batch:
            yield batch
    return stage


def deduplicate_stage(key_fn: Callable = None) -> Callable:
    def stage(data: Iterator) -> Iterator:
        seen = set()
        for item in data:
            k = key_fn(item) if key_fn else item
            if k not in seen:
                seen.add(k)
                yield item
    return stage


# ─── Top-K Tracker ──────────────────────────────────────────────────

class TopK:
    """Track top-K items by score using a min-heap."""

    def __init__(self, k: int = 10):
        self.k = k
        self._heap: list = []

    def add(self, item: Any, score: float):
        if len(self._heap) < self.k:
            heapq.heappush(self._heap, (score, id(item), item))
        elif score > self._heap[0][0]:
            heapq.heapreplace(self._heap, (score, id(item), item))

    def top(self) -> list:
        return sorted(
            [(item, score) for score, _, item in self._heap],
            key=lambda x: -x[1]
        )

    @property
    def min_score(self) -> float:
        if not self._heap:
            return float('-inf')
        return self._heap[0][0]

    def __len__(self) -> int:
        return len(self._heap)


# ─── HyperLogLog ───────────────────────────────────────────────────

class HyperLogLog:
    """Probabilistic cardinality estimation (count distinct)."""

    def __init__(self, precision: int = 14):
        self.precision = precision
        self.m = 1 << precision  # number of registers
        self.registers = bytearray(self.m)
        self.alpha = self._compute_alpha()

    def _compute_alpha(self) -> float:
        if self.m == 16:
            return 0.673
        elif self.m == 32:
            return 0.697
        elif self.m == 64:
            return 0.709
        else:
            return 0.7213 / (1 + 1.079 / self.m)

    def add(self, item: str):
        h = int(hashlib.sha256(item.encode()).hexdigest(), 16)
        idx = h & (self.m - 1)
        remaining = h >> self.precision
        rank = self._leading_zeros(remaining) + 1
        self.registers[idx] = max(self.registers[idx], rank)

    @staticmethod
    def _leading_zeros(value: int, max_bits: int = 64) -> int:
        if value == 0:
            return max_bits
        count = 0
        for i in range(max_bits - 1, -1, -1):
            if value & (1 << i):
                break
            count += 1
        return count

    def count(self) -> int:
        indicator = sum(2.0 ** (-r) for r in self.registers)
        estimate = self.alpha * self.m * self.m / indicator

        # Small range correction
        if estimate <= 2.5 * self.m:
            zeros = self.registers.count(0)
            if zeros > 0:
                estimate = self.m * math.log(self.m / zeros)

        # Large range correction
        if estimate > (1 << 32) / 30:
            estimate = -(1 << 32) * math.log(1 - estimate / (1 << 32))

        return int(estimate)

    def merge(self, other: 'HyperLogLog') -> 'HyperLogLog':
        if self.precision != other.precision:
            raise ValueError("Cannot merge HLLs with different precision")
        result = HyperLogLog(self.precision)
        result.registers = bytearray(
            max(a, b) for a, b in zip(self.registers, other.registers)
        )
        return result


# ─── Count-Min Sketch ───────────────────────────────────────────────

class CountMinSketch:
    """Probabilistic frequency estimation."""

    def __init__(self, width: int = 2048, depth: int = 5):
        self.width = width
        self.depth = depth
        self.table = [[0] * width for _ in range(depth)]
        self.total = 0

    def _hashes(self, item: str) -> list:
        h = hashlib.sha256(item.encode()).digest()
        return [
            int.from_bytes(h[i*4:(i+1)*4], 'big') % self.width
            for i in range(self.depth)
        ]

    def add(self, item: str, count: int = 1):
        self.total += count
        for i, pos in enumerate(self._hashes(item)):
            self.table[i][pos] += count

    def estimate(self, item: str) -> int:
        return min(
            self.table[i][pos]
            for i, pos in enumerate(self._hashes(item))
        )

    def frequency(self, item: str) -> float:
        if self.total == 0:
            return 0.0
        return self.estimate(item) / self.total

    def merge(self, other: 'CountMinSketch') -> 'CountMinSketch':
        if self.width != other.width or self.depth != other.depth:
            raise ValueError("Cannot merge sketches with different dimensions")
        result = CountMinSketch(self.width, self.depth)
        result.total = self.total + other.total
        for i in range(self.depth):
            for j in range(self.width):
                result.table[i][j] = self.table[i][j] + other.table[i][j]
        return result


# ─── Moving Window Correlation ──────────────────────────────────────

class WindowCorrelation:
    """Streaming Pearson correlation between two series."""

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self._x: collections.deque = collections.deque(maxlen=window_size)
        self._y: collections.deque = collections.deque(maxlen=window_size)

    def add(self, x: float, y: float):
        self._x.append(x)
        self._y.append(y)

    def correlation(self) -> float:
        if len(self._x) < 3:
            return 0.0

        x_vals = list(self._x)
        y_vals = list(self._y)
        n = len(x_vals)

        x_mean = sum(x_vals) / n
        y_mean = sum(y_vals) / n

        cov = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, y_vals))
        var_x = sum((x - x_mean) ** 2 for x in x_vals)
        var_y = sum((y - y_mean) ** 2 for y in y_vals)

        denom = math.sqrt(var_x * var_y)
        if denom < EPSILON:
            return 0.0
        return cov / denom

    @property
    def filled(self) -> bool:
        return len(self._x) >= self.window_size


# ─── Rate Tracker ───────────────────────────────────────────────────

class RateTracker:
    """Track event rate over time windows."""

    def __init__(self, windows: list = None):
        self.windows = windows or [60, 300, 900, 3600]
        self._events: collections.deque = collections.deque()
        self._lock = threading.Lock()

    def record(self, timestamp: float = None):
        ts = timestamp or time.time()
        with self._lock:
            self._events.append(ts)
            self._cleanup(ts)

    def _cleanup(self, now: float):
        max_window = max(self.windows)
        cutoff = now - max_window
        while self._events and self._events[0] < cutoff:
            self._events.popleft()

    def rates(self, now: float = None) -> dict:
        now = now or time.time()
        with self._lock:
            self._cleanup(now)
            result = {}
            for window in self.windows:
                cutoff = now - window
                count = sum(1 for t in self._events if t >= cutoff)
                result[f"{window}s"] = count / window
            return result

    @property
    def total(self) -> int:
        return len(self._events)


# ─── Main — Demo ───────────────────────────────────────────────────

def demo():
    """Run analytics demo."""
    import random

    # Streaming stats
    stats = StreamingStats()
    for i in range(10000):
        stats.update(random.gauss(100, 15))
    print(f"Stats: mean={stats.mean:.2f}, stddev={stats.stddev:.2f}, n={stats.n}")

    # Anomaly detection
    detector = AnomalyDetector(window_size=50)
    anomalies = []
    for i in range(500):
        value = random.gauss(100, 10)
        if i == 250:
            value = 300  # inject spike
        point = DataPoint(timestamp=time.time() + i, value=value)
        event = detector.check(point)
        if event:
            anomalies.append(event)
    print(f"Anomalies detected: {len(anomalies)}")

    # Bloom filter
    bf = BloomFilter()
    for i in range(10000):
        bf.add(f"item_{i}")
    print(f"Bloom: {len(bf)} items, FPR={bf.false_positive_rate:.6f}")

    # HyperLogLog
    hll = HyperLogLog()
    for i in range(100000):
        hll.add(f"user_{i}")
    print(f"HLL estimate: {hll.count()} (actual: 100000)")

    # Pipeline
    pipeline = Pipeline()
    pipeline.add_stage("filter", filter_stage(lambda x: x > 50))
    pipeline.add_stage("transform", map_stage(lambda x: x * 2))
    data = range(100)
    result = pipeline.process_batch(list(data))
    print(f"Pipeline: {len(result)} items after filter+transform")


if __name__ == "__main__":
    demo()
