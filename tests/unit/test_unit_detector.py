import unittest
from decimal import Decimal

from cse_financial_etl.domain.enums import MetricType, UnitScope
from cse_financial_etl.domain.models import UnitCandidate
from cse_financial_etl.extraction.unit_detector import (
    UnitConflictError,
    UnitNotDetectedError,
    compose_unit_text,
    detect_candidates,
    resolve_unit,
)
from cse_financial_etl.transformation.normalizer import normalize_value


class UnitDetectorTests(unittest.TestCase):
    def test_unit_variants(self) -> None:
        cases = [
            ("Rs.", "LKR", 1),
            ("Rs.' 000", "LKR", 1_000),
            ("Rs.’ 000", "LKR", 1_000),
            ("Rs.'000", "LKR", 1_000),
            ("Rs. '000s", "LKR", 1_000),
            ("all amounts in Sri Lankan Rupees", "LKR", 1),
            ("LKR Mn", "LKR", 1_000_000),
            ("Rs. Bn", "LKR", 1_000_000_000),
            ("USD '000", "USD", 1_000),
            ("Rs. 000", "LKR", 1_000),
            ("(Rs. Mn)", "LKR", 1_000_000),
            ("in Rs. thousands", "LKR", 1_000),
        ]
        for text, currency, scale in cases:
            with self.subTest(text=text):
                unit = resolve_unit(detect_candidates(text, scope=UnitScope.STATEMENT))
                self.assertEqual((unit.currency, unit.scale_factor), (currency, scale))

    def test_same_page_explicit_scale_outranks_bare_currency(self) -> None:
        candidates = [
            UnitCandidate("Rs.", "LKR", 1, UnitScope.STATEMENT, page=15, distance=0.01),
            UnitCandidate("Rs '000s", "LKR", 1_000, UnitScope.STATEMENT, page=15, distance=0.4),
        ]
        self.assertEqual(resolve_unit(candidates).scale_factor, 1_000)

    def test_composed_split_rs_and_thousands(self) -> None:
        text = compose_unit_text("Rs.", "'000")
        unit = resolve_unit(detect_candidates(text, scope=UnitScope.STATEMENT))
        self.assertEqual(unit.scale_factor, 1_000)

    def test_plain_amount_is_not_thousands_scale(self) -> None:
        candidates = detect_candidates("Rs.1,000.00", scope=UnitScope.STATEMENT)
        self.assertFalse(any(unit.scale_factor == 1_000 for unit in candidates))

    def test_closest_scope_wins(self) -> None:
        candidates = [
            UnitCandidate("Rs.'000", "LKR", 1_000, UnitScope.STATEMENT, distance=0),
            UnitCandidate("Rs.", "LKR", 1, UnitScope.ROW, distance=5),
        ]
        self.assertEqual(resolve_unit(candidates).scale_factor, 1)

    def test_yaml_sri_lankan_rupees_is_scale_one(self) -> None:
        from pathlib import Path

        from cse_financial_etl.config import load_unit_pattern_config
        from cse_financial_etl.extraction.unit_detector import configure_unit_patterns

        root = Path(__file__).resolve().parents[2]
        configure_unit_patterns(load_unit_pattern_config(root))
        unit = resolve_unit(
            detect_candidates("all amounts in Sri Lankan Rupees", scope=UnitScope.STATEMENT)
        )
        self.assertEqual((unit.currency, unit.scale_factor), ("LKR", 1))
        for text, scale in (
            ("Rs. 000", 1_000),
            ("(Rs. Mn)", 1_000_000),
            ("in Rs. thousands", 1_000),
        ):
            with self.subTest(yaml_text=text):
                resolved = resolve_unit(detect_candidates(text, scope=UnitScope.STATEMENT))
                self.assertEqual(resolved.scale_factor, scale)

    def test_equal_priority_conflict_fails_closed(self) -> None:
        candidates = [
            UnitCandidate("Rs.'000", "LKR", 1_000, UnitScope.TABLE, distance=0),
            UnitCandidate("Rs. Mn", "LKR", 1_000_000, UnitScope.TABLE, distance=0),
        ]
        with self.assertRaisesRegex(UnitConflictError, "UNIT_CONFLICT"):
            resolve_unit(candidates)

    def test_missing_unit_fails_closed(self) -> None:
        with self.assertRaisesRegex(UnitNotDetectedError, "UNIT_NOT_DETECTED"):
            resolve_unit([])

    def test_absolute_metric_is_scaled(self) -> None:
        candidates = detect_candidates("Rs.'000", scope=UnitScope.TABLE)
        result = normalize_value(Decimal("16621006"), MetricType.MONETARY_ABSOLUTE, candidates)
        self.assertEqual(result.normalized_value, Decimal("16621006000"))

    def test_per_share_does_not_inherit_statement_scale(self) -> None:
        candidates = detect_candidates("Rs.'000", scope=UnitScope.STATEMENT)
        result = normalize_value(Decimal("10.06"), MetricType.MONETARY_PER_SHARE, candidates)
        self.assertEqual(result.normalized_value, Decimal("10.06"))
        self.assertEqual(result.scale_factor, 1)

    def test_local_per_share_unit_can_override(self) -> None:
        candidates = [
            UnitCandidate("Rs.'000", "LKR", 1_000, UnitScope.STATEMENT),
            UnitCandidate("Rs.", "LKR", 1, UnitScope.ROW),
        ]
        result = normalize_value(Decimal("10.06"), MetricType.MONETARY_PER_SHARE, candidates)
        self.assertEqual(result.normalized_value, Decimal("10.06"))
        self.assertEqual(result.currency, "LKR")


if __name__ == "__main__":
    unittest.main()
