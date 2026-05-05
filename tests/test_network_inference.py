import unittest

from app.services.eob_analyzer import _infer_network_status_from_text, _parse_csv_claims, _parse_text_claim


class NetworkInferenceTests(unittest.TestCase):
    def test_infer_out_of_network_from_text(self):
        status, confidence, evidence, missing = _infer_network_status_from_text(
            "Provider: XYZ\nStatus: Out-of-Network\nAmount you owe $500.00"
        )
        self.assertEqual(status, "out_of_network")
        self.assertEqual(confidence, "high")
        self.assertTrue(evidence)
        self.assertEqual(missing, [])

    def test_infer_conflicting_markers_as_unknown(self):
        status, confidence, evidence, missing = _infer_network_status_from_text(
            "This page says in-network in one section and out-of-network in another section."
        )
        self.assertEqual(status, "unknown")
        self.assertEqual(confidence, "medium")
        self.assertTrue(evidence)
        self.assertTrue(missing)

    def test_csv_explicit_unknown_overrides_legacy_in_network_false(self):
        csv_text = (
            "claim_id,visit_date,provider_name,service_description,billed_amount,allowed_amount,"
            "patient_responsibility,insurance_paid,status,in_network,network_status\n"
            "CLM-CSV-UNKNOWN,2026-03-03,Ambiguous Clinic,Specialist Visit,900.00,300.00,"
            "300.00,0.00,paid,false,unknown\n"
        )

        claims = _parse_csv_claims(csv_text.encode("utf-8"))
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.network_status, "unknown")
        self.assertEqual(claim.network_confidence, "medium")
        self.assertIsNone(claim.in_network)

    def test_csv_explicit_out_of_network_overrides_legacy_in_network_true(self):
        csv_text = (
            "claim_id,visit_date,provider_name,service_description,billed_amount,allowed_amount,"
            "patient_responsibility,insurance_paid,status,in_network,network_status\n"
            "CLM-CSV-OON,2026-03-04,Out Clinic,Specialist Visit,900.00,300.00,"
            "300.00,0.00,paid,true,out_of_network\n"
        )

        claims = _parse_csv_claims(csv_text.encode("utf-8"))
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.network_status, "out_of_network")
        self.assertEqual(claim.network_confidence, "high")
        self.assertFalse(claim.in_network)


if __name__ == "__main__":
    unittest.main()


class TextParserAmountTests(unittest.TestCase):
    """
    Regression tests for _parse_text_claim amount extraction.
    Wide-column EOBs (e.g. 9-column hearing-aid tables) previously had their
    patient_responsibility truncated because the total-row window was too narrow.
    """

    # Minimal representation of the VIOLET hearing-aid EOB text.
    # The 'Total amount' row has 9 money columns; the last ($297.00) is patient responsibility.
    _VIOLET_EOB = (
        "Claim detail for VIOLET\n"
        "Provider: M TEMPLE\n"
        "Status: Out-of-network\n"
        "11/11/2025\n"
        "Services received\n"
        "HEARING AID 11/11/2025\n"
        "Billed $266.00 Amount saved $0.00 Plan allowed $53.20 "
        "Your plan paid $0.00 Applied to deductible $53.20 "
        "Copay $0.00 Coinsurance $0.00 Plan does not cover $212.80 "
        "Amount you owe $266.00\n"
        "HEARING AID 11/11/2025\n"
        "Billed $31.00 Amount saved $31.00 Plan allowed $0.00 "
        "Your plan paid $0.00 Applied to deductible $0.00 "
        "Copay $0.00 Coinsurance $0.00 Plan does not cover $0.00 "
        "Amount you owe $0.00\n"
        "HEARING AID 11/11/2025\n"
        "Billed $31.00 Amount saved $0.00 Plan allowed $0.00 "
        "Your plan paid $0.00 Applied to deductible $0.00 "
        "Copay $0.00 Coinsurance $0.00 Plan does not cover $31.00 "
        "Amount you owe $31.00\n"
        "Total amount $328.00 $31.00 $53.20 $0.00 $53.20 $0.00 $0.00 $243.80 $297.00\n"
        "Explanation of your claim processing codes\n"
        "1L – AN OUT-OF-NETWORK HEALTH CARE PROFESSIONAL OR FACILITY PROVIDED THESE SERVICES.\n"
        "HH – THIS SERVICE HAS BEEN DENIED. THE NUMBER OF UNITS BILLED IS MORE THAN THE MAXIMUM.\n"
        "4W – YOUR PLAN DOES NOT COVER CHARGES FOR HEARING AIDS. THEREFORE, NO BENEFITS ARE PAYABLE.\n"
        "IK – THE UNIT(S) FOR THIS SERVICE IS WITHIN THE TYPICAL FREQUENCY PER DAY.\n"
    )

    def test_patient_responsibility_wide_table(self):
        """$297.00 must be parsed as patient_responsibility, not $53.20."""
        claim = _parse_text_claim(self._VIOLET_EOB, "violet_eob.pdf", "test1234")
        self.assertIsNotNone(claim)
        self.assertAlmostEqual(claim.total_patient_responsibility, 297.00, places=2)

    def test_total_billed_wide_table(self):
        """$328.00 must be parsed as total_billed."""
        claim = _parse_text_claim(self._VIOLET_EOB, "violet_eob.pdf", "test1234")
        self.assertIsNotNone(claim)
        self.assertAlmostEqual(claim.total_billed, 328.00, places=2)

    def test_status_not_denied_from_glossary(self):
        """'denied' in the code glossary footer must not set status='denied' on the claim."""
        claim = _parse_text_claim(self._VIOLET_EOB, "violet_eob.pdf", "test1234")
        self.assertIsNotNone(claim)
        self.assertEqual(claim.line_items[0].status, "paid")

    def test_plan_exclusion_detected(self):
        """'no benefits are payable' phrase must set notes='plan_exclusion' on the line item."""
        claim = _parse_text_claim(self._VIOLET_EOB, "violet_eob.pdf", "test1234")
        self.assertIsNotNone(claim)
        self.assertEqual(claim.line_items[0].notes, "plan_exclusion")
