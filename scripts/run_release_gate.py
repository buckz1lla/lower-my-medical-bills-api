import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_benchmarks() -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / "run_eob_benchmark.py")]
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


def _read_latest_snapshot() -> dict:
    latest_path = ROOT / "benchmarks" / "history" / "benchmark_latest.json"
    if not latest_path.exists():
        raise FileNotFoundError(f"Missing latest benchmark snapshot: {latest_path}")
    return json.loads(latest_path.read_text(encoding="utf-8"))


def _read_previous_snapshot() -> dict | None:
    trend_path = ROOT / "benchmarks" / "history" / "benchmark_trend.jsonl"
    if not trend_path.exists():
        return None

    lines = [line.strip() for line in trend_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 2:
        return None

    return json.loads(lines[-2])


def _pct(value: float) -> str:
    return f"{value:.2f}%"


def _delta(current: float, previous: float | None) -> str:
    if previous is None:
        return "n/a"
    diff = current - previous
    arrow = "->" if diff == 0 else ("up" if diff > 0 else "down")
    sign = "+" if diff > 0 else ""
    return f"{arrow} ({sign}{diff:.2f}pp)"


def _meets_threshold(value: float, threshold: float) -> bool:
    return value >= threshold


def main() -> int:
    parser = argparse.ArgumentParser(description="Run benchmark-based release gate checks.")
    parser.add_argument("--raw-threshold", type=float, default=95.0, help="Minimum raw percent required")
    parser.add_argument("--weighted-threshold", type=float, default=97.0, help="Minimum weighted percent required")
    parser.add_argument(
        "--allow-case-failures",
        type=int,
        default=0,
        help="Allowed number of failing benchmark cases",
    )
    args = parser.parse_args()

    print("Running release gate benchmarks...")
    bench_rc = _run_benchmarks()

    latest = _read_latest_snapshot()
    previous = _read_previous_snapshot()

    raw_percent = float(latest.get("raw_percent", 0.0))
    weighted_percent = float(latest.get("weighted_percent", 0.0))
    cases_total = int(latest.get("cases_total", 0))
    cases_passed = int(latest.get("cases_passed", 0))
    cases_failed = max(0, cases_total - cases_passed)

    prev_raw = float(previous.get("raw_percent")) if previous else None
    prev_weighted = float(previous.get("weighted_percent")) if previous else None

    raw_ok = _meets_threshold(raw_percent, args.raw_threshold)
    weighted_ok = _meets_threshold(weighted_percent, args.weighted_threshold)
    cases_ok = cases_failed <= args.allow_case_failures

    print("\nRelease Gate Report")
    print("-------------------")
    print(f"Git SHA: {latest.get('git_sha', 'unknown')}")
    print(
        "Raw score: "
        f"{_pct(raw_percent)} "
        f"(threshold {_pct(args.raw_threshold)}) "
        f"{_delta(raw_percent, prev_raw)}"
    )
    print(
        "Weighted score: "
        f"{_pct(weighted_percent)} "
        f"(threshold {_pct(args.weighted_threshold)}) "
        f"{_delta(weighted_percent, prev_weighted)}"
    )
    print(
        "Case pass count: "
        f"{cases_passed}/{cases_total} "
        f"(allowed failures <= {args.allow_case_failures})"
    )

    failures = []
    if not raw_ok:
        failures.append("raw threshold not met")
    if not weighted_ok:
        failures.append("weighted threshold not met")
    if not cases_ok:
        failures.append("too many failing cases")

    if bench_rc != 0:
        failures.append("benchmark runner returned non-zero")

    if failures:
        print("\nGate decision: FAIL")
        print("Reasons:")
        for reason in failures:
            print(f"- {reason}")
        return 2

    print("\nGate decision: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
