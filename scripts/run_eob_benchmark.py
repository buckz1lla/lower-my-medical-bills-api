import asyncio
from datetime import datetime, timezone
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.eob_analyzer import analyze_eob  # noqa: E402


def _in_range(value: float, minimum: float, maximum: float) -> bool:
    return minimum <= value <= maximum


def _safe_git_short_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        sha = (result.stdout or "").strip()
        return sha or "unknown"
    except Exception:
        return "unknown"


def _write_trend_outputs(
    results: list,
    raw_passed: int,
    raw_total: int,
    raw_percent: float,
    weighted_earned: float,
    weighted_possible: float,
    weighted_percent: float,
):
    history_dir = ROOT / "benchmarks" / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    record = {
        "timestamp_utc": now,
        "git_sha": _safe_git_short_sha(),
        "cases_total": len(results),
        "cases_passed": sum(1 for item in results if item.get("passed")),
        "checks_passed": raw_passed,
        "checks_total": raw_total,
        "raw_percent": round(raw_percent, 2),
        "weighted_earned": round(weighted_earned, 4),
        "weighted_possible": round(weighted_possible, 4),
        "weighted_percent": round(weighted_percent, 2),
        "cases": [
            {
                "id": item.get("id"),
                "passed": item.get("passed"),
                "weight": item.get("weight"),
                "checks_passed": item.get("checks_passed"),
                "checks_total": item.get("checks_total"),
                "quality_score": round(float(item.get("quality_score", 0.0)), 4),
            }
            for item in results
        ],
    }

    history_file = history_dir / "benchmark_trend.jsonl"
    latest_file = history_dir / "benchmark_latest.json"

    with history_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
        handle.write("\n")

    latest_file.write_text(json.dumps(record, indent=2), encoding="utf-8")

    return history_file, latest_file


async def _run_case(case_path: Path) -> dict:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case_id = case.get("id", case_path.stem)
    input_data = case["input"]
    expect = case["expect"]

    analysis = await analyze_eob(
        file_name=input_data.get("file_name", "benchmark.pdf"),
        content=input_data.get("text", "").encode("utf-8"),
        file_type=input_data.get("file_type", ".pdf"),
        analysis_id=f"bench-{case_id}",
    )

    failures = []
    checks_total = 0
    checks_passed = 0

    def evaluate_check(condition: bool, failure_message: str):
        nonlocal checks_total, checks_passed
        checks_total += 1
        if condition:
            checks_passed += 1
        else:
            failures.append(failure_message)

    parser_source = analysis.key_metrics.get("parser_source")
    opportunities_by_type = {}
    for opp in analysis.savings_opportunities:
        opportunities_by_type[opp.type] = opportunities_by_type.get(opp.type, 0) + 1

    if "min_total_billed" in expect and "max_total_billed" in expect:
        evaluate_check(
            _in_range(analysis.total_billed, expect["min_total_billed"], expect["max_total_billed"]),
            (
                f"total_billed={analysis.total_billed} not in [{expect['min_total_billed']}, {expect['max_total_billed']}]"
            ),
        )

    if "min_patient_responsibility" in expect and "max_patient_responsibility" in expect:
        evaluate_check(
            _in_range(
                analysis.total_patient_responsibility,
                expect["min_patient_responsibility"],
                expect["max_patient_responsibility"],
            ),
            (
                "total_patient_responsibility="
                f"{analysis.total_patient_responsibility} not in "
                f"[{expect['min_patient_responsibility']}, {expect['max_patient_responsibility']}]"
            ),
        )

    if "min_claims" in expect:
        evaluate_check(
            len(analysis.claims) >= expect["min_claims"],
            f"claims={len(analysis.claims)} < min_claims={expect['min_claims']}",
        )

    if "max_claims" in expect:
        evaluate_check(
            len(analysis.claims) <= expect["max_claims"],
            f"claims={len(analysis.claims)} > max_claims={expect['max_claims']}",
        )

    if "parser_source_in" in expect:
        evaluate_check(
            parser_source in expect["parser_source_in"],
            f"parser_source={parser_source} not in {expect['parser_source_in']}",
        )

    if "parser_source_equals" in expect:
        evaluate_check(
            parser_source == expect["parser_source_equals"],
            f"parser_source={parser_source} != {expect['parser_source_equals']}",
        )

    if "min_out_of_network_opportunities" in expect:
        out_of_network_count = opportunities_by_type.get("out_of_network", 0)
        evaluate_check(
            out_of_network_count >= expect["min_out_of_network_opportunities"],
            (
                "out_of_network opportunities="
                f"{out_of_network_count} < min_out_of_network_opportunities="
                f"{expect['min_out_of_network_opportunities']}"
            ),
        )

    if "min_opportunities_by_type" in expect:
        for opp_type, min_count in expect["min_opportunities_by_type"].items():
            observed_count = opportunities_by_type.get(opp_type, 0)
            evaluate_check(
                observed_count >= min_count,
                f"{opp_type} opportunities={observed_count} < min_required={min_count}",
            )

    if "max_opportunities_by_type" in expect:
        for opp_type, max_count in expect["max_opportunities_by_type"].items():
            observed_count = opportunities_by_type.get(opp_type, 0)
            evaluate_check(
                observed_count <= max_count,
                f"{opp_type} opportunities={observed_count} > max_allowed={max_count}",
            )

    if checks_total == 0:
        checks_total = 1
        checks_passed = 1

    weight = float(case.get("weight", 1.0))
    quality_score = checks_passed / checks_total

    return {
        "id": case_id,
        "description": case.get("description", ""),
        "passed": len(failures) == 0,
        "weight": weight,
        "checks_total": checks_total,
        "checks_passed": checks_passed,
        "quality_score": quality_score,
        "failures": failures,
        "observed": {
            "total_billed": analysis.total_billed,
            "total_patient_responsibility": analysis.total_patient_responsibility,
            "claims": len(analysis.claims),
            "opportunities": len(analysis.savings_opportunities),
            "opportunities_by_type": opportunities_by_type,
            "parser_source": parser_source,
            "analysis_mode": analysis.key_metrics.get("analysis_mode"),
        },
    }


