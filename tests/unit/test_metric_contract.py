import unittest

from cse_financial_etl.domain.enums import MetricType, MissingReason, PeriodType


class MetricContractTests(unittest.TestCase):
    def test_domain_enums_use_stable_codes(self) -> None:
        self.assertEqual(MetricType.MONETARY_ABSOLUTE.value, "MONETARY_ABSOLUTE")
        self.assertEqual(PeriodType.AS_AT.value, "AS_AT")
        self.assertEqual(MissingReason.UNIT_NOT_DETECTED.value, "UNIT_NOT_DETECTED")


if __name__ == "__main__":
    unittest.main()
