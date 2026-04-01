import unittest

from app.services.eob_analyzer import _infer_network_status_from_text, _parse_csv_claims


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
