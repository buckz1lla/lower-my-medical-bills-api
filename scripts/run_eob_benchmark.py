import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.eob_analyzer import analyze_eob  # noqa: E402


def _in_range(value: float, minimum: float, maximum: float) -> bool:
    return minimum <= value <= maximum


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

    if "min_total_billed" in expect and "max_total_billed" in expect:
        if not _in_range(analysis.total_billed, expect["min_total_billed"], expect["max_total_billed"]):
            failures.append(
                f"total_billed={analysis.total_billed} not in [{expect['min_total_billed']}, {expect['max_total_billed']}]"
            )

    if "min_patient_responsibility" in expect and "max_patient_responsibility" in expect:
        if not _in_range(
            analysis.total_patient_responsibility,
            expect["min_patient_responsibility"],
            expect["max_patient_responsibility"],
        ):
            failures.append(
                "total_patient_responsibility="
                f"{analysis.total_patient_responsibility} not in "
                f"[{expect['min_patient_responsibility']}, {expect['max_patient_responsibility']}]"
            )

    if "min_claims" in expect and len(analysis.claims) < expect["min_claims"]:
        failures.append(f"claims={len(analysis.claims)} < min_claims={expect['min_claims']}")

    if "parser_source_in" in expect:
        parser_source = analysis.key_metrics.get("parser_source")
        if parser_source not in expect["parser_source_in"]:
            failures.append(
                f"parser_source={parser_source} not in {expect['parser_source_in']}"
            )

    if "min_out_of_network_opportunities" in expect:
        out_of_network_count = sum(1 for opp in analysis.savings_opportunities if opp.type == "out_of_network")
        if out_of_network_count < expect["min_out_of_network_opportunities"]:
            failures.append(
                "out_of_network opportunities="
                f"{out_of_network_count} < min_out_of_network_opportunities="
                f"{expect['min_out_of_network_opportunities']}"
            )

    return {
        "id": case_id,
        "description": case.get("description", ""),
        "passed": len(failures) == 0,
        "failures": failures,
        "observed": {
            "total_billed": analysis.total_billed,
            "total_patient_responsibility": analysis.total_patient_responsibility,
            "claims": len(analysis.claims),
            "opportunities": len(analysis.savings_opportunities),
            "parser_source": analysis.key_metrics.get("parser_source"),
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
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['id']}: {result['description']}")
        print(f"       observed={result['observed']}")
        if not result["passed"]:
            for failure in result["failures"]:
                print(f"       - {failure}")
        else:
            passed += 1

    print(f"\nSummary: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
