from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal
from unittest import TestCase

from payroll_engine.ordinary_payroll import (
    InvalidPayrollInput,
    calculate_ordinary_payroll_with_insurance_deductions_2026,
)
from payroll_engine.reconciliation import reconcile_ordinary_payroll


class FixedSupplementAndReconciliationTests(TestCase):
    def test_monthly_cash_supplement_affects_tax_and_contributions_not_extras(
        self,
    ):
        payroll = calculate_ordinary_payroll_with_insurance_deductions_2026(
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
            fixed_supplement=Decimal(200),
        )
        self.assertEqual(payroll.fixed_supplement_amount, Decimal(200))
        self.assertEqual(payroll.gross_amount, Decimal(2300))
        self.assertEqual(payroll.cash_gross_amount, Decimal(2300))
        self.assertEqual(payroll.extra_payment_accrual, Decimal(350))
        self.assertEqual(payroll.common_contribution_base, Decimal(2650))
        self.assertEqual(payroll.employee_contributions, Decimal("172.26"))
        self.assertEqual(payroll.withholding_amount, Decimal("345.00"))
        self.assertEqual(payroll.net_amount, Decimal("1682.74"))
        self.assertEqual(payroll.employer_cash_cost, Decimal("3151.98"))
        self.assertTrue(
            all(
                check.balanced
                for check in reconcile_ordinary_payroll(payroll, ROUND_HALF_UP)
            )
        )

    def test_controls_report_real_discrepancies_without_masking_them(self):
        payroll = calculate_ordinary_payroll_with_insurance_deductions_2026(
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
            fixed_supplement=Decimal(200),
        )
        altered = replace(
            payroll, net_amount=payroll.net_amount + Decimal("0.01")
        )
        checks = reconcile_ordinary_payroll(altered, ROUND_HALF_UP)
        failures = [check for check in checks if not check.balanced]
        self.assertEqual([check.label for check in failures], ["Líquido"])
        self.assertEqual(failures[0].difference, Decimal("-0.01"))

    def test_unknown_or_invalid_supplement_is_not_assumed_zero(self):
        for value in (
            None,
            10.0,
            Decimal("NaN"),
            Decimal("-1"),
            Decimal("0.001"),
            Decimal("10000000000"),
        ):
            with self.subTest(value=value):
                with self.assertRaises(InvalidPayrollInput) as raised:
                    calculate_ordinary_payroll_with_insurance_deductions_2026(
                        Decimal(28000),
                        14,
                        Decimal(100),
                        Decimal(4200),
                        Decimal(0),
                        Decimal(0),
                        5,
                        Decimal(15),
                        Decimal("1.50"),
                        ROUND_HALF_UP,
                        fixed_supplement=value,
                    )
                self.assertEqual(raised.exception.field, "fixed_supplement")
