"""Yükleme hattı testleri: ret/tekrar ayrımı, çalışma kaydı, ikinci yükleme ve kontrollü başarısızlıklar.

Veri: tests/fixtures/olist_quality_sample (sentetik). olist_sample'ın kopyası + hatalı kayıtlar:
- ...06 geçersiz tarih (2017-02-30), ...07 müşterisi kaynakta yok, ...08 bir kalemi olmayan ürüne bağlı,
  ...09 aynı order_id ile iki farklı satır (çelişkili anahtar), satıcı e...03 çelişkili anahtar,
  müşteri c...01 ve O2 ödemesi birebir tekrar, O1 için geçersiz yorum puanı (6).
Beklenen: teslim edilmiş satış metrikleri temiz örnekle (olist_sample) aynı.
"""

from __future__ import annotations

import shutil
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from etl.load_staging import load_staging
from etl.pipeline import QualityCheckError, _start_run, inspect_source_file, run_pipeline
from etl.transform import run_transform
from tests.conftest import QUALITY_SAMPLE_DIR

O = lambda n: "a" + "0" * 30 + str(n)  # noqa: E731

DW_TABLES = ["dim_customer", "dim_product", "dim_seller", "dim_date", "fact_orders", "fact_sales", "fact_payments"]


def snapshot(engine) -> dict:
    """dw tabloları, materialized view ve staging için satır sayısı + içerik özeti."""
    out = {}
    with engine.connect() as conn:
        for t in [f"dw.{n}" for n in DW_TABLES] + ["reporting.mv_monthly_sales", "staging.customers", "staging.orders"]:
            out[t] = tuple(
                conn.execute(text(f"SELECT count(*), md5(COALESCE(string_agg(x::text, '|' ORDER BY x::text), '')) FROM {t} x")).one()
            )
        out["kpis"] = dict(conn.execute(text("SELECT * FROM reporting.v_sales_kpis")).mappings().one())
    return out


def latest_run(engine) -> dict:
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT * FROM meta.etl_runs ORDER BY started_at DESC LIMIT 1")).mappings().one())


def copy_sample(tmp_path: Path) -> Path:
    target = tmp_path / "src"
    shutil.copytree(QUALITY_SAMPLE_DIR, target)
    return target


def drop_order(source: Path, order_id: str) -> None:
    """Bir siparişi ve ona bağlı kalem/ödeme/yorum satırlarını kopyadan çıkarır (veri farklı olsun diye)."""
    for name in ["olist_orders_dataset.csv", "olist_order_items_dataset.csv",
                 "olist_order_payments_dataset.csv", "olist_order_reviews_dataset.csv"]:
        path = source / name
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        path.write_text("".join(l for l in lines if order_id not in l), encoding="utf-8")


@pytest.fixture(scope="module")
def first_run(pipeline_engine):
    return run_pipeline(pipeline_engine, QUALITY_SAMPLE_DIR)


def test_file_counts_and_dispositions(first_run):
    assert first_run.status == "succeeded"
    counts = {f.source_table: (f.source_rows, f.staged_rows, f.accepted_rows, f.rejected_rows, f.duplicate_rows)
              for f in first_run.files}
    assert counts == {
        "customers": (9, 9, 8, 0, 1),
        "geolocation": (3, 3, 3, 0, 0),
        "orders": (10, 10, 5, 5, 0),
        "order_items": (11, 11, 6, 5, 0),
        "order_payments": (11, 11, 6, 4, 1),
        "order_reviews": (6, 6, 5, 1, 0),
        "products": (3, 3, 3, 0, 0),
        "sellers": (4, 4, 2, 2, 0),
        "category_translation": (2, 2, 2, 0, 0),
    }


def test_rejected_rows_have_reasons(pipeline_engine, first_run):
    with pipeline_engine.connect() as conn:
        rows = {
            (r.source_table, r.natural_key): (r.disposition, list(r.reasons), r.source_row)
            for r in conn.execute(text("SELECT * FROM meta.etl_rejected_rows WHERE run_id = :r"), {"r": str(first_run.run_id)})
        }
    assert rows[("orders", O(6))] == ("rejected", ["invalid_purchase_timestamp"], 6)
    assert rows[("orders", O(7))] == ("rejected", ["customer_not_found"], 7)
    assert rows[("orders", O(8))] == ("rejected", ["item_rejected"], 8)
    assert rows[("order_items", f"{O(8)}:1")][1] == ["product_not_found"]
    assert rows[("order_items", f"{O(8)}:2")][1] == ["order_rejected"]
    assert rows[("order_items", f"{O(6)}:1")][1] == ["order_rejected"]
    assert rows[("order_payments", f"{O(2)}:1")][:2] == ("duplicate_removed", ["exact_duplicate"])
    assert rows[("customers", "c" + "0" * 30 + "1")][:2] == ("duplicate_removed", ["exact_duplicate"])
    assert rows[("order_reviews", "f" + "0" * 30 + "6:" + O(1))][1] == ["invalid_review_score"]
    with pipeline_engine.connect() as conn:
        conflicts = conn.execute(
            text("SELECT source_table, count(*) FROM meta.etl_rejected_rows WHERE run_id = :r "
                 "AND 'conflicting_key' = ANY (reasons) GROUP BY 1"),
            {"r": str(first_run.run_id)},
        ).all()
    assert dict(conflicts) == {"orders": 2, "sellers": 2}


