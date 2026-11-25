from datetime import date, datetime
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
    monthly_contribution_days,
    prorate_monthly_salary,
    standard_month_salary_days,
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


class MonthlySalaryProrationTests(TestCase):
    def test_uses_thirty_days_and_rounds_only_the_final_amount(self):
        for days, expected in ((0, "0.00"), (16, "1066.67"), (30, "2000.00")):
            with self.subTest(days=days):
                self.assertEqual(
                    prorate_monthly_salary(Decimal(2000), days, ROUND_HALF_UP),
                    Decimal(expected),
                )
        with localcontext() as context:
            context.prec = 3
            context.traps[Inexact] = True
            self.assertEqual(
                prorate_monthly_salary(Decimal(2000), 16, ROUND_DOWN),
                Decimal("1066.66"),
            )
            self.assertEqual(context.prec, 3)

    def test_rejects_invalid_days_and_money(self):
        for days in (None, True, -1, 31, 15.5, "15"):
            with self.subTest(days=days):
                with self.assertRaises(InvalidBaseSalaryInput) as raised:
                    prorate_monthly_salary(Decimal(2000), days, ROUND_HALF_UP)
                self.assertEqual(raised.exception.field, "salary_days")
        for amount in (
            None,
            2000.0,
            Decimal("NaN"),
            Decimal(-1),
            Decimal("1.001"),
        ):
            with self.subTest(amount=amount):
                with self.assertRaises(InvalidBaseSalaryInput):
                    prorate_monthly_salary(amount, 16, ROUND_HALF_UP)


class StandardSalaryMonthTests(TestCase):
    def test_february_and_other_months_use_the_same_thirty_day_calendar(self):
        cases = (
            (date(2026, 2, 1), None, date(2026, 2, 1), 30),
            (date(2026, 2, 15), None, date(2026, 2, 1), 16),
            (date(2028, 2, 15), None, date(2028, 2, 1), 16),
            (date(2026, 2, 15), date(2026, 3, 1), date(2026, 2, 1), 16),
            (date(2026, 1, 1), date(2026, 2, 16), date(2026, 2, 1), 15),
            (date(2026, 2, 15), date(2026, 2, 21), date(2026, 2, 1), 6),
            (date(2026, 2, 28), None, date(2026, 2, 1), 3),
            (date(2026, 1, 15), None, date(2026, 1, 1), 16),
            (date(2026, 1, 31), None, date(2026, 1, 1), 1),
            (date(2026, 4, 15), None, date(2026, 4, 1), 16),
            (date(2026, 12, 15), None, date(2026, 12, 1), 16),
        )
        for start, end, month, expected in cases:
            with self.subTest(start=start, end=end, month=month):
                self.assertEqual(
                    standard_month_salary_days(start, end, month), expected
                )

    def test_no_employment_in_the_month_has_no_salary_days(self):
        for start, end in (
            (date(2026, 3, 1), None),
            (date(2026, 1, 1), date(2026, 2, 1)),
        ):
            with self.subTest(start=start, end=end):
                self.assertEqual(
                    standard_month_salary_days(start, end, date(2026, 2, 1)), 0
                )

    def test_invalid_intervals_and_dates_are_rejected(self):
        for start, end, month in (
            (None, None, date(2026, 2, 1)),
            (date(2026, 2, 1), "2026-03-01", date(2026, 2, 1)),
            (date(2026, 2, 1), date(2026, 2, 1), date(2026, 2, 1)),
            (date(2026, 2, 1), date(2026, 1, 1), date(2026, 2, 1)),
            (date(2026, 2, 1), None, date(2026, 2, 2)),
            (datetime(2026, 2, 1), None, date(2026, 2, 1)),
        ):
            with self.subTest(start=start, end=end, month=month):
                with self.assertRaises(InvalidBaseSalaryInput):
                    standard_month_salary_days(start, end, month)


class MonthlyContributionDayTests(TestCase):
    def test_full_month_is_thirty_but_incomplete_month_uses_actual_dates(self):
        for start, end, month, expected in (
            (date(2026, 2, 1), None, date(2026, 2, 1), 30),
            (date(2026, 2, 15), None, date(2026, 2, 1), 14),
            (date(2028, 2, 15), None, date(2028, 2, 1), 15),
            (date(2026, 1, 15), None, date(2026, 1, 1), 17),
            (date(2026, 1, 1), date(2026, 2, 16), date(2026, 2, 1), 15),
            (date(2026, 1, 1), date(2026, 2, 1), date(2026, 2, 1), 0),
        ):
            with self.subTest(start=start, end=end, month=month):
                self.assertEqual(
                    monthly_contribution_days(start, end, month), expected
                )
