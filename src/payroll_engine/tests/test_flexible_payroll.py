from decimal import ROUND_HALF_UP, Decimal, Inexact, localcontext
from unittest import TestCase

from payroll_engine.ordinary_payroll import (
    InvalidPayrollInput,
    calculate_flexible_payroll_2026,
)


class FlexiblePayrollTests(TestCase):
    def test_flexible_insurance_replaces_cash_and_recharges_tax(self):
        result = calculate_flexible_payroll_2026(
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
        )
        self.assertEqual(result.gross_amount, Decimal(2100))
        self.assertEqual(result.insurance_amount, Decimal(100))
        self.assertEqual(result.cash_gross_amount, Decimal(2000))
        self.assertEqual(result.taxable_gross_amount, Decimal(2050))
        self.assertEqual(result.common_contribution_base, Decimal(2450))
        self.assertEqual(result.employee_contributions, Decimal("159.26"))
        self.assertEqual(result.cash_withholding_amount, Decimal(300))
        self.assertEqual(result.payment_on_account_amount, Decimal("7.50"))
        self.assertEqual(result.withholding_amount, Decimal("307.50"))
        self.assertEqual(result.net_amount, Decimal("1533.24"))
        self.assertEqual(result.employer_cash_cost, Decimal("2887.68"))
        self.assertEqual(
            result.net_amount
            + result.insurance_amount
            + result.employee_contributions
            + result.withholding_amount,
            result.gross_amount,
        )

    def test_exempt_or_taxable_insurance_does_not_remove_it_from_social_security(
        self,
    ):
        for exempt, taxable, tax in ((100, 0, "300.00"), (0, 100, "315.00")):
            with self.subTest(exempt=exempt, taxable=taxable):
                result = calculate_flexible_payroll_2026(
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
                )
                self.assertEqual(
                    result.common_contribution_base, Decimal(2450)
                )
                self.assertEqual(result.withholding_amount, Decimal(tax))
                self.assertEqual(result.gross_amount, Decimal(2100))
                self.assertEqual(result.employer_cash_cost, Decimal("2887.68"))

    def test_cash_retention_and_payment_on_account_round_separately(self):
        result = calculate_flexible_payroll_2026(
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
        )
        self.assertEqual(result.cash_withholding_amount, Decimal("0.06"))
        self.assertEqual(result.payment_on_account_amount, Decimal("0.01"))
        self.assertEqual(result.withholding_amount, Decimal("0.07"))

    def test_invalid_premiums_and_insurance_exceeding_salary_are_rejected(
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
                        calculate_flexible_payroll_2026(
                            Decimal(28000),
                            14,
                            Decimal(100),
                            Decimal(4200),
                            **premiums,
                            contribution_group=5,
                            withholding_rate=Decimal(15),
                            occupational_risk_rate=Decimal("1.50"),
                            rounding=ROUND_HALF_UP,
                        )
                    self.assertEqual(raised.exception.field, field)
        with self.assertRaises(InvalidPayrollInput) as raised:
            calculate_flexible_payroll_2026(
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
            )
        self.assertEqual(raised.exception.field, "insurance_amount")

    def test_zero_insurance_and_decimal_context_keep_the_previous_result(self):
        with localcontext() as context:
            context.prec = 3
            context.traps[Inexact] = True
            result = calculate_flexible_payroll_2026(
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
            )
            self.assertEqual(result.net_amount, Decimal("2090.24"))
            self.assertEqual(result.cash_gross_amount, result.gross_amount)
            self.assertEqual(result.payment_on_account_amount, Decimal(0))
            self.assertEqual(context.prec, 3)
            self.assertTrue(context.traps[Inexact])
