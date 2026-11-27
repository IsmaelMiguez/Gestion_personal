from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal, localcontext
from unittest import TestCase

from payroll_engine.ncm import InvalidNcmInput, calculate_ncm_benefit


class NcmBenefitTests(TestCase):
    def test_partial_rest_is_relative_to_contract_without_scaling_base_twice(
        self,
    ):
        for contract, base, effective, benefit in (
            ("100", "100", "50", "1500.00"),
            ("50", "50", "25", "750.00"),
        ):
            with self.subTest(contract=contract):
                result = calculate_ncm_benefit(
                    Decimal(contract),
                    Decimal(50),
                    Decimal(base),
                    30,
                    ROUND_HALF_UP,
                )
                self.assertEqual(
                    result.effective_working_percentage, Decimal(effective)
                )
                self.assertEqual(result.gross_benefit, Decimal(benefit))
                self.assertEqual(result.equivalent_rest_days, Decimal(15))

    def test_full_rest_preserves_recognized_base_and_explicit_days(self):
        for days in (7, 28, 30, 31):
            with self.subTest(days=days):
                result = calculate_ncm_benefit(
                    Decimal(50),
                    Decimal(100),
                    Decimal("50.25"),
                    days,
                    ROUND_HALF_UP,
                )
                self.assertEqual(result.effective_working_percentage, 0)
                self.assertEqual(result.equivalent_rest_days, days)
                self.assertEqual(result.gross_benefit, Decimal("50.25") * days)

    def test_total_is_rounded_once_with_explicit_rounding(self):
        for rounding, expected in (
            (ROUND_HALF_UP, "116.67"),
            (ROUND_DOWN, "116.66"),
        ):
            with self.subTest(rounding=rounding):
                result = calculate_ncm_benefit(
                    Decimal(100),
                    Decimal(50),
                    Decimal("33.3333"),
                    7,
                    rounding,
                )
                self.assertEqual(result.gross_benefit, Decimal(expected))
                self.assertEqual(result.equivalent_rest_days, Decimal("3.5"))

    def test_calculation_is_independent_of_callers_decimal_context(self):
        with localcontext() as context:
            context.prec = 3
            context.rounding = ROUND_UP
            result = calculate_ncm_benefit(
                Decimal("37.50"),
                Decimal("33.33"),
                Decimal("67.8912"),
                28,
                ROUND_HALF_UP,
            )
            self.assertEqual(
                result.effective_working_percentage, Decimal("25.00125")
            )
            self.assertEqual(result.gross_benefit, Decimal("633.59"))
            self.assertEqual(context.prec, 3)
            self.assertEqual(context.rounding, ROUND_UP)

    def test_invalid_inputs_identify_the_field(self):
        values = {
            "contracted_percentage": Decimal(100),
            "rest_percentage": Decimal(50),
            "recognized_daily_base": Decimal(100),
            "benefit_days": 30,
            "rounding": ROUND_HALF_UP,
        }
        cases = {
            "contracted_percentage": (
                Decimal(0),
                Decimal("100.01"),
                Decimal("50.001"),
            ),
            "rest_percentage": (
                Decimal(-1),
                Decimal(0),
                Decimal(101),
                Decimal("NaN"),
                Decimal("Infinity"),
                50.0,
                Decimal("1E100"),
            ),
            "recognized_daily_base": (
                Decimal(0),
                Decimal("NaN"),
                Decimal("Infinity"),
                Decimal("1.00001"),
                Decimal("1E100"),
                "100",
            ),
            "benefit_days": (0, 32, -1, True, Decimal(30)),
            "rounding": (None, "invalid"),
        }
        for field, invalid_values in cases.items():
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(InvalidNcmInput) as caught:
                        calculate_ncm_benefit(**{**values, field: value})
                    self.assertEqual(caught.exception.field, field)
