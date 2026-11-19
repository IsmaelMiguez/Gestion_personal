from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, Inexact, localcontext
from unittest import TestCase

from payroll_engine.extra_payments import (
    InvalidExtraPaymentInput,
    calculate_extra_payment_reference,
)


class ExtraPaymentTests(TestCase):
    def test_fourteen_payments_include_base_and_calculated_seniority(self):
        result = calculate_extra_payment_reference(
            Decimal(2000), Decimal(735), 14, ROUND_HALF_UP
        )
        self.assertEqual(result.separate_payments_per_year, 2)
        self.assertEqual(result.amount_per_extra, Decimal(2735))
        self.assertEqual(result.annual_extra_amount, Decimal(5470))
        self.assertEqual(result.monthly_accrual, Decimal("455.83"))
        self.assertEqual(
            result.annual_accrual_rounding_difference, Decimal("0.04")
        )
        self.assertEqual(
            result.monthly_accrual * 12
            + result.annual_accrual_rounding_difference,
            result.annual_extra_amount,
        )

    def test_twelve_payments_do_not_duplicate_amounts_already_distributed(
        self,
    ):
        result = calculate_extra_payment_reference(
            Decimal("2333.33"), Decimal("816.67"), 12, ROUND_HALF_UP
        )
        self.assertEqual(result.separate_payments_per_year, 0)
        for amount in (
            result.amount_per_extra,
            result.annual_extra_amount,
            result.monthly_accrual,
            result.annual_accrual_rounding_difference,
        ):
            self.assertEqual(amount, Decimal(0))

    def test_invalid_inputs_are_rejected_with_the_responsible_field(self):
        for field in ("ordinary_base_salary", "monthly_seniority"):
            for value in (
                None,
                100.0,
                Decimal("NaN"),
                Decimal("Infinity"),
                Decimal("-1"),
                Decimal("0.001"),
                Decimal("10000000000"),
            ):
                with self.subTest(field=field, value=value):
                    values = {
                        "ordinary_base_salary": Decimal(2000),
                        "monthly_seniority": Decimal(0),
                    }
                    values[field] = value
                    with self.assertRaises(InvalidExtraPaymentInput) as raised:
                        calculate_extra_payment_reference(
                            **values,
                            payments_per_year=14,
                            rounding=ROUND_HALF_UP,
                        )
                    self.assertEqual(raised.exception.field, field)
        for count in (None, True, "14", 14.0, 13):
            with self.subTest(count=count):
                with self.assertRaises(InvalidExtraPaymentInput) as raised:
                    calculate_extra_payment_reference(
                        Decimal(2000), Decimal(0), count, ROUND_HALF_UP
                    )
                self.assertEqual(raised.exception.field, "payments_per_year")

    def test_rounding_is_explicit_and_independent_of_callers_context(self):
        with localcontext() as context:
            context.prec = 3
            context.traps[Inexact] = True
            result = calculate_extra_payment_reference(
                Decimal("2000.02"), Decimal(0), 14, ROUND_HALF_UP
            )
            self.assertEqual(result.monthly_accrual, Decimal("333.34"))
            other = calculate_extra_payment_reference(
                Decimal("2000.02"), Decimal(0), 14, ROUND_DOWN
            )
            self.assertEqual(other.monthly_accrual, Decimal("333.33"))
            self.assertEqual(context.prec, 3)
            self.assertTrue(context.traps[Inexact])

    def test_explicit_zero_is_a_valid_reference(self):
        result = calculate_extra_payment_reference(
            Decimal(0), Decimal(0), 14, ROUND_HALF_UP
        )
        self.assertEqual(result.separate_payments_per_year, 2)
        self.assertEqual(result.amount_per_extra, Decimal("0.00"))
