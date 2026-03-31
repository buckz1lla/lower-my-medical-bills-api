"""
Confidence validation harness for EOB opportunity detection.

Run:
    python test_confidence_validation.py

This script evaluates current analyzer behavior against labeled cases and prints
accuracy, precision, recall, and F1.
"""

from __future__ import annotations

from datetime import date
from typing import List, Dict, Any

from app import schemas
from app.services.eob_analyzer import _identify_savings_opportunities


def make_line_item(
    service_description: str,
    billed_amount: float,
    status: str = "paid",
    service_date: date | None = None,
) -> schemas.LineItem:
    return schemas.LineItem(
        service_date=service_date,
        provider_name="Test Provider",
        service_description=service_description,
        billed_amount=billed_amount,
        allowed_amount=billed_amount,
        patient_responsibility=max(0.0, billed_amount * 0.2),
        insurance_paid=max(0.0, billed_amount * 0.8),
        status=status,
        reason_code=None,
        notes=None,
    )


def make_claim(
    claim_id: str,
    visit_date: date,
    in_network: bool | None,
    line_items: List[schemas.LineItem],
    provider_name: str = "Test Facility",
    network_status: str | None = None,
    network_confidence: str | None = None,
) -> schemas.ClaimGroup:
    total_billed = round(sum(item.billed_amount for item in line_items), 2)
    total_allowed = round(sum(item.allowed_amount for item in line_items), 2)
    total_patient = round(sum(item.patient_responsibility for item in line_items), 2)
    total_ins_paid = round(sum(item.insurance_paid for item in line_items), 2)

    resolved_network_status = network_status
    if resolved_network_status is None:
        if in_network is True:
            resolved_network_status = "in_network"
        elif in_network is False:
            resolved_network_status = "out_of_network"
        else:
            resolved_network_status = "unknown"

    resolved_network_confidence = network_confidence
    if resolved_network_confidence is None:
        resolved_network_confidence = "high" if resolved_network_status != "unknown" else "low"

    return schemas.ClaimGroup(
        claim_id=claim_id,
        visit_date=visit_date,
        provider_name=provider_name,
        provider_npi="0000000000",
        facility_name=provider_name,
        line_items=line_items,
        in_network=in_network,
        network_status=resolved_network_status,
        network_confidence=resolved_network_confidence,
        network_evidence=["validation_harness"],
        network_missing_data_points=[] if resolved_network_status != "unknown" else ["explicit payer network marker"],
        total_billed=total_billed,
        total_allowed=total_allowed,
        total_paid_by_insurance=total_ins_paid,
        total_patient_responsibility=total_patient,
    )


