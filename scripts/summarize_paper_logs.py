#!/usr/bin/env python3
"""Summarize paper JSONL logs — Phase 1: gates, conf, skip vs entry.

Usage:
  PYTHONPATH=. python scripts/summarize_paper_logs.py
  PYTHONPATH=. python scripts/summarize_paper_logs.py --days 7
  PYTHONPATH=. python scripts/summarize_paper_logs.py --json-out logs/summary.json
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent


def _parse_ts(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = str(s).replace(" UTC", "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(s[:26], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _infer_gate(reason: str, gate: str = "") -> str:
    g = (gate or "").strip().upper()
    if g:
        return g
    r = reason or ""
    rules = [
        (r"ADX H4|ADX_H4", "ADX_H4"),
        (r"ADX H1|ADX ต่ำ|ไม่มีเทรนด์ชัด", "ADX"),
        (r"W1 block|W1_BLOCK", "W1_BLOCK"),
        (r"MOM block|MOM ", "MOM"),
        (r"H4 NEUTRAL", "H4_NEUTRAL"),
        (r"H4_MISALIGN", "H4_MISALIGN"),
        (r"confluence|ไม่มี confluence", "CONF"),
        (r"ATR", "ATR"),
        (r"ไม่เพียงพอ|DATA", "DATA"),
    ]
    for pat, code in rules:
        if re.search(pat, r, re.I):
            return code
    return "OTHER" if r else "NONE"


def _f(row: dict, *keys: str, default: float = 0.0) -> float:
    for k in keys:
        v = row.get(k)
        if v is None or v == "":
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return default


def _parse_conf_from_reason(reason: str) -> tuple[float, float]:
    buy = sell = 0.0
    if not reason:
        return buy, sell
    m = re.search(r"Buy\s*=\s*([0-9.]+)", reason, re.I)
    if m:
        try:
            buy = float(m.group(1))
        except ValueError:
            pass
    m = re.search(r"Sell\s*=\s*([0-9.]+)", reason, re.I)
    if m:
        try:
            sell = float(m.group(1))
        except ValueError:
            pass
    return buy, sell


def _parse_slope_from_reason(reason: str) -> Optional[float]:
    m = re.search(r"slope\s*=\s*([+\-]?[0-9.]+)", reason or "", re.I)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def load_jsonl_files(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "event" in obj and isinstance(obj.get("data"), dict):
                    data = dict(obj["data"])
                    data["_event"] = obj["event"]
                    data["_ts"] = obj.get("ts") or data.get("ts")
                    rows.append(data)
                else:
                    obj["_event"] = {
                        "skip": "SIGNAL_NONE",
                        "dry-run": "DRY_RUN_SIGNAL",
                        "ordered": "ORDER",
                        "rejected": "RISK_REJECT",
                        "blocked_open_position": "BLOCKED_OPEN",
                        "closed": "POSITION_CLOSED",
                    }.get(obj.get("action"), obj.get("_event", "RECORD"))
                    obj["_ts"] = obj.get("ts")
                    rows.append(obj)
    return rows


def filter_days(rows: list[dict], days: Optional[int]) -> list[dict]:
    if not days or days <= 0:
        return rows
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for r in rows:
        ts = _parse_ts(str(r.get("_ts") or r.get("ts") or ""))
        if ts is None or ts >= cutoff:
            out.append(r)
    return out


def _enrich_row(r: dict) -> dict:
    out = dict(r)
    if _f(out, "conf_buy") == 0.0 and _f(out, "conf_sell") == 0.0:
        pb, ps = _parse_conf_from_reason(str(out.get("reason") or ""))
        if pb or ps:
            out["conf_buy"], out["conf_sell"] = pb, ps
    if _f(out, "slope_atr") == 0.0:
        sl = _parse_slope_from_reason(str(out.get("reason") or ""))
        if sl is not None:
            out["slope_atr"] = sl
    if not out.get("gate"):
        out["gate"] = _infer_gate(str(out.get("reason") or ""), "")
    return out


def _stats(vals: list[float]) -> dict[str, Any]:
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0, "mean": None, "median": None, "p25": None, "p75": None, "min": None, "max": None}
    vals_s = sorted(vals)
    n = len(vals_s)

    def pct(p: float) -> float:
        i = min(n - 1, max(0, int(round((p / 100.0) * (n - 1)))))
        return vals_s[i]

    return {
        "n": n,
        "mean": round(statistics.mean(vals_s), 4),
        "median": round(statistics.median(vals_s), 4),
        "p25": round(pct(25), 4),
        "p75": round(pct(75), 4),
        "min": round(vals_s[0], 4),
        "max": round(vals_s[-1], 4),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [_enrich_row(r) for r in rows]
    events = Counter(str(r.get("_event") or "UNKNOWN") for r in rows)
    skips: list[dict] = []
    entries: list[dict] = []
    closes: list[dict] = []
    alerts = Counter()
    gates = Counter()
    regimes = Counter()
    w1_bias = Counter()
    h4_bias = Counter()
    gate_conf: dict[str, list[float]] = defaultdict(list)

    for r in rows:
        ev = str(r.get("_event") or "")
        direction = str(r.get("direction") or "")
        is_skip = ev in ("SIGNAL_NONE", "signal.none") or direction == "NONE" or r.get("action") == "skip"
        is_entry = direction in ("BUY", "SELL") and (
            ev in ("DRY_RUN_SIGNAL", "ORDER", "RISK_REJECT") or direction in ("BUY", "SELL")
        )
        if is_skip:
            gate = _infer_gate(str(r.get("reason") or ""), str(r.get("gate") or ""))
            gates[gate] += 1
            regimes[str(r.get("regime") or "?")] += 1
            w1_bias[str(r.get("w1_bias") or "?")] += 1
            h4_bias[str(r.get("h4_bias") or r.get("timeframe_bias") or "?")] += 1
            skips.append(r)
            cmax = max(_f(r, "conf_buy"), _f(r, "conf_sell"))
            if cmax > 0:
                gate_conf[gate].append(cmax)
        if is_entry and direction in ("BUY", "SELL"):
            entries.append(r)
        ea = r.get("early_alert")
        if isinstance(ea, dict) and ea.get("active"):
            alerts[str(ea.get("kind") or "ALERT")] += 1
        if ev in ("TRADE_CLOSED", "POSITION_CLOSED") or ("won" in r and "pnl" in r):
            closes.append(r)

    def side_stats(group: list[dict]) -> dict[str, Any]:
        has_conf = [r for r in group if _f(r, "conf_buy") > 0 or _f(r, "conf_sell") > 0]
        return {
            "n": len(group),
            "conf_buy": _stats([_f(r, "conf_buy") for r in has_conf]),
            "conf_sell": _stats([_f(r, "conf_sell") for r in has_conf]),
            "conf_max": _stats([max(_f(r, "conf_buy"), _f(r, "conf_sell")) for r in has_conf]),
            "slope_atr": _stats([_f(r, "slope_atr") for r in group]),
            "adx_h1": _stats([_f(r, "adx_h1", "adx") for r in group if _f(r, "adx_h1", "adx") > 0]),
            "adx_h4": _stats([_f(r, "adx_h4") for r in group if _f(r, "adx_h4") > 0]),
            "directions": dict(Counter(str(r.get("direction")) for r in group)),
        }

    skip_stats = side_stats(skips)
    entry_stats = side_stats(entries)

    near_misses = []
    for r in skips:
        gate = _infer_gate(str(r.get("reason") or ""), str(r.get("gate") or ""))
        if gate not in ("CONF", "MOM", "H4_MISALIGN"):
            continue
        cmax = max(_f(r, "conf_buy"), _f(r, "conf_sell"))
        min_c = _f(r, "min_confluence", default=0.62) or 0.62
        if cmax > 0 and cmax >= (min_c - 0.10):
            near_misses.append({
                "ts": r.get("ts") or r.get("_ts"),
                "gate": gate,
                "conf_buy": _f(r, "conf_buy"),
                "conf_sell": _f(r, "conf_sell"),
                "slope_atr": _f(r, "slope_atr"),
                "adx_h1": _f(r, "adx_h1", "adx"),
                "h4_bias": r.get("h4_bias") or r.get("timeframe_bias"),
                "price": r.get("price"),
                "gap_to_min": round(min_c - cmax, 4),
            })
    near_misses = sorted(near_misses, key=lambda x: x.get("gap_to_min") or 99)[:30]

    none_n = sum(gates.values())
    return {
        "events": dict(events),
        "gates": dict(gates),
        "gate_pct": {k: round(100 * v / none_n, 1) for k, v in gates.items()} if none_n else {},
        "gate_avg_conf_max": {k: round(statistics.mean(vs), 4) if vs else None for k, vs in gate_conf.items()},
        "regimes": dict(regimes),
        "w1_bias": dict(w1_bias),
        "h4_bias": dict(h4_bias),
        "alerts": dict(alerts),
        "skips": skip_stats,
        "entries": entry_stats,
        "near_misses": near_misses,
        "closes": closes,
        "n_rows": len(rows),
        "n_none": none_n,
        "n_signals": entry_stats["n"],
        "signals": entries[-20:],
    }


def _fmt_stats(label: str, st: dict) -> None:
    if not st or st.get("n", 0) == 0:
        print(f"  {label}: (no data)")
        return
    print(
        f"  {label}: n={st['n']} mean={st['mean']} med={st['median']} "
        f"p25={st['p25']} p75={st['p75']} min={st['min']} max={st['max']}"
    )


def print_report(summary: dict[str, Any], paths: list[Path]) -> None:
    print("=" * 68)
    print("PAPER LOG SUMMARY — Phase 1 (gate / conf / skip vs entry)")
    print("=" * 68)
    print(f"Files : {len(paths)}  Rows: {summary['n_rows']}")
    for p in paths[:12]:
        print(f"  - {p.name}")

    print("\n--- Events ---")
    for k, v in sorted(summary["events"].items(), key=lambda x: -x[1]):
        print(f"  {k:<28} {v:5d}")

    print("\n--- Gates on SIGNAL_NONE ---")
    if not summary["gates"]:
        print("  (no NONE records yet)")
    else:
        print(f"  {'Gate':<16} {'N':>5} {'%':>6}  {'avg conf_max':>12}")
        for k, v in sorted(summary["gates"].items(), key=lambda x: -x[1]):
            pct = summary["gate_pct"].get(k, 0)
            avg_c = summary.get("gate_avg_conf_max", {}).get(k)
            avg_s = f"{avg_c:.3f}" if avg_c is not None else "  -"
            print(f"  {k:<16} {v:5d} {pct:5.1f}%  {avg_s:>12}")
        print(f"  {'TOTAL':<16} {summary['n_none']:5d}")

    print("\n--- Bias on NONE ---")
    print("  H4:", dict(sorted(summary["h4_bias"].items(), key=lambda x: -x[1])))
    print("  W1:", dict(sorted(summary["w1_bias"].items(), key=lambda x: -x[1])))
    print("  Regime:", dict(sorted(summary["regimes"].items(), key=lambda x: -x[1])))

    print("\n--- SKIP feature stats ---")
    sk = summary["skips"]
    print(f"  N skips = {sk['n']}")
    _fmt_stats("conf_buy ", sk["conf_buy"])
    _fmt_stats("conf_sell", sk["conf_sell"])
    _fmt_stats("conf_max ", sk["conf_max"])
    _fmt_stats("slope_atr", sk["slope_atr"])
    _fmt_stats("adx_h1  ", sk["adx_h1"])
    _fmt_stats("adx_h4  ", sk["adx_h4"])

    print("\n--- ENTRY feature stats ---")
    en = summary["entries"]
    print(f"  N entries = {en['n']}  {en.get('directions')}")
    if en["n"] == 0:
        print("  (ยังไม่มีไม้เข้า)")
    else:
        _fmt_stats("conf_buy ", en["conf_buy"])
        _fmt_stats("conf_max ", en["conf_max"])
        _fmt_stats("slope_atr", en["slope_atr"])
        _fmt_stats("adx_h1  ", en["adx_h1"])

    print("\n--- SKIP vs ENTRY ---")
    if sk["conf_max"]["n"] and en["conf_max"]["n"]:
        print(f"  conf_max mean: skip={sk['conf_max']['mean']}  entry={en['conf_max']['mean']}")
        print(f"  slope mean:    skip={sk['slope_atr']['mean']}  entry={en['slope_atr']['mean']}")
        print(f"  adx_h1 mean:   skip={sk['adx_h1']['mean']}  entry={en['adx_h1']['mean']}")
    elif sk["conf_max"]["n"]:
        print(f"  conf_max (skip) mean={sk['conf_max']['mean']} med={sk['conf_max']['median']} p75={sk['conf_max']['p75']}")

    nm = summary.get("near_misses") or []
    print(f"\n--- Near-misses (conf within 0.10 of min) ---")
    if not nm:
        print("  (none)")
    else:
        for x in nm[:12]:
            print(
                f"    {x.get('ts')} gate={x.get('gate')} "
                f"buy={x.get('conf_buy'):.2f} sell={x.get('conf_sell'):.2f} "
                f"gap={x.get('gap_to_min'):+.3f} slope={x.get('slope_atr'):+.2f} "
                f"adx={x.get('adx_h1'):.1f} H4={x.get('h4_bias')} px={x.get('price')}"
            )

    print("\n--- Hints ---")
    gates = summary["gates"]
    if gates:
        top = max(gates.items(), key=lambda x: x[1])
        print(f"  Most common block: {top[0]} ({top[1]})")
        if gates.get("CONF", 0) >= 0.4 * max(summary["n_none"], 1):
            print("  → CONF หลัก — Phase-2: ลด min_confluence แบบมีเงื่อนไข H4 ADX")
        if gates.get("MOM", 0):
            print(f"  → MOM blocked {gates['MOM']}")
    if nm:
        print(f"  → near-miss {len(nm)} รอบ — ใช้ตัดสินใจปรับ threshold")
    print("=" * 68)


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize paper logs — Phase 1")
    ap.add_argument("--log-dir", type=str, default=str(ROOT / "logs"))
    ap.add_argument("--glob", type=str, default="paper_s1*.jsonl,orchestrator*.jsonl,*dryrun*.jsonl")
    ap.add_argument("--days", type=int, default=0)
    ap.add_argument("--json-out", type=str, default="")
    args = ap.parse_args()

    log_dir = Path(args.log_dir)
    patterns = [p.strip() for p in args.glob.split(",") if p.strip()]
    paths: list[Path] = []
    for pat in patterns:
        paths.extend(sorted(log_dir.glob(pat)))
    seen, uniq = set(), []
    for p in paths:
        if p.resolve() not in seen:
            seen.add(p.resolve())
            uniq.append(p)
    if not uniq:
        print(f"No log files in {log_dir}")
        return 1

    rows = filter_days(load_jsonl_files(uniq), args.days if args.days > 0 else None)
    summary = summarize(rows)
    print_report(summary, uniq)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        compact = {k: v for k, v in summary.items() if k not in ("signals", "closes")}
        compact["near_miss_n"] = len(summary.get("near_misses") or [])
        with open(out, "w", encoding="utf-8") as f:
            json.dump(compact, f, ensure_ascii=False, indent=2, default=str)
        print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