def test_accepted_data_matches_clean_sample_metrics(pipeline_engine, first_run):
    k = snapshot(pipeline_engine)["kpis"]
    assert (k["order_count"], k["customer_count"], k["item_count"]) == (3, 2, 5)
    assert (k["product_sales"], k["freight_amount"], k["payment_amount"]) == (
        Decimal("360.50"), Decimal("37.25"), Decimal("397.75"),
    )
    with pipeline_engine.connect() as conn:
        o1 = conn.execute(text("SELECT review_count, review_score_avg FROM dw.fact_orders WHERE order_id = :o"), {"o": O(1)}).one()
        o2 = conn.execute(text("SELECT payment_count, payment_value FROM dw.fact_orders WHERE order_id = :o"), {"o": O(2)}).one()
    assert tuple(o1) == (2, Decimal("4.00"))  # geçersiz yorum siparişi düşürmedi, ortalamaya da girmedi
    assert tuple(o2) == (1, Decimal("92.00"))  # birebir tekrar ödeme toplamı ikiye katlamadı


def test_run_log_and_checks(pipeline_engine, first_run):
    run = latest_run(pipeline_engine)
    assert run["run_id"] == first_run.run_id and run["status"] == "succeeded"
    assert run["finished_at"] is not None and run["duration_seconds"] > 0 and run["error_message"] is None
    with pipeline_engine.connect() as conn:
        checks = {r.check_name: (r.severity, r.passed, r.row_count) for r in conn.execute(
            text("SELECT * FROM meta.etl_run_checks WHERE run_id = :r"), {"r": str(first_run.run_id)})}
        files = conn.execute(text("SELECT count(*) FROM meta.etl_run_files WHERE run_id = :r"), {"r": str(first_run.run_id)}).scalar()
    errors = {n: v for n, v in checks.items() if v[0] == "error"}
    assert set(errors) == {
        "000_source_rows_match_staging", "010_row_counts_match_staging.sql", "020_order_totals_match_detail.sql",
        "030_reporting_totals_not_duplicated.sql", "040_dim_date_covers_orders.sql", "050_natural_keys_unique.sql",
        "060_no_orphans_in_dw.sql", "070_order_and_item_counts.sql", "080_reporting_analyses_consistent.sql",
        "090_dashboard_functions_consistent.sql",
    }
    assert all(passed for _, passed, _ in errors.values())
    assert checks["report/010_rejections_by_reason.sql"][2] > 0
    assert files == 9


def test_payment_difference_is_reported_not_forced(pipeline_engine, first_run):
    with pipeline_engine.connect() as conn:
        diffs = conn.execute(text("SELECT order_id, difference_type, difference, in_sales_scope FROM reporting.v_order_payment_differences")).all()
        o4 = conn.execute(text("SELECT payment_value, product_value FROM dw.fact_orders WHERE order_id = :o"), {"o": O(4)}).one()
    assert [tuple(d) for d in diffs] == [(O(4), "no_items", Decimal("25.00"), False)]
    assert tuple(o4) == (Decimal("25.00"), Decimal("0.00"))  # ödeme 0'a çekilmedi
    report = next(c for c in first_run.checks if c.name == "report/030_payment_vs_items_difference.sql")
    assert report.rows and report.rows[0]["order_count"] == 1


def test_category_translation_policy(pipeline_engine, first_run):
    with pipeline_engine.connect() as conn:
        rows = {r.product_id[-1]: (r.category_translation_status, r.category_label, r.category_name_english)
                for r in conn.execute(text("SELECT * FROM dw.dim_product"))}
    assert rows == {
        "1": ("translated", "health_beauty", "health_beauty"),
        "2": ("untranslated", "pc_gamer", None),
        "3": ("missing_category", "uncategorized", None),
    }


def test_source_files_are_not_modified(first_run):
    for f in first_run.files:
        sha, size, records = inspect_source_file(QUALITY_SAMPLE_DIR / f.file_name)
        assert (sha, size, records) == (f.file_sha256, f.file_bytes, f.source_rows)


def test_second_load_gives_identical_result(pipeline_engine, first_run):
    before = snapshot(pipeline_engine)
    second = run_pipeline(pipeline_engine, QUALITY_SAMPLE_DIR)
    after = snapshot(pipeline_engine)
    assert second.status == "succeeded" and second.run_id != first_run.run_id
    assert after == before
    with pipeline_engine.connect() as conn:
        per_run = dict(conn.execute(text(
            "SELECT run_id, count(*) FROM meta.etl_rejected_rows WHERE run_id IN (:a, :b) GROUP BY run_id"),
            {"a": str(first_run.run_id), "b": str(second.run_id)}).all())
    # 1 müşteri tekrarı + 5 sipariş + 5 kalem + 5 ödeme (4 ret, 1 tekrar) + 1 yorum + 2 satıcı
    assert per_run[first_run.run_id] == per_run[second.run_id] == 19


