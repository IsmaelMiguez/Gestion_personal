from decimal import ROUND_HALF_UP, Decimal, Inexact, localcontext
from unittest import TestCase

from payroll_engine.ordinary_payroll import (
    InvalidPayrollInput,
    calculate_ordinary_payroll_with_seniority_2026,
)


class OrdinarySeniorityTests(TestCase):
    def test_complete_month_includes_seniority_but_pays_no_extra(self):
        result = calculate_ordinary_payroll_with_seniority_2026(
            Decimal(28000),
            14,
            Decimal(700),
            Decimal(5400),
            5,
            Decimal(15),
            Decimal("1.50"),
            ROUND_HALF_UP,
        )
        self.assertEqual(result.salary.ordinary_payment_amount, Decimal(2000))
        self.assertEqual(result.gross_amount, Decimal(2700))
        self.assertEqual(result.extra_payment_accrual, Decimal(450))
        self.assertEqual(result.common_contribution_base, Decimal(3150))
        self.assertEqual(result.professional_contribution_base, Decimal(3150))
        self.assertEqual(result.employee_contributions, Decimal("204.76"))
        self.assertEqual(result.employer_contributions, Decimal("1012.73"))
        self.assertEqual(result.withholding_amount, Decimal(405))
        self.assertEqual(result.net_amount, Decimal("2090.24"))
        self.assertEqual(result.employer_cash_cost, Decimal("3712.73"))
        self.assertEqual(
            result.net_amount
            + result.employee_contributions
            + result.withholding_amount,
            result.gross_amount,
        )

    def test_annual_estimate_is_independent_of_this_months_extra_reference(
        self,
    ):
        result = calculate_ordinary_payroll_with_seniority_2026(
            Decimal(28000),
            14,
            Decimal(700),
            Decimal(5940),
            5,
            Decimal(15),
            Decimal("1.50"),
            ROUND_HALF_UP,
        )
        self.assertEqual(result.extra_payment_accrual, Decimal(495))
        self.assertEqual(result.common_contribution_base, Decimal(3195))
        self.assertEqual(result.net_amount, Decimal("2087.32"))

    def test_twelve_payments_have_no_additional_proration(self):
        result = calculate_ordinary_payroll_with_seniority_2026(
            Decimal(24000),
            12,
            Decimal(700),
            Decimal(0),
            5,
            Decimal(15),
            Decimal("1.50"),
            ROUND_HALF_UP,
        )
        self.assertEqual(result.gross_amount, Decimal(2700))
        self.assertEqual(result.extra_payment_accrual, Decimal(0))
        self.assertEqual(result.net_amount, Decimal("2119.50"))
        with self.assertRaises(InvalidPayrollInput) as raised:
            calculate_ordinary_payroll_with_seniority_2026(
                Decimal(24000),
                12,
                Decimal(700),
                Decimal(5400),
                5,
                Decimal(15),
                Decimal("1.50"),
                ROUND_HALF_UP,
            )
        self.assertEqual(raised.exception.field, "estimated_annual_extras")

    def test_seniority_counts_towards_maximum_and_solidarity(self):
        result = calculate_ordinary_payroll_with_seniority_2026(
            Decimal(60000),
            12,
            Decimal(1000),
            Decimal(0),
            1,
            Decimal(20),
            Decimal("1.50"),
            ROUND_HALF_UP,
        )
        self.assertEqual(result.common_contribution_base, Decimal("5101.20"))
        self.assertEqual(
            tuple(line.base for line in result.contributions[-3:]),
            (Decimal("510.12"), Decimal("388.68"), Decimal("0.00")),
        )
        self.assertEqual(result.withholding_amount, Decimal(1200))

    def test_missing_or_invalid_amounts_are_never_defaulted(self):
        for field in ("monthly_seniority", "estimated_annual_extras"):
            for value in (
                None,
                700.0,
                Decimal("NaN"),
                Decimal("Infinity"),
                Decimal(-1),
                Decimal("0.001"),
                Decimal("10000000000"),
            ):
                with self.subTest(field=field, value=value):
                    values = {
                        "monthly_seniority": Decimal(700),
                        "estimated_annual_extras": Decimal(5400),
                    }
                    values[field] = value
                    with self.assertRaises(InvalidPayrollInput) as raised:
                        calculate_ordinary_payroll_with_seniority_2026(
                            Decimal(28000),
                            14,
                            **values,
                            contribution_group=5,
                            withholding_rate=Decimal(15),
                            occupational_risk_rate=Decimal("1.50"),
                            rounding=ROUND_HALF_UP,
                        )
                    self.assertEqual(raised.exception.field, field)

    def test_decimal_context_is_local_for_all_components(self):
        with localcontext() as context:
            context.prec = 3
            context.traps[Inexact] = True
            result = calculate_ordinary_payroll_with_seniority_2026(
                Decimal(28000),
                14,
                Decimal(700),
                Decimal(5400),
                5,
                Decimal(15),
                Decimal("1.50"),
                ROUND_HALF_UP,
            )
            self.assertEqual(result.net_amount, Decimal("2090.24"))
            self.assertEqual(context.prec, 3)
            self.assertTrue(context.traps[Inexact])
