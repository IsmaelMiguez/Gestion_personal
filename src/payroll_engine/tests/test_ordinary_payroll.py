from decimal import ROUND_HALF_UP, ROUND_UP, Decimal, Inexact, localcontext
from unittest import TestCase

from payroll_engine.ordinary_payroll import (
    InvalidPayrollInput,
    calculate_condition_change_contributions_2026,
    calculate_ordinary_payroll_2026,
    calculate_part_time_contributions_2026,
    calculate_period_contributions_2026,
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


class PeriodContributionTests(TestCase):
    def test_partial_year_extras_are_normalized_before_applying_contribution_days(
        self,
    ):
        with localcontext() as context:
            context.prec = 3
            context.traps[Inexact] = True
            result = calculate_period_contributions_2026(
                Decimal("1066.67"),
                Decimal("3511.11"),
                316,
                14,
                5,
                Decimal("1.50"),
                ROUND_HALF_UP,
            )
            self.assertEqual(result.extra_payment_accrual, Decimal("155.56"))
            self.assertEqual(
                result.common_contribution_base, Decimal("1222.23")
            )
            self.assertEqual(result.employee_contributions, Decimal("79.43"))
            self.assertEqual(context.prec, 3)
        march = calculate_period_contributions_2026(
            Decimal(2000),
            Decimal("3511.11"),
            316,
            30,
            5,
            Decimal("1.50"),
            ROUND_HALF_UP,
        )
        self.assertEqual(march.extra_payment_accrual, Decimal("333.33"))

    def test_period_limits_and_all_solidarity_bands_scale_to_contribution_days(
        self,
    ):
        result = calculate_period_contributions_2026(
            Decimal(4800),
            Decimal(15800),
            316,
            14,
            1,
            Decimal(1),
            ROUND_HALF_UP,
        )
        self.assertEqual(result.extra_payment_accrual, Decimal(700))
        self.assertEqual(result.uncapped_contribution_base, Decimal(5500))
        self.assertEqual(result.common_contribution_base, Decimal("2380.56"))
        self.assertEqual(
            tuple(line.base for line in result.contributions[-3:]),
            (Decimal("238.06"), Decimal("952.22"), Decimal("1929.16")),
        )
        low = calculate_period_contributions_2026(
            Decimal(100), Decimal(0), 360, 14, 1, Decimal(1), ROUND_HALF_UP
        )
        self.assertEqual(low.common_contribution_base, Decimal("928.34"))
        self.assertEqual(low.professional_contribution_base, Decimal("664.72"))
        for base in (
            Decimal("2380.56"),
            Decimal("2618.62"),
            Decimal("3570.84"),
        ):
            with self.subTest(base=base):
                edge = calculate_period_contributions_2026(
                    base, Decimal(0), 360, 14, 1, Decimal(1), ROUND_HALF_UP
                )
                self.assertEqual(
                    sum(line.base for line in edge.contributions[-3:]),
                    max(Decimal(0), base - Decimal("2380.56")),
                )

    def test_invalid_days_group_and_money_are_rejected(self):
        values = dict(
            gross_amount=Decimal(1000),
            estimated_annual_extras=Decimal(2000),
            annual_salary_days=360,
            contribution_days=15,
            contribution_group=5,
            occupational_risk_rate=Decimal(1),
            rounding=ROUND_HALF_UP,
        )
        for field, invalid_values in (
            ("annual_salary_days", (None, True, 0, 361)),
            ("contribution_days", (None, True, 0, 31)),
            ("contribution_group", (0, 8)),
            (
                "gross_amount",
                (1000.0, Decimal("NaN"), Decimal(-1), Decimal("1.001")),
            ),
            ("estimated_annual_extras", (None, Decimal("Infinity"))),
            ("occupational_risk_rate", (None, Decimal(101))),
        ):
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(InvalidPayrollInput) as raised:
                        calculate_period_contributions_2026(
                            **{**values, field: value}
                        )
                    self.assertEqual(raised.exception.field, field)


class PartTimeContributionTests(TestCase):
    def test_hourly_minima_use_real_hours_and_preserve_distinct_professional_base(
        self,
    ):
        with localcontext() as context:
            context.prec = 3
            context.traps[Inexact] = True
            result = calculate_part_time_contributions_2026(
                Decimal(500),
                Decimal(0),
                360,
                30,
                1,
                Decimal("1.50"),
                Decimal(80),
                ROUND_HALF_UP,
            )
            self.assertEqual(
                result.common_contribution_base, Decimal("958.40")
            )
            self.assertEqual(
                result.professional_contribution_base, Decimal("686.40")
            )
            self.assertEqual(result.employee_contributions, Decimal("57.81"))
            self.assertEqual(context.prec, 3)
        partial = calculate_part_time_contributions_2026(
            Decimal("533.33"),
            Decimal("1755.56"),
            316,
            14,
            5,
            Decimal("1.50"),
            Decimal(40),
            ROUND_HALF_UP,
        )
        self.assertEqual(partial.minimum_common_base, Decimal("343.20"))
        self.assertEqual(partial.extra_payment_accrual, Decimal("77.78"))
        self.assertEqual(partial.common_contribution_base, Decimal("611.11"))
        self.assertEqual(partial.employee_contributions, Decimal("39.72"))

    def test_maximum_and_solidarity_do_not_reduce_with_contract_percentage(
        self,
    ):
        result = calculate_part_time_contributions_2026(
            Decimal(6000),
            Decimal(12000),
            360,
            30,
            5,
            Decimal(1),
            Decimal(80),
            ROUND_HALF_UP,
        )
        self.assertEqual(result.uncapped_contribution_base, Decimal(7000))
        self.assertEqual(result.common_contribution_base, Decimal("5101.20"))
        self.assertEqual(
            tuple(line.base for line in result.contributions[-3:]),
            (Decimal("510.12"), Decimal("1388.68"), Decimal(0)),
        )

    def test_hours_must_be_explicit_finite_positive_decimals(self):
        for hours in (
            None,
            True,
            80.0,
            "80",
            Decimal("NaN"),
            Decimal("Infinity"),
            Decimal(0),
            Decimal(-1),
            Decimal(745),
            Decimal("1.001"),
        ):
            with self.subTest(hours=hours):
                with self.assertRaises(InvalidPayrollInput) as raised:
                    calculate_part_time_contributions_2026(
                        Decimal(1000),
                        Decimal(2000),
                        360,
                        30,
                        5,
                        Decimal(1),
                        hours,
                        ROUND_HALF_UP,
                    )
                self.assertEqual(raised.exception.field, "worked_hours")


class ConditionChangeContributionTests(TestCase):
    def test_segment_minimums_cannot_be_offset_by_higher_pay_in_the_next_segment(
        self,
    ):
        result = calculate_condition_change_contributions_2026(
            ((Decimal(50), 15), (Decimal(1500), 15)),
            Decimal(0),
            360,
            5,
            Decimal("1.50"),
            ROUND_HALF_UP,
        )
        self.assertEqual(result.uncapped_contribution_base, Decimal(1550))
        self.assertEqual(result.common_contribution_base, Decimal("2212.20"))
        self.assertEqual(result.employee_contributions, Decimal("143.79"))
        high = calculate_condition_change_contributions_2026(
            ((Decimal(5000), 15), (Decimal(3000), 15)),
            Decimal(0),
            360,
            5,
            Decimal("1.50"),
            ROUND_HALF_UP,
        )
        self.assertEqual(high.common_contribution_base, Decimal("5101.20"))
        self.assertEqual(
            tuple(line.base for line in high.contributions[-3:]),
            (Decimal("510.12"), Decimal("2040.48"), Decimal("348.20")),
        )

    def test_invalid_segment_days_and_zero_day_earnings_are_rejected(self):
        for segments in (
            (),
            ((Decimal(100), 15),),
            ((Decimal(100), True), (Decimal(100), 15)),
            ((Decimal(100), 0), (Decimal(100), 30)),
            ((Decimal(100), 16), (Decimal(100), 16)),
            ((None, 15), (Decimal(100), 15)),
        ):
            with self.subTest(segments=segments):
                with self.assertRaises(InvalidPayrollInput):
                    calculate_condition_change_contributions_2026(
                        segments, Decimal(0), 360, 5, Decimal(1), ROUND_HALF_UP
                    )