def test_failed_copy_keeps_previous_data_and_logs_failure(pipeline_engine, first_run, tmp_path):
    before = snapshot(pipeline_engine)
    source = copy_sample(tmp_path)
    # Fazla kolonlu satır: Python CSV okuyucu sayar, PostgreSQL COPY reddeder. orders dosyası,
    # customers ve geolocation staging'e yüklendikten SONRA işlenir; geri alma bunları da kapsamalı.
    with (source / "olist_orders_dataset.csv").open("a", encoding="utf-8") as fh:
        fh.write(f"{O(10)},c{'0' * 30}1,delivered,2017-02-01 10:00:00,,,,2017-02-20 00:00:00,EXTRA\n")
    with pytest.raises(Exception):
        run_pipeline(pipeline_engine, source)

    run = latest_run(pipeline_engine)
    assert run["status"] == "failed" and run["finished_at"] is not None
    assert "extra data after last expected column" in run["error_message"]
    assert snapshot(pipeline_engine) == before
    with pipeline_engine.connect() as conn:
        files = conn.execute(text("SELECT count(*) FROM meta.etl_run_files WHERE run_id = :r"), {"r": str(run["run_id"])}).scalar()
    assert files == 9  # başarısız çalışmanın dosya bilgileri rollback'e rağmen kayıtlı


def test_failed_quality_check_rolls_back_whole_load(pipeline_engine, first_run, tmp_path):
    before = snapshot(pipeline_engine)
    source = copy_sample(tmp_path)
    drop_order(source, O(5))  # farklı veri: başarılı olsaydı metrikler değişirdi
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "999_always_fails.sql").write_text("SELECT 'controlled failure' AS problem", encoding="utf-8")

    with pytest.raises(QualityCheckError, match="999_always_fails.sql"):
        run_pipeline(pipeline_engine, source, tests_dir=checks)

    assert snapshot(pipeline_engine) == before
    run = latest_run(pipeline_engine)
    assert run["status"] == "failed" and "QualityCheckError" in run["error_message"]
    with pipeline_engine.connect() as conn:
        recorded = dict(conn.execute(text("SELECT check_name, passed FROM meta.etl_run_checks WHERE run_id = :r"),
                                     {"r": str(run["run_id"])}).all())
        rejected = conn.execute(text("SELECT count(*) FROM meta.etl_rejected_rows WHERE run_id = :r"),
                                {"r": str(run["run_id"])}).scalar()
    assert recorded["999_always_fails.sql"] is False  # kontrol sonucu rollback'e rağmen kayıtlı
    assert rejected == 0  # ret kayıtları veriyle birlikte geri alındı


def test_readers_see_previous_data_while_load_in_progress(pipeline_engine, first_run, tmp_path):
    before = snapshot(pipeline_engine)
    source = copy_sample(tmp_path)
    drop_order(source, O(5))
    run_id = uuid.uuid4()
    _start_run(pipeline_engine, run_id, source)

    with pipeline_engine.connect() as writer:
        tx = writer.begin()
        writer.execute(text("SELECT set_config('etl.run_id', :r, true)"), {"r": str(run_id)})
        load_staging(writer, source)
        run_transform(writer)
        in_tx = writer.execute(text("SELECT order_count FROM reporting.v_sales_kpis")).scalar()

        # Ayrı oturum (dashboard gibi): kilit beklemeden önceki taahhüt edilmiş veriyi görmeli.
        with pipeline_engine.connect() as reader:
            reader.execute(text("SET statement_timeout = '5s'"))
            seen = reader.execute(text("SELECT order_count FROM reporting.v_sales_kpis")).scalar()
            mv = reader.execute(text("SELECT sum(order_count) FROM reporting.mv_monthly_sales")).scalar()
        tx.rollback()

    assert in_tx == 2  # yazan işlem yeni veriyi görüyor (O5 çıkarıldı)
    assert seen == before["kpis"]["order_count"] == 3
    assert mv == 3
    assert snapshot(pipeline_engine) == before
    with pipeline_engine.begin() as conn:
        conn.execute(text("UPDATE meta.etl_runs SET status = 'failed', finished_at = now(), "
                          "error_message = 'test: bilerek geri alındı' WHERE run_id = :r"), {"r": str(run_id)})


def test_missing_required_column_is_reported(pipeline_engine, first_run, tmp_path):
    before = snapshot(pipeline_engine)
    source = copy_sample(tmp_path)
    path = source / "olist_order_items_dataset.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    idx = header.index("freight_value")
    path.write_text("\n".join(",".join(c for i, c in enumerate(l.split(",")) if i != idx) for l in lines) + "\n", encoding="utf-8")
    with pytest.raises(Exception, match=r"eksik=\['freight_value'\]"):
        run_pipeline(pipeline_engine, source)
    assert snapshot(pipeline_engine) == before
    assert latest_run(pipeline_engine)["status"] == "failed"


def test_transform_refuses_to_run_without_run_id(pipeline_engine):
    with pytest.raises(Exception, match="etl.run_id"):
        run_transform(pipeline_engine)