TEST_CASES: List[Dict[str, Any]] = [
    {
        "name": "Duplicate service same visit date",
        "expected_flag": True,
        "claims": [
            make_claim(
                claim_id="CLM-001",
                visit_date=date(2024, 1, 15),
                in_network=True,
                provider_name="Acme Hospital",
                line_items=[make_line_item("ER Visit", 500.0)],
            ),
            make_claim(
                claim_id="CLM-002",
                visit_date=date(2024, 1, 15),
                in_network=True,
                provider_name="Acme Hospital",
                line_items=[make_line_item("ER Visit", 500.0)],
            ),
        ],
        "notes": "Should trigger duplicate billing_error rule.",
    },
    {
        "name": "Out-of-network high responsibility",
        "expected_flag": True,
        "claims": [
            make_claim(
                claim_id="CLM-003",
                visit_date=date(2024, 2, 1),
                in_network=False,
                provider_name="OON Lab",
                network_status="out_of_network",
                network_confidence="high",
                line_items=[make_line_item("Lab Panel", 800.0)],
            )
        ],
        "notes": "Should trigger out_of_network rule.",
    },
    {
        "name": "Unknown network should not trigger OON",
        "expected_flag": False,
        "claims": [
            make_claim(
                claim_id="CLM-003B",
                visit_date=date(2024, 2, 2),
                in_network=None,
                provider_name="Unclear Network Lab",
                network_status="unknown",
                network_confidence="low",
                line_items=[make_line_item("Lab Panel", 850.0)],
            )
        ],
        "notes": "Safety guard should avoid out_of_network opportunity when network status is unknown.",
    },
    {
        "name": "Denied high-dollar line item",
        "expected_flag": True,
        "claims": [
            make_claim(
                claim_id="CLM-004",
                visit_date=date(2024, 2, 5),
                in_network=True,
                provider_name="Imaging Center",
                line_items=[make_line_item("MRI", 1200.0, status="denied")],
            )
        ],
        "notes": "Should trigger appeal rule.",
    },
    {
        "name": "Clean in-network routine claim",
        "expected_flag": False,
        "claims": [
            make_claim(
                claim_id="CLM-005",
                visit_date=date(2024, 2, 10),
                in_network=True,
                provider_name="Primary Care",
                line_items=[make_line_item("Preventive Visit", 100.0)],
            )
        ],
        "notes": "No rule should fire.",
    },
    {
        "name": "Different service descriptions same day",
        "expected_flag": False,
        "claims": [
            make_claim(
                claim_id="CLM-006",
                visit_date=date(2024, 2, 20),
                in_network=True,
                provider_name="City Clinic",
                line_items=[make_line_item("Office Visit", 250.0)],
            ),
            make_claim(
                claim_id="CLM-007",
                visit_date=date(2024, 2, 20),
                in_network=True,
                provider_name="City Clinic",
                line_items=[make_line_item("Lab Draw", 250.0)],
            ),
        ],
        "notes": "No duplicate because service descriptions differ.",
    },
    {
        "name": "Denied low-dollar line item",
        "expected_flag": False,
        "claims": [
            make_claim(
                claim_id="CLM-008",
                visit_date=date(2024, 3, 1),
                in_network=True,
                provider_name="Pharmacy",
                line_items=[make_line_item("Medication", 45.0, status="denied")],
            )
        ],
        "notes": "Denial amount <= 100 should not trigger appeal opportunity.",
    },
]


def classify_case(expected_flag: bool, opportunities_found: bool) -> str:
    if expected_flag and opportunities_found:
        return "TP"
    if not expected_flag and not opportunities_found:
        return "TN"
    if not expected_flag and opportunities_found:
        return "FP"
    return "FN"


def compute_metrics(tp: int, fp: int, fn: int, tn: int) -> Dict[str, float]:
    total = tp + fp + fn + tn
    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def run_validation() -> None:
    print("=" * 80)
    print("CONFIDENCE VALIDATION HARNESS")
    print("=" * 80)

    tp = fp = fn = tn = 0

    for index, case in enumerate(TEST_CASES, start=1):
        opportunities = _identify_savings_opportunities(case["claims"])
        fired = len(opportunities) > 0
        label = classify_case(case["expected_flag"], fired)

        if label == "TP":
            tp += 1
        elif label == "FP":
            fp += 1
        elif label == "FN":
            fn += 1
        else:
            tn += 1

        print(f"\n[{index}] {case['name']}")
        print(f"Expected flag: {case['expected_flag']} | Actual flag: {fired} | Class: {label}")
        print(f"Notes: {case['notes']}")

        if opportunities:
            print("Opportunities:")
            for opp in opportunities:
                print(
                    f"  - {opp.type} | claim={opp.claim_id} | "
                    f"confidence={opp.confidence_score:.2f} ({opp.confidence_level})"
                )

    metrics = compute_metrics(tp, fp, fn, tn)

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"TP: {tp} | FP: {fp} | FN: {fn} | TN: {tn}")
    print(f"Accuracy : {metrics['accuracy']:.2%}")
    print(f"Precision: {metrics['precision']:.2%}")
    print(f"Recall   : {metrics['recall']:.2%}")
    print(f"F1 Score : {metrics['f1']:.2%}")

    print("\nThreshold guidance:")
    print("- Target precision >= 85% (avoid false alarms)")
    print("- Target recall    >= 80% (catch most real issues)")


if __name__ == "__main__":
    run_validation()
