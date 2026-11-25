from decimal import ROUND_HALF_UP, Decimal, Inexact, localcontext
from unittest import TestCase

from payroll_engine.ordinary_payroll import (
    InvalidPayrollInput,
    calculate_ordinary_payroll_with_insurance_deductions_2026,
)


class InsuranceDeductionPayrollTests(TestCase):
    def test_insurance_is_deducted_after_payroll_tax_and_contributions(self):
        result = calculate_ordinary_payroll_with_insurance_deductions_2026(
            Decimal(28000),
            14,
            Decimal(100),
            Decimal(4200),
            Decimal(50),
            Decimal(50),
            5,
            Decimal(15),
            Decimal("1.50"),
            ROUND_HALF_UP,
            fixed_supplement=Decimal(0),
        )
        self.assertEqual(result.gross_amount, Decimal(2100))
        self.assertEqual(result.insurance_amount, Decimal(100))
        self.assertEqual(result.cash_gross_amount, Decimal(2100))
        self.assertEqual(result.taxable_gross_amount, Decimal(2100))
        self.assertEqual(result.common_contribution_base, Decimal(2450))
        self.assertEqual(result.employee_contributions, Decimal("159.26"))
        self.assertEqual(result.cash_withholding_amount, Decimal(315))
        self.assertEqual(result.net_before_insurance, Decimal("1625.74"))
        self.assertEqual(result.withholding_amount, Decimal("315.00"))
        self.assertEqual(result.net_amount, Decimal("1525.74"))
        self.assertEqual(result.employer_cash_cost, Decimal("2887.68"))
        self.assertEqual(
            result.net_amount
            + result.insurance_amount
            + result.employee_contributions
            + result.withholding_amount,
            result.gross_amount,
        )

    def test_legacy_exempt_taxable_split_changes_neither_tax_nor_social_security(
        self,
    ):
        for exempt, taxable, tax in ((100, 0, "315.00"), (0, 100, "315.00")):
            with self.subTest(exempt=exempt, taxable=taxable):
                result = (
                    calculate_ordinary_payroll_with_insurance_deductions_2026(
                        Decimal(28000),
                        14,
                        Decimal(100),
                        Decimal(4200),
                        Decimal(exempt),
                        Decimal(taxable),
                        5,
                        Decimal(15),
                        Decimal("1.50"),
                        ROUND_HALF_UP,
                        fixed_supplement=Decimal(0),
                    )
                )
                self.assertEqual(
                    result.common_contribution_base, Decimal(2450)
                )
                self.assertEqual(result.withholding_amount, Decimal(tax))
                self.assertEqual(result.gross_amount, Decimal(2100))
                self.assertEqual(result.employer_cash_cost, Decimal("2887.68"))

    def test_withholding_is_rounded_once_before_insurance_deduction(self):
        result = calculate_ordinary_payroll_with_insurance_deductions_2026(
            Decimal("14.40"),
            12,
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal("0.10"),
            5,
            Decimal(5),
            Decimal("1.50"),
            ROUND_HALF_UP,
            fixed_supplement=Decimal(0),
        )
        self.assertEqual(result.cash_withholding_amount, Decimal("0.06"))
        self.assertEqual(result.withholding_amount, Decimal("0.06"))

    def test_invalid_premiums_are_rejected_and_insufficient_net_is_not_hidden(
        self,
    ):
        for field in ("insurance_exempt", "insurance_taxable"):
            for value in (
                None,
                10.0,
                Decimal("NaN"),
                Decimal("Infinity"),
                Decimal(-1),
                Decimal("0.001"),
                Decimal("10000000000"),
            ):
                with self.subTest(field=field, value=value):
                    premiums = {
                        "insurance_exempt": Decimal(0),
                        "insurance_taxable": Decimal(0),
                    }
                    premiums[field] = value
                    with self.assertRaises(InvalidPayrollInput) as raised:
                        calculate_ordinary_payroll_with_insurance_deductions_2026(
                            Decimal(28000),
                            14,
                            Decimal(100),
                            Decimal(4200),
                            **premiums,
                            contribution_group=5,
                            withholding_rate=Decimal(15),
                            occupational_risk_rate=Decimal("1.50"),
                            rounding=ROUND_HALF_UP,
                            fixed_supplement=Decimal(0),
                        )
                    self.assertEqual(raised.exception.field, field)
        payroll = calculate_ordinary_payroll_with_insurance_deductions_2026(
            Decimal(28000),
            14,
            Decimal(0),
            Decimal(4000),
            Decimal(1500),
            Decimal(1000),
            5,
            Decimal(15),
            Decimal("1.50"),
            ROUND_HALF_UP,
            fixed_supplement=Decimal(0),
        )
        self.assertEqual(
            payroll.net_amount, payroll.net_before_insurance - Decimal(2500)
        )
        self.assertLess(payroll.net_amount, 0)

    def test_zero_insurance_and_decimal_context_keep_the_previous_result(self):
        with localcontext() as context:
            context.prec = 3
            context.traps[Inexact] = True
            result = calculate_ordinary_payroll_with_insurance_deductions_2026(
                Decimal(28000),
                14,
                Decimal(700),
                Decimal(5400),
                Decimal(0),
                Decimal(0),
                5,
                Decimal(15),
                Decimal("1.50"),
                ROUND_HALF_UP,
                fixed_supplement=Decimal(0),
            )
            self.assertEqual(result.net_amount, Decimal("2090.24"))
            self.assertEqual(result.cash_gross_amount, result.gross_amount)
            self.assertEqual(context.prec, 3)
            self.assertTrue(context.traps[Inexact])
