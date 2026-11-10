from datetime import date, datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, Inexact, localcontext
from unittest import TestCase

from payroll_engine.seniority import (
    InvalidSeniorityInput,
    UnresolvedSeniorityPeriod,
    calculate_monthly_seniority,
    monthly_seniority_percentage,
)


class SeniorityTests(TestCase):
    def test_all_agreed_steps_and_caps(self):
        expected = (
            0,
            0,
            5,
            5,
            10,
            10,
            15,
            15,
            20,
            20,
            25,
            25,
            25,
            25,
            25,
            35,
            40,
            40,
            40,
            40,
            50,
            50,
            55,
            55,
            60,
            60,
            60,
        )
        for years, percentage in enumerate(expected):
            with self.subTest(years=years):
                self.assertEqual(
                    monthly_seniority_percentage(
                        date(2026 - years, 1, 1), date(2026, 1, 1)
                    ),
                    Decimal(percentage),
                )

    def test_amount_includes_all_four_insurances_without_fixed_supplement(
        self,
    ):
        result = calculate_monthly_seniority(
            date(2011, 1, 1),
            date(2026, 1, 1),
            Decimal("2000.00"),
            (Decimal(10), Decimal(20), Decimal(30), Decimal(40)),
            ROUND_HALF_UP,
        )
        self.assertEqual(result.percentage, Decimal(35))
        self.assertEqual(result.calculation_base, Decimal(2100))
        self.assertEqual(result.amount, Decimal(735))

    def test_rate_change_inside_month_is_pending_but_frozen_rate_is_stable(
        self,
    ):
        with self.assertRaises(UnresolvedSeniorityPeriod):
            monthly_seniority_percentage(date(2024, 1, 15), date(2026, 1, 1))
        self.assertEqual(
            monthly_seniority_percentage(date(2015, 1, 15), date(2026, 1, 1)),
            Decimal(25),
        )
        self.assertEqual(
            monthly_seniority_percentage(date(2024, 2, 1), date(2026, 1, 1)),
            Decimal(0),
        )
        self.assertEqual(
            monthly_seniority_percentage(date(2024, 2, 1), date(2026, 2, 1)),
            Decimal(5),
        )

    def test_leap_anniversary_needs_a_rule_if_it_changes_the_rate(self):
        with self.assertRaises(UnresolvedSeniorityPeriod):
            monthly_seniority_percentage(date(2024, 2, 29), date(2026, 2, 1))
        self.assertEqual(
            monthly_seniority_percentage(date(2024, 2, 29), date(2026, 3, 1)),
            Decimal(5),
        )

    def test_dates_and_missing_money_are_not_silently_replaced(self):
        for recognized, month in (
            (None, date(2026, 1, 1)),
            (date(2027, 1, 1), date(2026, 1, 1)),
            (date(2020, 1, 1), date(2026, 1, 2)),
            (date(2020, 1, 1), datetime(2026, 1, 1)),
        ):
            with self.subTest(recognized=recognized, month=month):
                with self.assertRaises(InvalidSeniorityInput):
                    monthly_seniority_percentage(recognized, month)
        for amount in (
            None,
            10.0,
            Decimal("NaN"),
            Decimal("-1"),
            Decimal("0.001"),
        ):
            with self.subTest(amount=amount):
                with self.assertRaises(InvalidSeniorityInput):
                    calculate_monthly_seniority(
                        date(2020, 1, 1),
                        date(2026, 1, 1),
                        Decimal(1000),
                        (amount, Decimal(0), Decimal(0), Decimal(0)),
                        ROUND_HALF_UP,
                    )
        with self.assertRaises(InvalidSeniorityInput):
            calculate_monthly_seniority(
                date(2020, 1, 1),
                date(2026, 1, 1),
                Decimal(1000),
                (),
                ROUND_HALF_UP,
            )

    def test_explicit_rounding_is_local_and_zero_is_valid(self):
        with localcontext() as context:
            context.prec = 3
            context.traps[Inexact] = True
            result = calculate_monthly_seniority(
                date(2024, 1, 1),
                date(2026, 1, 1),
                Decimal("1000.10"),
                (Decimal(0),) * 4,
                ROUND_HALF_UP,
            )
            self.assertEqual(result.amount, Decimal("50.01"))
            self.assertEqual(context.prec, 3)
            other = calculate_monthly_seniority(
                date(2024, 1, 1),
                date(2026, 1, 1),
                Decimal("1000.10"),
                (Decimal(0),) * 4,
                ROUND_DOWN,
            )
            self.assertEqual(other.amount, Decimal("50.00"))
        result = calculate_monthly_seniority(
            date(2026, 1, 1),
            date(2026, 1, 1),
            Decimal(0),
            (Decimal(0),) * 4,
            ROUND_HALF_UP,
        )
        self.assertEqual(result.amount, Decimal("0.00"))
