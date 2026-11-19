from dataclasses import replace
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, Inexact, localcontext
from unittest import TestCase

from payroll_engine.extra_payments import InvalidExtraPaymentInput
from payroll_engine.semester_extras import (
    ExtraAccrualMonth,
    calculate_semester_extra,
)


class SemesterExtraTests(TestCase):
    def setUp(self):
        self.months = tuple(
            ExtraAccrualMonth(
                date(2026, month, 1), Decimal(2000), Decimal(735), 14
            )
            for month in range(1, 7)
        )

    def test_stable_semester_rounds_total_once_and_exposes_difference(self):
        result = calculate_semester_extra(self.months, ROUND_HALF_UP)
        self.assertEqual(result.payment_month, date(2026, 7, 1))
        self.assertEqual(result.amount, Decimal("2735.00"))
        self.assertEqual(result.rounded_months_total, Decimal("2734.98"))
        self.assertEqual(result.rounding_difference, Decimal("0.02"))
        self.assertEqual(
            sum((line.accrued_amount for line in result.lines), Decimal(0))
            + result.rounding_difference,
            result.amount,
        )

    def test_salary_and_seniority_change_between_months(self):
        months = tuple(
            replace(
                item,
                base_salary=Decimal(2000 if index < 3 else 2400),
                seniority=Decimal(100 if index < 4 else 200),
            )
            for index, item in enumerate(self.months)
        )
        result = calculate_semester_extra(months, ROUND_HALF_UP)
        self.assertEqual(result.amount, Decimal("2333.33"))
        self.assertEqual(
            [line.reference_amount for line in result.lines],
            [Decimal(2100)] * 3 + [Decimal(2500)] + [Decimal(2600)] * 2,
        )

    def test_second_semester_twelve_payments_does_not_add_an_extra(self):
        months = tuple(
            replace(
                item,
                month=date(2026, item.month.month + 6, 1),
                payments_per_year=12,
            )
            for item in self.months
        )
        result = calculate_semester_extra(months, ROUND_HALF_UP)
        self.assertEqual(result.payment_month, date(2026, 12, 1))
        self.assertEqual(result.amount, Decimal("0.00"))
        self.assertTrue(all(line.accrued_amount == 0 for line in result.lines))

    def test_incomplete_unordered_or_invalid_calendar_is_rejected(self):
        for months in (
            None,
            (),
            self.months[:-1],
            list(self.months),
            tuple(reversed(self.months)),
            (self.months[0],) * 6,
            (
                replace(self.months[0], month=date(2026, 1, 2)),
                *self.months[1:],
            ),
            (
                replace(self.months[0], month=datetime(2026, 1, 1)),
                *self.months[1:],
            ),
            (None, *self.months[1:]),
        ):
            with self.subTest(months=months):
                with self.assertRaises(InvalidExtraPaymentInput):
                    calculate_semester_extra(months, ROUND_HALF_UP)

    def test_unknown_transition_and_invalid_money_preserve_errors(self):
        with self.assertRaises(InvalidExtraPaymentInput) as raised:
            calculate_semester_extra(
                (
                    replace(self.months[0], payments_per_year=12),
                    *self.months[1:],
                ),
                ROUND_HALF_UP,
            )
        self.assertEqual(raised.exception.field, "payments_per_year")
        with self.assertRaises(InvalidExtraPaymentInput) as raised:
            calculate_semester_extra(
                (replace(self.months[0], seniority=None), *self.months[1:]),
                ROUND_HALF_UP,
            )
        self.assertEqual(raised.exception.field, "months[0].monthly_seniority")
        self.assertIsInstance(
            raised.exception.__cause__, InvalidExtraPaymentInput
        )

    def test_callers_decimal_context_does_not_change_the_accrual(self):
        with localcontext() as context:
            context.prec = 3
            context.traps[Inexact] = True
            result = calculate_semester_extra(self.months, ROUND_HALF_UP)
            self.assertEqual(result.amount, Decimal("2735.00"))
            self.assertEqual(context.prec, 3)
            self.assertTrue(context.traps[Inexact])
