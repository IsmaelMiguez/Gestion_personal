from decimal import (
    ROUND_DOWN,
    ROUND_HALF_UP,
    ROUND_UP,
    Decimal,
    Inexact,
    localcontext,
)
from unittest import TestCase

from payroll_engine.base_salary import (
    InvalidBaseSalaryInput,
    base_salary_from_annual,
    base_salary_from_monthly,
)


class BaseSalaryTests(TestCase):
    def test_annual_base_salary_is_preserved_for_twelve_and_fourteen_payments(
        self,
    ):
        annual = Decimal("28000.00")
        for count, payment, extra_count in (
            (12, Decimal("2333.33"), 0),
            (14, Decimal("2000.00"), 2),
        ):
            with self.subTest(payments=count):
                result = base_salary_from_annual(annual, count, ROUND_HALF_UP)
                self.assertEqual(result.annual_amount, annual)
                self.assertEqual(result.ordinary_payment_amount, payment)
                self.assertEqual(result.extra_payments_per_year, extra_count)
                self.assertEqual(
                    payment * 12
                    + result.extra_payment_amount * extra_count
                    + result.annual_rounding_difference,
                    annual,
                )
        self.assertEqual(
            base_salary_from_annual(
                annual, 12, ROUND_HALF_UP
            ).extra_payment_amount,
            Decimal("0.00"),
        )

    def test_monthly_amount_is_per_payment_and_excludes_other_concepts(self):
        for count in (12, 14):
            with self.subTest(payments=count):
                result = base_salary_from_monthly(
                    Decimal("2000.01"), count, ROUND_HALF_UP
                )
                self.assertEqual(
                    result.annual_amount, Decimal("2000.01") * count
                )
                self.assertEqual(
                    result.ordinary_payment_amount, Decimal("2000.01")
                )
                self.assertEqual(result.annual_rounding_difference, Decimal(0))

    def test_rounding_difference_is_explicit_instead_of_changing_annual_salary(
        self,
    ):
        result = base_salary_from_annual(Decimal("10000"), 14, ROUND_HALF_UP)
        self.assertEqual(result.ordinary_payment_amount, Decimal("714.29"))
        self.assertEqual(result.annual_rounding_difference, Decimal("-0.06"))
        other_policy = base_salary_from_annual(
            Decimal("10000"), 14, ROUND_DOWN
        )
        self.assertEqual(
            other_policy.ordinary_payment_amount, Decimal("714.28")
        )
        self.assertEqual(
            other_policy.annual_rounding_difference, Decimal("0.08")
        )

    def test_calculation_does_not_use_or_change_callers_decimal_context(self):
        with localcontext() as context:
            context.prec = 3
            context.rounding = ROUND_UP
            context.traps[Inexact] = True
            result = base_salary_from_annual(
                Decimal("10000"), 14, ROUND_HALF_UP
            )
            self.assertEqual(result.ordinary_payment_amount, Decimal("714.29"))
            self.assertEqual(context.prec, 3)
            self.assertEqual(context.rounding, ROUND_UP)
            self.assertTrue(context.traps[Inexact])

    def test_invalid_amounts_are_rejected_without_float_conversion(self):
        for amount in (
            None,
            "2000.00",
            2000.01,
            Decimal("NaN"),
            Decimal("sNaN"),
            Decimal("Infinity"),
            Decimal("-0.01"),
            Decimal("1.001"),
            Decimal("10000000000"),
        ):
            for calculator in (
                base_salary_from_annual,
                base_salary_from_monthly,
            ):
                with self.subTest(
                    amount=amount, calculator=calculator.__name__
                ):
                    with self.assertRaises(InvalidBaseSalaryInput) as raised:
                        calculator(amount, 14, ROUND_HALF_UP)
                    self.assertEqual(raised.exception.field, "amount")

    def test_payment_count_requires_an_explicit_supported_integer(self):
        for count in (None, True, "14", 14.0, 0, 13, 15):
            with self.subTest(payments=count):
                with self.assertRaises(InvalidBaseSalaryInput) as raised:
                    base_salary_from_annual(
                        Decimal("28000"), count, ROUND_HALF_UP
                    )
                self.assertEqual(raised.exception.field, "payments_per_year")

    def test_missing_rounding_mode_does_not_use_an_implicit_policy(self):
        with self.assertRaises(InvalidBaseSalaryInput) as raised:
            base_salary_from_annual(Decimal("28000"), 14, None)
        self.assertEqual(raised.exception.field, "rounding")

    def test_unknown_rounding_mode_preserves_original_error(self):
        with self.assertRaises(InvalidBaseSalaryInput) as raised:
            base_salary_from_annual(Decimal("28000"), 14, "UNKNOWN")
        self.assertEqual(raised.exception.field, "rounding")
        self.assertIsNotNone(raised.exception.__cause__)

    def test_zero_salary_is_an_explicit_value(self):
        result = base_salary_from_annual(Decimal(0), 14, ROUND_HALF_UP)
        self.assertEqual(result.annual_amount, Decimal("0.00"))
        self.assertEqual(result.ordinary_payment_amount, Decimal("0.00"))
        self.assertEqual(result.annual_rounding_difference, Decimal("0.00"))
