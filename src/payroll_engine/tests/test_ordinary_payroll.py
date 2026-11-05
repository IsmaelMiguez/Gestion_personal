from decimal import ROUND_HALF_UP, ROUND_UP, Decimal, Inexact, localcontext
from unittest import TestCase

from payroll_engine.ordinary_payroll import (
    InvalidPayrollInput,
    calculate_ordinary_payroll_2026,
)


class OrdinaryPayrollTests(TestCase):
    def test_fourteen_payments_contribute_extras_without_paying_them(self):
        result = calculate_ordinary_payroll_2026(
            Decimal(28000), 14, 5, Decimal(15), Decimal("1.50"), ROUND_HALF_UP
        )
        self.assertEqual(result.salary.ordinary_payment_amount, Decimal(2000))
        self.assertEqual(result.extra_payment_accrual, Decimal("333.33"))
        self.assertEqual(result.common_contribution_base, Decimal("2333.33"))
        self.assertEqual(
            result.professional_contribution_base, Decimal("2333.33")
        )
        self.assertEqual(result.employee_contributions, Decimal("151.67"))
        self.assertEqual(result.employer_contributions, Decimal("750.17"))
        self.assertEqual(result.withholding_amount, Decimal(300))
        self.assertEqual(result.net_amount, Decimal("1548.33"))
        self.assertEqual(result.employer_cash_cost, Decimal("2750.17"))
        self.assertEqual(
            result.net_amount
            + result.employee_contributions
            + result.withholding_amount,
            result.salary.ordinary_payment_amount,
        )

    def test_twelve_payments_have_no_separate_extra_accrual(self):
        result = calculate_ordinary_payroll_2026(
            Decimal(30000), 12, 5, Decimal(10), Decimal(2), ROUND_HALF_UP
        )
        self.assertEqual(result.extra_payment_accrual, Decimal(0))
        self.assertEqual(result.uncapped_contribution_base, Decimal(2500))
        self.assertEqual(result.employee_contributions, Decimal("162.50"))
        self.assertEqual(result.net_amount, Decimal("2087.50"))

    def test_common_and_professional_minimum_bases_are_distinct(self):
        for group, common in (
            (1, "1989.30"),
            (2, "1649.70"),
            (3, "1435.20"),
            (7, "1424.40"),
        ):
            with self.subTest(group=group):
                result = calculate_ordinary_payroll_2026(
                    Decimal(12000),
                    12,
                    group,
                    Decimal(0),
                    Decimal(1),
                    ROUND_HALF_UP,
                )
                self.assertEqual(
                    result.common_contribution_base, Decimal(common)
                )
                self.assertEqual(
                    result.professional_contribution_base, Decimal("1424.40")
                )
                self.assertEqual(
                    result.salary.ordinary_payment_amount, Decimal(1000)
                )

    def test_solidarity_bands_apply_only_to_excess_not_capped_base(self):
        for monthly, expected in (
            ("5101.20", ("0.00", "0.00", "0.00")),
            ("5101.21", ("0.01", "0.00", "0.00")),
            ("5611.32", ("510.12", "0.00", "0.00")),
            ("5611.33", ("510.12", "0.01", "0.00")),
            ("7651.80", ("510.12", "2040.48", "0.00")),
            ("7651.81", ("510.12", "2040.48", "0.01")),
            ("10000.00", ("510.12", "2040.48", "2348.20")),
        ):
            with self.subTest(monthly=monthly):
                result = calculate_ordinary_payroll_2026(
                    Decimal(monthly) * 12,
                    12,
                    1,
                    Decimal(20),
                    Decimal(1),
                    ROUND_HALF_UP,
                )
                self.assertEqual(
                    result.common_contribution_base, Decimal("5101.20")
                )
                bands = result.contributions[-3:]
                self.assertEqual(
                    tuple(line.base for line in bands),
                    tuple(map(Decimal, expected)),
                )
                if monthly == "10000.00":
                    self.assertEqual(
                        tuple(line.employee_amount for line in bands),
                        (Decimal("0.97"), Decimal("4.29"), Decimal("5.64")),
                    )
                    self.assertEqual(
                        tuple(line.employer_amount for line in bands),
                        (Decimal("4.90"), Decimal("21.22"), Decimal("28.65")),
                    )

    def test_rounding_residual_remains_visible_without_inventing_a_payment(
        self,
    ):
        with localcontext() as context:
            context.prec = 3
            context.rounding = ROUND_UP
            context.traps[Inexact] = True
            result = calculate_ordinary_payroll_2026(
                Decimal(28001), 14, 5, Decimal(15), Decimal(1), ROUND_HALF_UP
            )
            self.assertEqual(
                result.salary.annual_rounding_difference, Decimal("0.02")
            )
            self.assertEqual(context.prec, 3)
            self.assertTrue(context.traps[Inexact])

    def test_rates_require_explicit_finite_percentages(self):
        for field in ("withholding_rate", "occupational_risk_rate"):
            for value in (
                None,
                "15",
                15.0,
                Decimal("NaN"),
                Decimal("Infinity"),
                Decimal("-0.01"),
                Decimal("100.01"),
                Decimal("1.001"),
            ):
                with self.subTest(field=field, value=value):
                    values = {
                        "withholding_rate": Decimal(15),
                        "occupational_risk_rate": Decimal(1),
                    }
                    values[field] = value
                    with self.assertRaises(InvalidPayrollInput) as raised:
                        calculate_ordinary_payroll_2026(
                            Decimal(28000),
                            14,
                            5,
                            **values,
                            rounding=ROUND_HALF_UP,
                        )
                    self.assertEqual(raised.exception.field, field)

    def test_daily_or_unknown_contribution_groups_are_rejected(self):
        for group in (None, True, "5", 5.0, 0, 8, 11):
            with self.subTest(group=group):
                with self.assertRaises(InvalidPayrollInput) as raised:
                    calculate_ordinary_payroll_2026(
                        Decimal(28000),
                        14,
                        group,
                        Decimal(15),
                        Decimal(1),
                        ROUND_HALF_UP,
                    )
                self.assertEqual(raised.exception.field, "contribution_group")
