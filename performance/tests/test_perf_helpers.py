import unittest

from performance.perf_helpers import (
    build_risk_analysis_payload,
    extract_access_token,
    parse_bool,
    parse_csv_ids,
)


class PerformanceHelperTests(unittest.TestCase):
    def test_boolean_parsing(self):
        self.assertTrue(parse_bool("TRUE"))
        self.assertTrue(parse_bool("yes"))
        self.assertFalse(parse_bool("false"))
        self.assertTrue(parse_bool(None, default=True))

    def test_id_list_parsing(self):
        self.assertEqual(parse_csv_ids(" a, ,b,c "), ["a", "b", "c"])
        self.assertEqual(parse_csv_ids(None), [])

    def test_token_extraction(self):
        self.assertEqual(
            extract_access_token({"data": {"access_token": "token-value"}}),
            "token-value",
        )
        self.assertIsNone(extract_access_token({"data": {}}))
        self.assertIsNone(extract_access_token(None))

    def test_risk_payload_is_valid_shape(self):
        payload = build_risk_analysis_payload("customer-id")
        self.assertEqual(payload["customer_id"], "customer-id")
        self.assertEqual(len(payload["transactions"]), 1)
        item = payload["transactions"][0]
        self.assertEqual(item["currency"], "USD")
        self.assertTrue(item["occurred_at"].endswith("+00:00"))
        self.assertEqual(payload["historical_transactions"], [])
        self.assertNotEqual(item["transaction_id"], "")


if __name__ == "__main__":
    unittest.main()
