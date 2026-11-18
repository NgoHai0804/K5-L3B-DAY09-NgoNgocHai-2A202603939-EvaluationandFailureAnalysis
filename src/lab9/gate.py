"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def _threshold_looser(old: dict, new: dict) -> list[str]:
    """Return reasons a new threshold is weaker than the old one (ratchet)."""
    problems: list[str] = []
    if "max" in old and ("max" not in new or new["max"] > old["max"]):
        problems.append("max rose or was removed")
    if "min" in old and ("min" not in new or new["min"] < old["min"]):
        problems.append("min fell or was removed")
    if "max_increase" in old and ("max_increase" not in new or new["max_increase"] > old["max_increase"]):
        problems.append("max_increase rose or was removed")
    if old.get("no_significant_drop") and not new.get("no_significant_drop"):
        problems.append("no_significant_drop was removed")
    return problems


def _ratchet_problems(spec: dict, base_spec: dict) -> list[str]:
    """Same eval-set version: thresholds may only get stricter, never looser."""
    problems: list[str] = []
    new_metrics = {m["id"]: m for m in spec.get("metrics") or []}
    for old in base_spec.get("metrics") or []:
        mid = old["id"]
        new = new_metrics.get(mid)
        if new is None:
            problems.append(f"ratchet: metric {mid} disappeared")
            continue
        problems += [f"ratchet: {mid}: {detail}"
                     for detail in _threshold_looser(old.get("threshold") or {}, new.get("threshold") or {})]
        if old.get("blocking") and not new.get("blocking"):
            problems.append(f"ratchet: {mid} is no longer blocking")

    new_slices = {(s.get("name"), s.get("metric")): s for s in spec.get("slices") or []}
    for old in base_spec.get("slices") or []:
        key = (old.get("name"), old.get("metric"))
        new = new_slices.get(key)
        if new is None:
            problems.append(f"ratchet: slice {key[0]}/{key[1]} disappeared")
            continue
        if "min" in old and ("min" not in new or new["min"] < old["min"]):
            problems.append(f"ratchet: slice {key[0]}/{key[1]} min fell or was removed")
        if old.get("no_significant_drop") and not new.get("no_significant_drop"):
            problems.append(f"ratchet: slice {key[0]}/{key[1]} no_significant_drop removed")
        if old.get("blocking") and not new.get("blocking"):
            problems.append(f"ratchet: slice {key[0]}/{key[1]} no longer blocking")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate."""
    problems: list[str] = []
    rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    manifest = pr.get("manifest") or {}

    # 1) aggregate metric must be a finite number (NaN/inf silently escapes comparisons)
    for key, value in (pr.get("metrics") or {}).items():
        if isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(value):
            problems.append(f"metric {key}={value!r} is not finite")

    # 2) rows must match manifest items x seeds (dropped or duplicated rows)
    items = manifest.get("items")
    seeds = manifest.get("seeds") or []
    if isinstance(items, int) and seeds:
        expected = items * len(seeds)
        if len(rows) != expected:
            problems.append(f"rows {len(rows)} != items×seeds {expected} (dropped/duplicated rows)")

    # 3) the (item_id, seed) set must equal the baseline's (cherry-picked seeds/items)
    pr_keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(set(pr_keys)) != len(pr_keys):
        problems.append("duplicate (item_id, seed) rows")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    missing = base_keys - set(pr_keys)
    extra = set(pr_keys) - base_keys
    if missing:
        problems.append(f"missing (item_id, seed) vs baseline: {len(missing)} e.g. {sorted(missing)[:3]}")
    if extra:
        problems.append(f"unexpected (item_id, seed) vs baseline: {len(extra)} e.g. {sorted(extra)[:3]}")

    # 4) crashed graders / missing values
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s)")
    if rows:
        graded = {m["id"] for m in spec.get("metrics") or []} & set(rows[0].keys())
        for row in rows:
            for mid in graded:
                value = row.get(mid)
                if value is None:
                    problems.append(f"{row.get('item_id')}@{row.get('seed')}: {mid} is None (grader missing)")
                elif isinstance(value, float) and not math.isfinite(value):
                    problems.append(f"{row.get('item_id')}@{row.get('seed')}: {mid}={value!r} is not finite")

    # 5) slice tags may not change per (item_id, seed) (relabel out of a slice)
    pr_tags = {(r.get("item_id"), r.get("seed")): tuple(sorted(r.get("slices") or [])) for r in rows}
    base_tags = {(r.get("item_id"), r.get("seed")): tuple(sorted(r.get("slices") or [])) for r in base_rows}
    changed = [k for k in pr_tags.keys() & base_tags.keys() if pr_tags[k] != base_tags[k]]
    if changed:
        problems.append(f"slice tags changed for {len(changed)} row(s), e.g. {sorted(changed)[:3]}")

    # 6) ratchet: a looser spec on the same eval-set version is not a valid comparison
    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        problems += _ratchet_problems(spec, base_spec)
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for item in spec.get("slices") or []:
        name, metric = item["name"], item["metric"]
        pr_items = per_item(pr, metric, slice_name=name)
        base_items = per_item(base, metric, slice_name=name)
        value = round(sum(pr_items.values()) / len(pr_items), 4) if pr_items else None
        failed = False
        note = ""
        if value is None:
            failed = True
            note = "empty slice"
        else:
            if "min" in item and value < item["min"]:
                failed = True
                note = f"< min {item['min']}"
            if item.get("no_significant_drop"):
                keys = sorted(set(pr_items) & set(base_items))
                if keys:
                    d, lo, hi = stats.paired_bootstrap(
                        [pr_items[k] for k in keys], [base_items[k] for k in keys],
                        n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        failed = True
        slice_id = f"slice:{name}/{metric}"
        if failed and item.get("blocking"):
            blocked.append(slice_id)
        threshold = {k: item[k] for k in ("min", "no_significant_drop") if k in item}
        verdict = "BLOCK" if failed and item.get("blocking") else ("warn" if failed else "ok")
        lines.append(f"  {slice_id:<34} {value!s:<8} {json.dumps(threshold):<38} {note:<28} {verdict}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
