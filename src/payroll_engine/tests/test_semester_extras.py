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
                date(2026, month, 1), Decimal(2000), Decimal(735), 14, 30
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

    def test_partial_hire_and_termination_weight_references_by_days_over_180(
        self,
    ):
        references = tuple(
            replace(item, seniority=Decimal(100)) for item in self.months
        )
        for days, expected in (
            ((0, 16, 30, 30, 30, 30), "1586.67"),
            ((30, 15, 0, 0, 0, 0), "525.00"),
            ((0, 0, 0, 0, 0, 0), "0.00"),
        ):
            months = tuple(
                replace(
                    item,
                    salary_days=count,
                    base_salary=item.base_salary if count else Decimal(0),
                    seniority=item.seniority if count else Decimal(0),
                )
                for item, count in zip(references, days, strict=True)
            )
            with self.subTest(days=days):
                result = calculate_semester_extra(months, ROUND_HALF_UP)
                self.assertEqual(result.amount, Decimal(expected))
                self.assertEqual(
                    tuple(line.salary_days for line in result.lines), days
                )
                self.assertEqual(
                    result.rounded_months_total + result.rounding_difference,
                    result.amount,
                )
                twelve = tuple(
                    replace(item, payments_per_year=12) for item in months
                )
                self.assertEqual(
                    calculate_semester_extra(twelve, ROUND_HALF_UP).amount,
                    Decimal(0),
                )

    def test_partial_days_are_explicit_and_zero_weight_does_not_add_accrual(
        self,
    ):
        for days in (None, True, -1, 31, Decimal("16.5"), "16"):
            with self.subTest(days=days):
                with self.assertRaises(InvalidExtraPaymentInput) as raised:
                    calculate_semester_extra(
                        (
                            replace(self.months[0], salary_days=days),
                            *self.months[1:],
                        ),
                        ROUND_HALF_UP,
                    )
                self.assertEqual(
                    raised.exception.field, "months[0].salary_days"
                )
        result = calculate_semester_extra(
            (replace(self.months[0], salary_days=0), *self.months[1:]),
            ROUND_HALF_UP,
        )
        self.assertEqual(result.amount, Decimal("2279.17"))
        self.assertEqual(result.lines[0].accrued_amount, Decimal(0))

    def test_multiple_references_in_one_month_use_their_own_weights(self):
        first = replace(
            self.months[0],
            base_salary=Decimal(2000),
            seniority=Decimal(0),
            salary_days=15,
        )
        second = replace(first, base_salary=Decimal(3000))
        later = tuple(
            replace(item, base_salary=Decimal(3000), seniority=Decimal(0))
            for item in self.months[1:]
        )
        result = calculate_semester_extra(
            (first, second, *later), ROUND_HALF_UP
        )
        self.assertEqual(result.amount, Decimal("2916.67"))
        self.assertEqual(len(result.lines), 7)
        self.assertEqual(result.lines[0].accrued_amount, Decimal("166.67"))
        self.assertEqual(result.lines[1].accrued_amount, Decimal("250.00"))
        with self.assertRaises(InvalidExtraPaymentInput):
            calculate_semester_extra(
                (replace(first, salary_days=16), second, *later), ROUND_HALF_UP
            )
