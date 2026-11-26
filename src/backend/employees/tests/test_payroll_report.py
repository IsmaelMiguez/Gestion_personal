from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from ..api.serializers import EmploymentConditionSerializer
from ..forms import EmployeeRegistrationConditionForm
from ..models import (
    Company,
    Employee,
    EmploymentCondition,
    EmploymentRelationship,
)
from ..payroll_columns import COLUMNS
from ..payroll_report import report_row
from ..payroll_semester import annual_extra_estimate


class PayrollReportTests(TestCase):
    def test_positive_supplement_is_paid_monthly_without_increasing_seniority_or_extras(
        self,
    ):
        self.relationship.seniority_date = date(2023, 12, 1)
        self.relationship.save()
        self.condition.fixed_supplement_cents = 20000
        self.condition.save()
        response = self.client.post(self.url, self.values)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertEqual(cells["P"]["value"], Decimal(100))
        self.assertEqual(cells["I"]["value"], Decimal(350))
        self.assertEqual(cells["W"]["value"], Decimal(2300))
        self.assertEqual(cells["X"]["value"], Decimal(350))
        self.assertTrue(cells["CA"]["available"])
        self.assertEqual(cells["CJ"]["value"], "OK")
        self.assertEqual(
            response.context["semester_extras"][0]["result"].amount,
            Decimal(2100),
        )
        response = self.client.post(
            self.url,
            {**self.values, "cell": cells["CJ"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "Controles aritméticos")
        self.assertContains(response, "Composición del bruto")
        self.assertTrue(
            all(
                check.balanced
                for check in response.context["detail"]["checks"]
            )
        )

    def test_insurance_deductions_preserve_gross_tax_and_explain_transfer(
        self,
    ):
        self.relationship.seniority_date = date(2023, 12, 1)
        self.relationship.save()
        self.condition.employee_insurance_exempt_cents = 4000
        self.condition.employee_insurance_taxable_cents = 2000
        self.condition.family_insurance_exempt_cents = 1000
        self.condition.family_insurance_taxable_cents = 3000
        self.condition.save()
        response = self.client.post(self.url, self.values)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        for code, value in (
            ("P", "105.00"),
            ("W", "2105.00"),
            ("X", "350.83"),
            ("AC", "2455.83"),
            ("AE", "2105.00"),
            ("BV", "159.63"),
            ("BZ", "315.75"),
            ("CA", "1529.62"),
            ("CB", "2894.55"),
        ):
            with self.subTest(code=code):
                self.assertTrue(cells[code]["available"])
                self.assertEqual(cells[code]["value"], Decimal(value))
        response = self.client.post(
            self.url,
            {**self.values, "cell": cells["BZ"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        payment = response.context["detail"]["payment_breakdown"]
        self.assertEqual(payment.cash_gross_amount, Decimal(2105))
        self.assertEqual(payment.cash_withholding_amount, Decimal("315.75"))
        self.assertEqual(payment.net_before_insurance, Decimal("1629.62"))
        self.assertContains(response, "Líquido antes de seguros")
        self.assertContains(response, "Del bruto al ingreso bancario")
        self.assertNotContains(response, "<!doctype html>")
        self.condition.refresh_from_db()
        self.assertEqual(self.condition.salary_amount_cents, 2800000)
        self.assertEqual(self.condition.family_insurance_taxable_cents, 3000)

    def test_insurance_exceeding_net_preserves_visible_negative_balance(
        self,
    ):
        self.condition.employee_insurance_exempt_cents = 300000
        self.condition.save()
        response = self.client.post(self.url, self.values)
        cell = next(
            cell
            for cell in response.context["rows"][0]["cells"]
            if cell["code"] == "CA"
        )
        self.assertTrue(cell["available"])
        self.assertLess(cell["value"], 0)

    def test_table_explains_actual_missing_fields_and_unsupported_contract(
        self,
    ):
        self.condition.contract_type = "General"
        for name in self.condition.money_fields[1:]:
            setattr(self.condition, name, None)
        self.condition.save()
        response = self.client.post(self.url, self.values)
        self.assertContains(response, "Nómina pendiente: revisar datos")
        self.assertContains(response, "Modalidad contractual «General»")
        self.assertContains(response, "seguro trabajador exento")
        self.assertContains(response, "seguro familia sujeto")
        self.assertContains(response, "complemento fijo")
        self.assertContains(response, "vacío no significa cero")
        self.condition.refresh_from_db()
        self.assertIsNone(self.condition.employee_insurance_exempt_cents)
        self.assertIsNone(self.condition.fixed_supplement_cents)
        self.assertEqual(self.condition.contract_type, "General")

    def test_full_ordinary_payroll_with_seniority_and_annual_estimate_detail(
        self,
    ):
        self.relationship.seniority_date = date(2010, 12, 1)
        self.relationship.save()
        response = self.client.post(self.url, self.values)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        for code, value in (
            ("P", "700.00"),
            ("W", "2700.00"),
            ("X", "451.39"),
            ("AC", "3151.39"),
            ("BV", "204.85"),
            ("BY", "1013.18"),
            ("BZ", "405.00"),
            ("CA", "2090.15"),
            ("CB", "3713.18"),
        ):
            with self.subTest(code=code):
                self.assertTrue(cells[code]["available"])
                self.assertEqual(cells[code]["value"], Decimal(value))
        response = self.client.post(
            self.url,
            {**self.values, "cell": cells["X"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "5416.67 ÷ 12 = 451.39")
        self.assertContains(response, "Extra de Julio 2026")
        self.assertContains(response, "Extra de Diciembre 2026")
        self.assertNotContains(response, "<!doctype html>")

    def test_known_future_salary_change_distinguishes_reference_from_contribution(
        self,
    ):
        self.relationship.seniority_date = date(2010, 12, 1)
        self.relationship.save()
        self.condition.valid_until = date(2026, 7, 1)
        self.condition.save()
        self.condition.pk = None
        self.condition.valid_from = date(2026, 7, 1)
        self.condition.valid_until = None
        self.condition.salary_period = "MONTHLY"
        self.condition.salary_amount_cents = 240000
        self.condition.save()
        response = self.client.post(
            self.url, {**self.values, "months": ["1", "7"]}
        )
        first, second = [
            {cell["code"]: cell for cell in row["cells"]}
            for row in response.context["rows"]
        ]
        self.assertEqual(first["I"]["value"], Decimal(450))
        self.assertEqual(first["X"]["value"], Decimal("496.67"))
        self.assertEqual(first["J"]["value"], Decimal(3150))
        self.assertEqual(first["Z"]["value"], Decimal("3196.67"))
        self.assertEqual(first["CA"]["value"], Decimal("2087.21"))
        self.assertEqual(second["W"]["value"], Decimal(3240))
        self.assertEqual(second["I"]["value"], Decimal(540))
        self.assertEqual(second["X"]["value"], Decimal("496.67"))

    def test_twelve_payments_with_seniority_do_not_need_separate_extras(self):
        self.relationship.seniority_date = date(2010, 12, 1)
        self.relationship.save()
        self.condition.salary_amount_cents = 2400000
        self.condition.payments_per_year = 12
        self.condition.save()
        response = self.client.post(self.url, self.values)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertEqual(cells["I"]["value"], Decimal(0))
        self.assertEqual(cells["X"]["value"], Decimal(0))
        self.assertEqual(cells["CA"]["value"], Decimal("2119.50"))

    def test_incomplete_future_estimate_blocks_totals_and_transition_blocks_both_modalities(
        self,
    ):
        self.condition.valid_until = date(2026, 7, 1)
        self.condition.save()
        response = self.client.post(self.url, self.values)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertTrue(cells["P"]["available"])
        self.assertFalse(cells["CA"]["available"])
        self.assertIn("Estimación anual", cells["CA"]["note"])
        self.condition.pk = None
        self.condition.valid_from = date(2026, 7, 1)
        self.condition.valid_until = None
        self.condition.payments_per_year = 12
        self.condition.save()
        response = self.client.post(
            self.url, {**self.values, "months": ["1", "7"]}
        )
        for row in response.context["rows"]:
            cell = next(cell for cell in row["cells"] if cell["code"] == "CA")
            self.assertFalse(cell["available"])
            self.assertIn("12 y 14", cell["note"])

        EmploymentCondition.objects.filter(valid_from=date(2026, 1, 1)).update(
            payments_per_year=12
        )
        self.condition.payments_per_year = 14
        self.condition.family_insurance_exempt_cents = None
        self.condition.save()
        response = self.client.post(self.url, {**self.values, "months": ["1"]})
        cell = next(
            cell
            for cell in response.context["rows"][0]["cells"]
            if cell["code"] == "CA"
        )
        self.assertFalse(cell["available"])
        self.assertIn("12 y 14", cell["note"])

    def test_extra_reference_uses_seniority_and_excludes_direct_insurance_and_supplement(
        self,
    ):
        self.relationship.seniority_date = date(2010, 12, 1)
        self.relationship.save()
        self.condition.employee_insurance_exempt_cents = 10000
        self.condition.fixed_supplement_cents = 50000
        self.condition.save()
        response = self.client.post(self.url, self.values)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertEqual(cells["P"]["value"], Decimal(735))
        self.assertEqual(cells["I"]["value"], Decimal("455.83"))
        self.assertTrue(cells["CA"]["available"])
        response = self.client.post(
            self.url,
            {**self.values, "cell": cells["I"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "referencia por extra = 2735.00")
        self.assertContains(response, "455,83")
        self.assertContains(response, "no es el pago efectivo")

    def test_extra_reference_handles_leap_anniversary_and_twelve_has_no_extra(
        self,
    ):
        self.relationship.seniority_date = date(2024, 2, 29)
        self.relationship.save()
        cells = {
            cell["code"]: cell
            for cell in report_row(
                self.relationship,
                2026,
                3,
                ROUND_HALF_UP,
                annual_extra_estimate(
                    self.relationship, 2026, ROUND_HALF_UP, date(2026, 11, 19)
                ),
                None,
            )["cells"]
        }
        self.assertTrue(cells["I"]["available"])
        self.condition.payments_per_year = 12
        self.condition.save()
        cells = {
            cell["code"]: cell
            for cell in report_row(
                self.relationship,
                2026,
                3,
                ROUND_HALF_UP,
                annual_extra_estimate(
                    self.relationship, 2026, ROUND_HALF_UP, date(2026, 11, 19)
                ),
                None,
            )["cells"]
        }
        self.assertEqual(cells["I"]["value"], Decimal("0.00"))
        self.assertTrue(cells["I"]["available"])
        self.assertTrue(cells["P"]["available"])

    def test_seniority_cells_and_detail_include_insurances_but_not_fixed_supplement(
        self,
    ):
        self.relationship.seniority_date = date(2010, 12, 1)
        self.relationship.save()
        self.condition.employee_insurance_exempt_cents = 1000
        self.condition.employee_insurance_taxable_cents = 2000
        self.condition.family_insurance_exempt_cents = 3000
        self.condition.family_insurance_taxable_cents = 4000
        self.condition.fixed_supplement_cents = 50000
        self.condition.save()
        response = self.client.post(self.url, self.values)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertEqual(cells["G"]["value"], Decimal(35))
        self.assertEqual(cells["P"]["value"], Decimal(735))
        self.assertTrue(cells["CA"]["available"])
        response = self.client.post(
            self.url,
            {**self.values, "cell": cells["P"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "735,00")
        self.assertContains(response, "base = 2100.00")

    def test_missing_insurance_blocks_amount_but_not_anniversary_month_rate(
        self,
    ):
        self.relationship.seniority_date = date(2023, 12, 1)
        self.relationship.save()
        self.condition.employee_insurance_exempt_cents = None
        self.condition.save()
        cells = {
            cell["code"]: cell
            for cell in report_row(
                self.relationship,
                2026,
                1,
                ROUND_HALF_UP,
                annual_extra_estimate(
                    self.relationship, 2026, ROUND_HALF_UP, date(2026, 11, 19)
                ),
                None,
            )["cells"]
        }
        self.assertTrue(cells["G"]["available"])
        self.assertFalse(cells["P"]["available"])
        self.assertIn("seguros", cells["P"]["note"])
        self.relationship.seniority_date = date(2024, 2, 29)
        self.relationship.save()
        cells = {
            cell["code"]: cell
            for cell in report_row(
                self.relationship,
                2026,
                3,
                ROUND_HALF_UP,
                annual_extra_estimate(
                    self.relationship, 2026, ROUND_HALF_UP, date(2026, 11, 19)
                ),
                None,
            )["cells"]
        }
        for code in ("G", "P"):
            self.assertEqual(cells[code]["available"], code == "G")
        self.assertIn("seguros", cells["P"]["note"])

    def test_february_hire_prorates_salary_and_explains_days_in_detail(self):
        self.relationship.start_date = date(2026, 2, 15)
        self.relationship.seniority_date = date(2026, 2, 15)
        self.relationship.save()
        self.condition.valid_from = date(2026, 2, 15)
        self.condition.save()
        response = self.client.post(self.url, {**self.values, "months": ["2"]})
        row = response.context["rows"][0]
        cells = {cell["code"]: cell for cell in row["cells"]}
        self.assertEqual(row["salary_days"], 16)
        self.assertEqual(cells["O"]["value"], Decimal("1066.67"))
        self.assertTrue(cells["O"]["available"])
        for code in ("Q", "CA", "AC", "BZ"):
            self.assertTrue(cells[code]["available"])
        self.assertEqual(cells["AC"]["value"], Decimal("1222.23"))
        self.assertEqual(cells["X"]["value"], Decimal("155.56"))
        self.assertIn("Días cotizados: 14", cells["AC"]["note"])
        detail = self.client.post(
            self.url,
            {**self.values, "months": ["2"], "cell": cells["O"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(detail, "2000.00 ÷ 30 × 16 días")
        self.assertContains(
            detail, "Mes estándar de 30 días también en febrero"
        )
        self.condition.refresh_from_db()
        self.assertEqual(self.condition.salary_amount_cents, 2800000)

    def test_february_termination_uses_exclusive_end_and_following_month_has_no_payroll(
        self,
    ):
        self.relationship.end_date = date(2026, 2, 16)
        self.relationship.save()
        self.condition.valid_until = date(2026, 2, 16)
        self.condition.save()
        response = self.client.post(
            self.url, {**self.values, "months": ["2", "3"]}
        )
        february, march = response.context["rows"]
        cells = {cell["code"]: cell for cell in february["cells"]}
        self.assertEqual(february["salary_days"], 15)
        self.assertEqual(cells["O"]["value"], Decimal("1000.00"))
        self.assertTrue(cells["CA"]["available"])
        self.assertEqual(march["salary_days"], 0)
        self.assertFalse(
            next(cell for cell in march["cells"] if cell["code"] == "CA")[
                "available"
            ]
        )

    def test_partial_earnings_and_contributions_use_their_respective_days(
        self,
    ):
        self.relationship.start_date = date(2026, 2, 15)
        self.relationship.seniority_date = date(2024, 2, 20)
        self.relationship.save()
        self.condition.valid_from = date(2026, 2, 15)
        self.condition.fixed_supplement_cents = 20000
        self.condition.save()
        response = self.client.post(
            self.url, {**self.values, "months": ["2", "3"]}
        )
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        for code, expected in (
            ("O", "1066.67"),
            ("P", "53.33"),
            ("U", "106.67"),
            ("W", "1226.67"),
        ):
            with self.subTest(code=code):
                self.assertTrue(cells[code]["available"])
                self.assertEqual(cells[code]["value"], Decimal(expected))
        self.assertEqual(
            response.context["semester_extras"][0]["result"].amount,
            Decimal("1586.67"),
        )
        march = {
            cell["code"]: cell for cell in response.context["rows"][1]["cells"]
        }
        self.assertTrue(march["AC"]["available"])
        self.assertEqual(march["X"]["value"], Decimal("350.00"))
        detail = self.client.post(
            self.url,
            {**self.values, "months": ["2"], "cell": cells["P"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(detail, "100.00 ÷ 30 × 16 días")
        self.assertNotContains(detail, "<!doctype html>")
        self.assertContains(response, "Días / 30")
        self.assertContains(response, "÷ 180")

    def test_partial_insurance_uses_salary_days_without_changing_contributions(
        self,
    ):
        self.relationship.start_date = date(2026, 2, 15)
        self.relationship.seniority_date = date(2026, 2, 15)
        self.relationship.save()
        self.condition.valid_from = date(2026, 2, 15)
        self.condition.employee_insurance_exempt_cents = 10000
        self.condition.save()
        response = self.client.post(
            self.url, {**self.values, "months": ["2", "3"]}
        )
        february, march = [
            {cell["code"]: cell for cell in row["cells"]}
            for row in response.context["rows"]
        ]
        for code in ("AC", "BV", "BY", "BZ", "CB"):
            self.assertTrue(february[code]["available"])
        self.assertTrue(february["CA"]["available"])
        self.assertEqual(february["Q"]["value"], Decimal("53.33"))
        self.assertEqual(february["CA"]["value"], Decimal("773.91"))
        self.assertTrue(march["CA"]["available"])
        self.assertEqual(march["CA"]["value"], Decimal("1448.33"))
        detail = self.client.post(
            self.url,
            {**self.values, "months": ["2"], "cell": february["X"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(detail, "Días salariales y cotizados")
        self.assertContains(detail, "3511.11 ÷ 316 × 14 = 155.56")
        self.assertContains(detail, "días naturales de alta")
        self.assertNotContains(
            detail,
            "La prorrata de cotización es este total dividido entre doce",
        )
        self.condition.withholding_rate_basis_points = None
        self.condition.save()
        response = self.client.post(self.url, {**self.values, "months": ["2"]})
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertTrue(cells["BV"]["available"])
        self.assertFalse(cells["BZ"]["available"])
        self.assertFalse(cells["CA"]["available"])

    def test_partial_premiums_round_individually_and_transfer_uses_displayed_deductions(
        self,
    ):
        self.relationship.end_date = date(2026, 2, 16)
        self.relationship.save()
        self.condition.valid_until = date(2026, 2, 16)
        for name in self.condition.money_fields[1:5]:
            setattr(self.condition, name, 1)
        self.condition.save()
        response = self.client.post(self.url, {**self.values, "months": ["2"]})
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        for code in ("Q", "R", "S", "T"):
            self.assertEqual(cells[code]["value"], Decimal("0.01"))
        self.assertEqual(
            cells["CA"]["value"],
            cells["W"]["value"]
            - cells["BV"]["value"]
            - cells["BZ"]["value"]
            - Decimal("0.04"),
        )
        self.assertEqual(cells["CG"]["value"], cells["CA"]["value"])
        detail = self.client.post(
            self.url,
            {**self.values, "months": ["2"], "cell": cells["Q"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(detail, "0.01 ÷ 30 × 15 días")
        self.assertContains(detail, "cada seguro por separado")
        self.condition.refresh_from_db()
        self.assertEqual(self.condition.employee_insurance_exempt_cents, 1)
        self.condition.family_insurance_taxable_cents = None
        self.condition.save()
        response = self.client.post(self.url, {**self.values, "months": ["2"]})
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertFalse(cells["T"]["available"])
        self.assertFalse(cells["CA"]["available"])

    def test_part_time_hours_are_entered_per_period_and_survive_detail_without_persistence(
        self,
    ):
        self.condition.working_time_percentage = 50
        self.condition.salary_period = "MONTHLY"
        self.condition.salary_amount_cents = 50000
        self.condition.payments_per_year = 12
        self.condition.contribution_group = 1
        self.condition.save()
        response = self.client.post(self.url, self.values)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertEqual(cells["O"]["value"], Decimal(500))
        self.assertFalse(cells["AC"]["available"])
        self.assertContains(
            response, "Introduce las horas de este trabajador y mes"
        )
        payload = {
            **self.values,
            f"hours-{self.relationship.pk}-2026-1-worked_hours": "80",
            f"hours-{self.relationship.pk}-2026-2-worked_hours": "60",
        }
        response = self.client.post(self.url, payload)
        january, february = response.context["rows"]
        jan = {cell["code"]: cell for cell in january["cells"]}
        feb = {cell["code"]: cell for cell in february["cells"]}
        self.assertEqual(jan["AC"]["value"], Decimal("958.40"))
        self.assertEqual(feb["AC"]["value"], Decimal("718.80"))
        self.assertTrue(jan["CA"]["available"])
        self.assertEqual(january["hours_form"]["worked_hours"].value(), "80")
        self.assertContains(response, "data-payroll-hours")
        self.assertContains(response, 'form="report-filters"')
        detail = self.client.post(
            self.url,
            {**payload, "cell": jan["AC"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(detail, "Horas ordinarias introducidas")
        self.assertContains(detail, "958,40")
        self.assertNotContains(detail, "<!doctype html>")
        self.condition.refresh_from_db()
        self.assertEqual(self.condition.salary_amount_cents, 50000)
        self.assertEqual(self.condition.working_time_percentage, Decimal(50))
        self.assertEqual(EmploymentCondition.objects.count(), 1)
        for invalid in ("", "0", "-1", "1.001", "NaN", "abc", "700"):
            with self.subTest(hours=invalid):
                result = self.client.post(
                    self.url,
                    {
                        **payload,
                        "months": ["2"],
                        f"hours-{self.relationship.pk}-2026-2-worked_hours": invalid,
                    },
                )
                row = result.context["rows"][0]
                self.assertTrue(row["hours_form"].errors)
                self.assertFalse(
                    next(
                        cell for cell in row["cells"] if cell["code"] == "CA"
                    )["available"]
                )

    def test_part_time_february_hire_keeps_salary_and_insurance_proration_separate_from_hours(
        self,
    ):
        self.relationship.start_date = date(2026, 2, 15)
        self.relationship.seniority_date = date(2026, 2, 15)
        self.relationship.save()
        self.condition.valid_from = date(2026, 2, 15)
        self.condition.working_time_percentage = 50
        self.condition.salary_period = "MONTHLY"
        self.condition.salary_amount_cents = 100000
        self.condition.employee_insurance_exempt_cents = 10000
        self.condition.save()
        response = self.client.post(
            self.url,
            {
                **self.values,
                "months": ["2"],
                f"hours-{self.relationship.pk}-2026-2-worked_hours": "40",
            },
        )
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        for code, expected in (
            ("O", "533.33"),
            ("Q", "53.33"),
            ("AC", "611.11"),
            ("BV", "39.72"),
            ("CA", "360.28"),
        ):
            with self.subTest(code=code):
                self.assertEqual(cells[code]["value"], Decimal(expected))
        self.assertEqual(
            cells["AC"]["contribution_period"]["worked_hours"], Decimal(40)
        )
        self.assertEqual(
            cells["AC"]["contribution_period"]["minimum_common_base"],
            Decimal("343.20"),
        )
        self.assertEqual(
            response.context["semester_extras"][0]["payment"].net_amount,
            Decimal("642.23"),
        )

    def test_manual_hours_are_isolated_between_workers_and_stale_values_are_ignored(
        self,
    ):
        self.condition.working_time_percentage = 50
        self.condition.salary_period = "MONTHLY"
        self.condition.salary_amount_cents = 50000
        self.condition.payments_per_year = 12
        self.condition.contribution_group = 1
        self.condition.save()
        other = Employee.objects.create(
            internal_code="PART-OTHER",
            first_name="Sam",
            last_name="Other",
            birth_date=date(1991, 1, 1),
        )
        relationship = EmploymentRelationship.objects.create(
            employee=other,
            company=self.company,
            start_date=date(2026, 1, 1),
            seniority_date=date(2026, 1, 1),
        )
        values = {
            field.name: getattr(self.condition, field.name)
            for field in self.condition._meta.concrete_fields
            if not field.primary_key and not field.is_relation
        }
        EmploymentCondition.objects.create(
            employment_relationship=relationship, **values
        )
        payload = {
            **self.values,
            "months": ["1"],
            "employees": [str(self.employee.pk), str(other.pk)],
            f"hours-{self.relationship.pk}-2026-1-worked_hours": "80",
            f"hours-{relationship.pk}-2026-1-worked_hours": "40",
            "hours-999999-2026-1-worked_hours": "744",
        }
        response = self.client.post(self.url, payload)
        rows = {
            row["relationship_id"]: row for row in response.context["rows"]
        }
        first = {
            cell["code"]: cell for cell in rows[self.relationship.pk]["cells"]
        }
        second = {
            cell["code"]: cell for cell in rows[relationship.pk]["cells"]
        }
        self.assertEqual(first["AC"]["value"], Decimal("958.40"))
        self.assertEqual(second["AC"]["value"], Decimal(500))
        self.assertEqual(
            rows[relationship.pk]["hours_form"]["worked_hours"].value(), "40"
        )
        self.assertNotIn(
            "required",
            rows[relationship.pk]["hours_form"]["worked_hours"].as_widget(),
        )
        del payload[f"hours-{relationship.pk}-2026-1-worked_hours"]
        response = self.client.post(self.url, payload)
        row = next(
            row
            for row in response.context["rows"]
            if row["relationship_id"] == relationship.pk
        )
        self.assertFalse(
            next(cell for cell in row["cells"] if cell["code"] == "AC")[
                "available"
            ]
        )

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="report-staff", is_staff=True
        )
        self.client.force_login(self.user)
        self.company = Company.objects.create(
            name="Empresa ejemplo", tax_id="EXAMPLE"
        )
        self.other_company = Company.objects.create(
            name="Otra empresa", tax_id="OTHER"
        )
        self.employee = Employee.objects.create(
            internal_code="REPORT",
            first_name="Alex",
            last_name="Example",
            birth_date=date(1990, 1, 1),
        )
        self.relationship = EmploymentRelationship.objects.create(
            employee=self.employee,
            company=self.company,
            start_date=date(2026, 1, 1),
            seniority_date=date(2026, 1, 1),
        )
        self.condition = EmploymentCondition.objects.create(
            employment_relationship=self.relationship,
            valid_from=date(2026, 1, 1),
            contract_type="Indefinido",
            working_time_percentage=100,
            social_security_regime="Régimen General",
            collective_agreement="Prueba",
            contribution_group=5,
            occupational_risk_rate=Decimal("1.50"),
            salary_amount_cents=2800000,
            salary_period="ANNUAL",
            payments_per_year=14,
            withholding_rate_basis_points=1500,
            employee_insurance_exempt_cents=0,
            employee_insurance_taxable_cents=0,
            family_insurance_exempt_cents=0,
            family_insurance_taxable_cents=0,
            fixed_supplement_cents=0,
        )
        self.url = reverse("employees:calculation")
        self.values = {
            "companies": [str(self.company.pk)],
            "employees": [str(self.employee.pk)],
            "years": ["2026"],
            "months": ["1", "2"],
            "columns": [code for code, label in COLUMNS],
            "rounding": ROUND_HALF_UP,
            "base_only": "on",
        }

    def test_initial_page_has_full_catalog_and_dependent_workers(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(COLUMNS), 90)
        self.assertContains(response, "CK · Control BR NCM")
        self.assertContains(response, "Selecciona empresas")
        self.assertIn("no-store", response.headers["Cache-Control"])
        response = self.client.get(
            reverse("employees:calculation-workers"),
            {"companies": self.company.pk},
        )
        self.assertContains(response, "Alex Example")
        self.assertNotContains(response, "<!doctype html>")
        response = self.client.get(
            reverse("employees:calculation-workers"),
            {"companies": "not-an-id"},
        )
        self.assertNotContains(response, "Alex Example")

    def test_table_and_detail_use_same_values_without_writing_records(self):
        response = self.client.post(self.url, self.values)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["rows"]), 2)
        row = response.context["rows"][0]
        cells = {cell["code"]: cell for cell in row["cells"]}
        self.assertEqual(cells["CA"]["value"], Decimal("1548.33"))
        self.assertEqual(cells["AF"]["value"], Decimal("109.67"))
        self.assertFalse(cells["CC"]["available"])
        response = self.client.post(
            self.url,
            {**self.values, "cell": cells["AF"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "2333.33 × 4.70 ÷ 100")
        self.assertContains(response, "109,67")
        self.assertNotContains(response, "<!doctype html>")
        self.assertEqual(
            response.context["detail"]["value"], cells["AF"]["value"]
        )
        self.assertEqual(EmploymentCondition.objects.count(), 1)
        self.assertEqual(Employee.objects.count(), 1)

    def test_normal_post_refresh_and_htmx_history_restore(self):
        response = self.client.post(
            self.url, {"companies": [self.company.pk], "load_workers": "1"}
        )
        self.assertContains(response, "Alex Example")
        self.assertFalse(response.context["form"].is_bound)
        response = self.client.post(
            self.url,
            {**self.values, "cell": f"{self.relationship.pk}:2026:1:CA"},
        )
        self.assertContains(response, "<!doctype html>")
        self.assertEqual(
            response.context["detail"]["value"], Decimal("1548.33")
        )
        response = self.client.get(
            self.url,
            HTTP_HX_REQUEST="true",
            HTTP_HX_HISTORY_RESTORE_REQUEST="true",
        )
        self.assertContains(response, "<!doctype html>")

    def test_worker_and_cell_cannot_escape_selected_company_or_columns(self):
        response = self.client.post(
            self.url, {**self.values, "companies": [self.other_company.pk]}
        )
        self.assertIn("employees", response.context["form"].errors)
        response = self.client.post(
            self.url,
            {
                **self.values,
                "columns": ["O"],
                "cell": f"{self.relationship.pk}:2026:1:CA",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertIsNone(response.context["detail"])
        self.assertContains(response, "Vuelve a calcular")

    def test_each_company_contract_month_is_a_separate_row(self):
        EmploymentRelationship.objects.create(
            employee=self.employee,
            company=self.other_company,
            start_date=date(2026, 1, 1),
            seniority_date=date(2026, 1, 1),
        )
        response = self.client.post(
            self.url,
            {
                **self.values,
                "companies": [self.company.pk, self.other_company.pk],
            },
        )
        self.assertEqual(len(response.context["rows"]), 4)
        self.assertEqual(
            len(
                {
                    (row["relationship_id"], row["period"])
                    for row in response.context["rows"]
                }
            ),
            4,
        )

    def test_unsupported_or_missing_inputs_remain_pending_instead_of_zero(
        self,
    ):
        for name, value in (
            ("occupational_risk_rate", None),
            ("contribution_group", 8),
            ("working_time_percentage", Decimal(50)),
            ("fixed_supplement_cents", None),
            ("social_security_regime", "Mar"),
        ):
            with self.subTest(name=name, value=value):
                EmploymentCondition.objects.filter(
                    pk=self.condition.pk
                ).update(**{name: value})
                row = report_row(
                    self.relationship,
                    2026,
                    1,
                    ROUND_HALF_UP,
                    annual_extra_estimate(
                        self.relationship,
                        2026,
                        ROUND_HALF_UP,
                        date(2026, 11, 19),
                    ),
                    None,
                )
                cells = {cell["code"]: cell for cell in row["cells"]}
                self.assertFalse(cells["CA"]["available"])
                self.assertTrue(cells["O"]["available"])
                self.assertTrue(row["issues"])
                self.condition.save()

    def test_year_without_rules_and_mid_month_change_are_explicit(self):
        row = report_row(
            self.relationship,
            2027,
            1,
            ROUND_HALF_UP,
            annual_extra_estimate(
                self.relationship, 2027, ROUND_HALF_UP, date(2026, 11, 19)
            ),
            None,
        )
        self.assertIn("ejercicio", " ".join(row["issues"]))
        self.condition.valid_until = date(2026, 1, 15)
        self.condition.save()
        row = report_row(
            self.relationship,
            2026,
            1,
            ROUND_HALF_UP,
            annual_extra_estimate(
                self.relationship, 2026, ROUND_HALF_UP, date(2026, 11, 19)
            ),
            None,
        )
        self.assertFalse(
            next(cell for cell in row["cells"] if cell["code"] == "CA")[
                "available"
            ]
        )
        self.assertIn(
            "todo el intervalo activo del mes", " ".join(row["issues"])
        )

    def test_security_and_invalid_filter_values(self):
        for field, value in (
            ("months", ["13"]),
            ("columns", ["UNKNOWN"]),
            ("rounding", "INVALID"),
            ("base_only", ""),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    self.url, {**self.values, field: value}
                )
                self.assertIn(field, response.context["form"].errors)
                self.assertEqual(response.context["rows"], [])
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertIn(
            "HX-Redirect",
            self.client.get(self.url, HTTP_HX_REQUEST="true").headers,
        )
        self.user.is_staff = False
        self.user.save()
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.post(self.url, self.values).status_code, 403
        )
        csrf_client = Client(enforce_csrf_checks=True)
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        csrf_client.force_login(self.user)
        self.assertEqual(
            csrf_client.post(self.url, self.values).status_code, 403
        )

    def test_new_fields_roundtrip_in_form_and_api_and_have_database_limits(
        self,
    ):
        serializer = EmploymentConditionSerializer(
            self.condition,
            data={"contribution_group": 3, "occupational_risk_rate": "2.35"},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save()
        form = EmployeeRegistrationConditionForm(instance=instance)
        self.assertEqual(form["contribution_group"].value(), 3)
        self.assertEqual(
            form["occupational_risk_rate"].value(), Decimal("2.35")
        )
        for payload in (
            {"contribution_group": 12},
            {"occupational_risk_rate": "100.01"},
        ):
            serializer = EmploymentConditionSerializer(
                instance, data=payload, partial=True
            )
            self.assertFalse(serializer.is_valid())
        for payload in (
            {"contribution_group": 12},
            {"occupational_risk_rate": Decimal(-1)},
        ):
            with self.assertRaises(IntegrityError), transaction.atomic():
                EmploymentCondition.objects.filter(pk=instance.pk).update(
                    **payload
                )

    def test_monthly_salary_and_exclusive_condition_boundary(self):
        self.condition.salary_period = "MONTHLY"
        self.condition.salary_amount_cents = 200001
        self.condition.valid_until = date(2026, 2, 1)
        self.condition.save()
        row = report_row(
            self.relationship,
            2026,
            1,
            ROUND_HALF_UP,
            annual_extra_estimate(
                self.relationship, 2026, ROUND_HALF_UP, date(2026, 11, 19)
            ),
            None,
        )
        cells = {cell["code"]: cell for cell in row["cells"]}
        self.assertEqual(cells["O"]["value"], Decimal("2000.01"))
        self.assertFalse(cells["CA"]["available"])
        self.assertIn("Estimación anual", cells["CA"]["note"])
        row = report_row(
            self.relationship,
            2026,
            2,
            ROUND_HALF_UP,
            annual_extra_estimate(
                self.relationship, 2026, ROUND_HALF_UP, date(2026, 11, 19)
            ),
            None,
        )
        self.assertFalse(
            next(cell for cell in row["cells"] if cell["code"] == "O")[
                "available"
            ]
        )

    def test_seniority_anniversary_is_resolved_but_technical_limit_is_pending(
        self,
    ):
        self.relationship.seniority_date = date(2024, 1, 15)
        self.relationship.save()
        row = report_row(
            self.relationship,
            2026,
            1,
            ROUND_HALF_UP,
            annual_extra_estimate(
                self.relationship, 2026, ROUND_HALF_UP, date(2026, 11, 19)
            ),
            None,
        )
        cells = {cell["code"]: cell for cell in row["cells"]}
        self.assertTrue(cells["P"]["available"])
        self.assertEqual(cells["G"]["value"], Decimal(5))
        self.relationship.seniority_date = date(2026, 1, 1)
        self.relationship.save()
        self.condition.salary_period = "MONTHLY"
        self.condition.salary_amount_cents = 999999999999
        self.condition.save()
        row = report_row(
            self.relationship,
            2026,
            1,
            ROUND_HALF_UP,
            annual_extra_estimate(
                self.relationship, 2026, ROUND_HALF_UP, date(2026, 11, 19)
            ),
            None,
        )
        self.assertIn("límite", " ".join(row["issues"]))

    def test_more_than_240_requested_periods_are_rejected(self):
        extra_employees = []
        for number in range(20):
            employee = Employee.objects.create(
                internal_code=f"LIMIT-{number}",
                first_name="Limit",
                last_name=str(number),
                birth_date=date(1990, 1, 1),
            )
            extra_employees.append(str(employee.pk))
            EmploymentRelationship.objects.create(
                employee=employee,
                company=self.company,
                start_date=date(2026, 1, 1),
                seniority_date=date(2026, 1, 1),
            )
        response = self.client.post(
            self.url,
            {
                **self.values,
                "employees": [str(self.employee.pk), *extra_employees],
                "months": [str(month) for month in range(1, 13)],
            },
        )
        self.assertEqual(response.context["rows"], [])
        self.assertContains(response, "240")
