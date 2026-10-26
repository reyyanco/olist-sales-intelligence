"""docs/perf/results/*.json dosyalarından özet tabloları üretir (elle düzenlenmez)."""

from __future__ import annotations

import json
from pathlib import Path


def _load(results_dir: Path, name: str):
    path = results_dir / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _ms(m: dict) -> str:
    if m.get("timed_out"):
        return f"zaman aşımı (>{m['timeout_ms']}, {m['phase']}) | - | -"
    return f"{m['median_ms']:.3f} | {m['min_ms']:.3f} | {m['max_ms']:.3f}"


def _speedup(s: dict) -> str:
    if "median_speedup_vs_baseline" in s:
        return str(s["median_speedup_vs_baseline"])
    if "median_speedup_lower_bound" in s:
        return f"≥ {s['median_speedup_lower_bound']}"
    return ""


def _equal(s: dict) -> str:
    if s["state"] == "baseline":
        return "-"
    if "result_equal_to_reference" not in s:
        return "referans"
    v = s["result_equal_to_reference"]
    return "ölçülemedi" if v is None else f"{v} (ref: {s.get('result_reference_state')})"


def _list(values) -> str:
    return ", ".join(values) if values else "-"


def write_summary(results_dir: Path, out: Path) -> None:
    lines = ["# Performans Ölçümleri — Özet", "",
             "Bu dosya `python -m perf` tarafından `docs/perf/results/*.json` dosyalarından üretilir; elle düzenlenmez.",
             "Süreler milisaniye (ms). medyan | min | max. Önbellek temizlenmedi (sıcak önbellek).", ""]

    env = _load(results_dir, "environment.json")
    if env:
        lines += ["## Ortam", "", f"- Veri: {env['data']}", f"- Ölçüm zamanı (UTC): {env['measured_at_utc']}",
                  f"- {env['postgres_version']}",
                  f"- Konteyner CPU: {env['container_cpu_count']}, bellek: {env['container_mem_total_kb']} kB",
                  f"- Veritabanı boyutu: {env['database_size_bytes']} bayt",
                  "- Ayarlar: " + ", ".join(f"{k}={v}" for k, v in env["settings"].items()),
                  "- Satır sayıları: " + ", ".join(f"{k}={v}" for k, v in env["row_counts"].items()),
                  f"- Yöntem: {env['measurement_method']}", ""]

    base = _load(results_dir, "baseline_state.json")
    if base:
        lines += ["## Başlangıç durumu", "", "Kaldırılan indeksler (yalnızca olist_perf):", ""]
        lines += [f"- `{i['definition']}`" for i in base["dropped_indexes"]] or ["- yok"]
        lines += ["", f"Korunan indeks sayısı (PK/UNIQUE): {len(base['kept_indexes'])}", ""]

    params = _load(results_dir, "parameters.json")
    if params:
        lines += ["## Parametreler", ""] + [f"- `{k}` = `{v}`" for k, v in params["values"].items()] + [""]

    cat = _load(results_dir, "catalog.json")
    if cat:
        lines += ["## Başlangıç kataloğu (değişiklik yok)", "",
                  "| Sorgu | medyan | min | max | satır | Plan düğümleri |", "|---|---:|---:|---:|---:|---|"]
        for name, r in cat.items():
            lines.append(f"| {name} | {_ms(r['measurement'])} | {r['measurement'].get('row_count', '-')} | {_list(r['plan']['node_types'])} |")
        lines.append("")

    for path in sorted(results_dir.glob("E*.json")):
        exp = json.loads(path.read_text(encoding="utf-8"))
        lines += [f"## {exp['id']} — {exp['title']} ({exp['technique']})", "",
                  "| Durum | medyan | min | max | hızlanma | sonuç aynı | kullanılan indeks | Seq Scan | plan ANALYZE | uygulama ms (1 kez) | indeks bayt | yazma medyan ms |",
                  "|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|"]
        for s in exp["states"]:
            m, p = s["measurement"], s["plan"]
            size = sum(s.get("index_sizes_bytes", {}).values()) if s.get("index_sizes_bytes") else ""
            wc = s.get("write_cost", {}).get("median_ms", "")
            lines.append(
                f"| {s['state']} | {_ms(m)} | {_speedup(s)} | {_equal(s)} | {_list(p['indexes_used'])} | "
                f"{_list(p['seq_scans'])} | {s.get('plan_analyzed')} | {s.get('apply_ms_single_run') or ''} | {size} | {wc} |"
            )
        lines += ["", "EXPLAIN dosyaları: " + ", ".join(f"`plans/{s['plan_file']}`" for s in exp["states"]), ""]

    mv = _load(results_dir, "mv_costs.json")
    if mv:
        f = mv["freshness_demo"]
        lines += ["## E5 ek — materialized view maliyetleri", "",
                  "| Ölçüm | medyan | min | max |", "|---|---:|---:|---:|",
                  f"| REFRESH (normal) | {_ms(mv['refresh_plain'])} |",
                  f"| REFRESH CONCURRENTLY | {_ms(mv['refresh_concurrently'])} |", "",
                  f"- Satır: {mv['rows']}; depolama: heap {mv['storage_bytes']['heap']} bayt, UNIQUE indeks "
                  f"{mv['storage_bytes']['unique_index']} bayt, toplam {mv['storage_bytes']['total_with_indexes']} bayt",
                  f"- Güncellik: view toplamı {f['view_total_before']} → {f['view_total_after_change']}; "
                  f"yenilenmemiş MV toplamı {f['mv_total_without_refresh']} (değişikliği yansıtıyor mu: {f['mv_reflects_change']})", ""]

    load = _load(results_dir, "L1_load_comparison.json")
    if load:
        lines += ["## L1 — COPY ve pandas to_sql", "", f"- Kaynak: `{load['source_file']}` ({load['source_bytes']} bayt)",
                  f"- Hedef: {load['target_table']}; işlem: {load['transaction']}",
                  f"- Sürümler: {load['versions']}; to_sql ortak: {load['to_sql_common_kwargs']}",
                  f"- pandas.read_csv ({load['pandas_read_csv']['kwargs']}): {_ms(load['pandas_read_csv'])} ms",
                  f"- Tüm yöntemlerin sonucu aynı: {load['all_results_identical']}", "",
                  "| Yöntem | method | chunksize | medyan | min | max | satır |", "|---|---|---:|---:|---:|---:|---:|"]
        for r in load["methods"]:
            lines.append(f"| {r['name']} | {r.get('method', '-')} | {r.get('chunksize', '-')} | {_ms(r)} | {r['verify']['rows']} |")
        lines.append("")

    part = _load(results_dir, "P1_partitioning.json")
    if part:
        lines += ["## P1 — Partitioning (yalıtılmış, gerçek hacim)", "",
                  "Satır sayıları: " + ", ".join(f"{k}={v}" for k, v in part["row_counts"].items()), "",
                  "| Sorgu | Tablo | medyan | min | max | taranan tablolar | sonuç aynı | hızlanma |", "|---|---|---:|---:|---:|---|---|---:|"]
        for q, r in part["queries"].items():
            for label in ("plain", "partitioned"):
                s = r[label]
                lines.append(f"| {q} | {label} | {_ms(s['measurement'])} | {_list(s['plan']['seq_scans'])} | "
                             f"{r['result_equal']} | {r['median_speedup'] if label == 'partitioned' else ''} |")
        lines.append("")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
