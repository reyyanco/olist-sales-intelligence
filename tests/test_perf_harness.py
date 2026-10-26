"""Performans düzeneğinin saf fonksiyonları (veritabanı gerektirmez)."""

from perf.harness import Measurement, plan_summary, result_digest


def test_measurement_statistics():
    m = Measurement([5.0, 1.0, 3.0, 4.0, 2.0], row_count=10, result_md5="x")
    assert (m.median_ms, m.min_ms, m.max_ms) == (3.0, 1.0, 5.0)
    assert m.to_dict()["timings_ms"] == [5.0, 1.0, 3.0, 4.0, 2.0]


def test_result_digest_order_sensitivity():
    rows = [(1, "a"), (2, "b")]
    assert result_digest(rows, ordered=True) != result_digest(list(reversed(rows)), ordered=True)
    assert result_digest(rows, ordered=False) == result_digest(list(reversed(rows)), ordered=False)


def test_plan_summary_collects_indexes_and_seq_scans():
    plan = [{
        "Plan": {
            "Node Type": "Nested Loop", "Shared Hit Blocks": 7, "Shared Read Blocks": 0, "Temp Written Blocks": 0,
            "Plans": [
                {"Node Type": "Index Scan", "Index Name": "perf_idx", "Relation Name": "dim_customer"},
                {"Node Type": "Seq Scan", "Relation Name": "fact_orders"},
            ],
        },
        "Planning Time": 0.1,
        "Execution Time": 0.5,
    }]
    s = plan_summary(plan)
    assert s["indexes_used"] == ["perf_idx"]
    assert s["seq_scans"] == ["fact_orders"]
    assert s["node_types"] == ["Index Scan", "Nested Loop", "Seq Scan"]
    assert (s["execution_time_ms"], s["shared_hit_blocks"], s["jit"]) == (0.5, 7, False)
