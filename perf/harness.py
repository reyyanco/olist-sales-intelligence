"""Ölçüm yardımcıları: süre, sonuç özeti, EXPLAIN planı.

Kurallar:
- Isınma çalışmaları (WARMUP_RUNS) ayrı tutulur ve ölçüme katılmaz.
- Ölçüm: istemcide execute + fetchall süresi (time.perf_counter), MEASURED_RUNS kez.
- Önbellek temizlenmez; tüm ölçümler sıcak önbellek (warm cache) koşulundadır.
- EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ayrı bir çalıştırmadır, süre ölçümüne karışmaz.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

WARMUP_RUNS = 2
MEASURED_RUNS = 7
# Her perf bağlantısında statement_timeout. Sınırı aşan ölçüm süre uydurulmadan "timed_out" kaydedilir.
QUERY_TIMEOUT_MS = 60_000


class QueryTimeout(Exception):
    def __init__(self, phase: str, completed_ms: list[float]):
        super().__init__(f"statement_timeout ({QUERY_TIMEOUT_MS} ms) aşıldı: {phase}")
        self.phase = phase
        self.completed_ms = completed_ms

    def to_dict(self) -> dict:
        return {"timed_out": True, "timeout_ms": QUERY_TIMEOUT_MS, "phase": self.phase,
                "completed_runs_ms": self.completed_ms}


def _is_timeout(exc: Exception) -> bool:
    import psycopg2.errors

    return isinstance(exc, psycopg2.errors.QueryCanceled)


@dataclass
class Measurement:
    timings_ms: list[float]
    row_count: int
    result_md5: str
    warmup_runs: int = WARMUP_RUNS
    median_ms: float = field(init=False)
    min_ms: float = field(init=False)
    max_ms: float = field(init=False)

    def __post_init__(self) -> None:
        self.median_ms = round(statistics.median(self.timings_ms), 3)
        self.min_ms = round(min(self.timings_ms), 3)
        self.max_ms = round(max(self.timings_ms), 3)

    def to_dict(self) -> dict:
        return asdict(self)


def fetch(conn, sql: str, params: dict | None = None) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, params or {})
        return cur.fetchall() if cur.description else []


def execute(conn, sql: str, params: dict | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(sql, params or {})


def result_digest(rows: list[tuple], ordered: bool) -> str:
    data = rows if ordered else sorted(rows, key=repr)
    return hashlib.md5(repr(data).encode("utf-8")).hexdigest()


def measure(conn, sql: str, params: dict | None = None, ordered: bool = True,
            warmup: int = WARMUP_RUNS, runs: int = MEASURED_RUNS) -> Measurement:
    """Zaman aşımında QueryTimeout yükseltir (o ana kadarki ölçümlerle)."""
    timings, rows = [], []
    try:
        for _ in range(warmup):
            fetch(conn, sql, params)
    except Exception as exc:
        if _is_timeout(exc):
            raise QueryTimeout("warmup", []) from exc
        raise
    try:
        for _ in range(runs):
            started = time.perf_counter()
            rows = fetch(conn, sql, params)
            timings.append(round((time.perf_counter() - started) * 1000, 3))
    except Exception as exc:
        if _is_timeout(exc):
            raise QueryTimeout("measured", timings) from exc
        raise
    return Measurement(timings, len(rows), result_digest(rows, ordered), warmup)


def measure_or_timeout(conn, sql: str, params: dict | None = None, ordered: bool = True) -> dict:
    try:
        return measure(conn, sql, params, ordered).to_dict()
    except QueryTimeout as t:
        return t.to_dict()


def time_statement(conn, statements: list[str], warmup: int = 1, runs: int = 5, setup: list[str] | None = None,
                   teardown: list[str] | None = None) -> Measurement:
    """Sonuç döndürmeyen ifadelerin (REFRESH, INSERT ...) süresi; setup/teardown süreye katılmaz."""
    timings = []
    for i in range(warmup + runs):
        for s in setup or []:
            execute(conn, s)
        started = time.perf_counter()
        for s in statements:
            execute(conn, s)
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        for s in teardown or []:
            execute(conn, s)
        if i >= warmup:
            timings.append(elapsed)
    return Measurement(timings, 0, "", warmup)


def explain(conn, sql: str, params: dict | None = None, analyze: bool = True) -> list:
    options = "ANALYZE, BUFFERS, FORMAT JSON" if analyze else "FORMAT JSON"
    with conn.cursor() as cur:
        cur.execute(f"EXPLAIN ({options}) " + sql, params or {})
        plan = cur.fetchone()[0]
    return plan if isinstance(plan, list) else json.loads(plan)


def explain_or_estimate(conn, sql: str, params: dict | None = None) -> tuple[list, bool]:
    """EXPLAIN ANALYZE; zaman aşımında yalnızca tahmini plan (sorgu çalıştırılmadan). (plan, analyzed)"""
    try:
        return explain(conn, sql, params), True
    except Exception as exc:
        if not _is_timeout(exc):
            raise
        return explain(conn, sql, params, analyze=False), False


def _walk(node: dict):
    yield node
    for child in node.get("Plans", []):
        yield from _walk(child)


def plan_summary(plan: list) -> dict:
    root = plan[0]
    top = root["Plan"]
    nodes = list(_walk(top))
    return {
        "total_cost_estimate": top.get("Total Cost"),
        "execution_time_ms": root.get("Execution Time"),
        "planning_time_ms": root.get("Planning Time"),
        "node_types": sorted({n["Node Type"] for n in nodes}),
        "indexes_used": sorted({n["Index Name"] for n in nodes if "Index Name" in n}),
        "seq_scans": sorted({n.get("Relation Name") for n in nodes if n["Node Type"] == "Seq Scan"} - {None}),
        "shared_hit_blocks": top.get("Shared Hit Blocks"),
        "shared_read_blocks": top.get("Shared Read Blocks"),
        "temp_written_blocks": top.get("Temp Written Blocks"),
        "jit": root.get("JIT") is not None,
    }


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