async def main() -> int:
    cases_dir = ROOT / "benchmarks" / "cases"
    case_files = sorted(cases_dir.glob("*.json"))

    if not case_files:
        print("No benchmark cases found in benchmarks/cases")
        return 1

    print(f"Running {len(case_files)} benchmark case(s)...")
    results = [await _run_case(path) for path in case_files]

    passed = 0
    weighted_possible = 0.0
    weighted_earned = 0.0
    total_checks = 0
    total_checks_passed = 0

    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['id']}: {result['description']}")
        print(
            "       "
            f"score={result['checks_passed']}/{result['checks_total']} "
            f"weight={result['weight']}"
        )
        print(f"       observed={result['observed']}")
        if not result["passed"]:
            for failure in result["failures"]:
                print(f"       - {failure}")
        else:
            passed += 1

        weighted_possible += result["weight"]
        weighted_earned += result["weight"] * result["quality_score"]
        total_checks += result["checks_total"]
        total_checks_passed += result["checks_passed"]

    weighted_percent = (weighted_earned / weighted_possible * 100.0) if weighted_possible else 0.0
    raw_percent = (total_checks_passed / total_checks * 100.0) if total_checks else 0.0

    history_file, latest_file = _write_trend_outputs(
        results=results,
        raw_passed=total_checks_passed,
        raw_total=total_checks,
        raw_percent=raw_percent,
        weighted_earned=weighted_earned,
        weighted_possible=weighted_possible,
        weighted_percent=weighted_percent,
    )

    print(f"\nSummary: {passed}/{len(results)} passed")
    print(f"Raw check score: {total_checks_passed}/{total_checks} ({raw_percent:.1f}%)")
    print(f"Weighted quality score: {weighted_earned:.2f}/{weighted_possible:.2f} ({weighted_percent:.1f}%)")
    print(f"Trend history appended to: {history_file}")
    print(f"Latest benchmark snapshot: {latest_file}")
    return 0 if passed == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
