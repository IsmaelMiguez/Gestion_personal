from datetime import date
from decimal import ROUND_HALF_UP, Decimal, Inexact, localcontext

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import (
    Company,
    Employee,
    EmploymentCondition,
    EmploymentRelationship,
)
from ..payroll_semester import annual_extra_estimate, semester_extra


class SemesterExtraReportTests(TestCase):
    def test_extra_payment_uses_payment_month_tax_and_excludes_monthly_supplement(
        self,
    ):
        self.condition.contribution_group = 5
        self.condition.withholding_rate_basis_points = 1500
        self.condition.fixed_supplement_cents = 50000
        self.condition.valid_until = date(2026, 7, 1)
        self.condition.save()
        self.condition.pk = None
        self.condition.valid_from = date(2026, 7, 1)
        self.condition.valid_until = None
        self.condition.withholding_rate_basis_points = 2000
        self.condition.save()
        report = semester_extra(
            self.relationship, 2026, 1, ROUND_HALF_UP, date(2026, 8, 1)
        )
        self.assertEqual(report["result"].amount, Decimal(2000))
        self.assertEqual(report["payment"].withholding_rate, Decimal(20))
        self.assertEqual(report["payment"].withholding_amount, Decimal(400))
        self.assertEqual(report["payment"].net_amount, Decimal(1600))
        self.assertEqual(report["payment_issue"], "")

    def test_extra_keeps_gross_when_payment_tax_or_date_is_unknown(self):
        self.condition.contribution_group = 5
        self.condition.save()
        report = semester_extra(
            self.relationship, 2026, 1, ROUND_HALF_UP, date(2026, 8, 1)
        )
        self.assertEqual(report["result"].amount, Decimal(2000))
        self.assertIsNone(report["payment"])
        self.assertIn("IRPF", report["payment_issue"])
        self.condition.withholding_rate_basis_points = 1500
        self.condition.valid_until = date(2026, 7, 15)
        self.condition.save()
        report = semester_extra(
            self.relationship, 2026, 1, ROUND_HALF_UP, date(2026, 8, 1)
        )
        self.assertIsNone(report["payment"])
        self.assertIn("fecha efectiva de pago", report["payment_issue"])
        self.condition.valid_until = None
        self.condition.payments_per_year = 12
        self.condition.save()
        report = semester_extra(
            self.relationship, 2026, 1, ROUND_HALF_UP, date(2026, 8, 1)
        )
        self.assertEqual(report["result"].amount, Decimal(0))
        self.assertIsNone(report["payment"])
        self.assertEqual(report["payment_issue"], "")

    def setUp(self):
        self.company = Company.objects.create(
            name="Empresa", tax_id="SEMESTER"
        )
        self.employee = Employee.objects.create(
            internal_code="SEMESTER",
            first_name="Alex",
            last_name="Example",
            birth_date=date(1990, 1, 1),
        )
        self.relationship = EmploymentRelationship.objects.create(
            company=self.company,
            employee=self.employee,
            start_date=date(2026, 1, 1),
            seniority_date=date(2026, 1, 1),
        )
        self.condition = EmploymentCondition.objects.create(
            employment_relationship=self.relationship,
            valid_from=date(2026, 1, 1),
            contract_type="Indefinido",
            social_security_regime="Régimen General",
            collective_agreement="Prueba",
            working_time_percentage=100,
            salary_amount_cents=200000,
            salary_period="MONTHLY",
            payments_per_year=14,
            employee_insurance_exempt_cents=0,
            employee_insurance_taxable_cents=0,
            family_insurance_exempt_cents=0,
            family_insurance_taxable_cents=0,
        )

    def test_complete_history_uses_previous_conditions_without_per_month_queries(
        self,
    ):
        self.condition.valid_until = date(2026, 4, 1)
        self.condition.save()
        self.condition.pk = None
        self.condition.valid_from = date(2026, 4, 1)
        self.condition.valid_until = None
        self.condition.salary_amount_cents = 240000
        self.condition.save()
        with self.assertNumQueries(1):
            report = semester_extra(
                self.relationship, 2026, 1, ROUND_HALF_UP, date(2026, 7, 1)
            )
        self.assertEqual(report["result"].amount, Decimal(2200))
        self.assertEqual(
            [row["base_salary"] for row in report["rows"]],
            [Decimal(2000)] * 3 + [Decimal(2400)] * 3,
        )
        self.assertFalse(report["projected"])

    def test_seniority_step_on_first_day_uses_each_months_amount(self):
        self.relationship.seniority_date = date(2011, 5, 1)
        self.relationship.save()
        report = semester_extra(
            self.relationship, 2026, 1, ROUND_HALF_UP, date(2026, 7, 1)
        )
        self.assertEqual(report["result"].amount, Decimal("2566.67"))
        self.assertEqual(
            [row["seniority"] for row in report["rows"]],
            [Decimal(500)] * 4 + [Decimal(700)] * 2,
        )

    def test_uncovered_or_ambiguous_month_prevents_partial_total(self):
        self.condition.valid_until = date(2026, 3, 15)
        self.condition.save()
        report = semester_extra(
            self.relationship, 2026, 1, ROUND_HALF_UP, date(2026, 7, 1)
        )
        self.assertIsNone(report["result"])
        self.assertEqual(len(report["rows"]), 6)
        self.assertIn(
            "todo el intervalo activo del mes", report["rows"][2]["issue"]
        )
        self.assertTrue(all("accrued" not in row for row in report["rows"]))
        self.relationship.start_date = date(2026, 1, 15)
        report = semester_extra(
            self.relationship, 2026, 1, ROUND_HALF_UP, date(2026, 7, 1)
        )
        self.assertEqual(report["rows"][0]["salary_days"], 16)
        self.assertNotIn("issue", report["rows"][0])

    def test_leap_anniversary_is_resolved_but_missing_insurance_or_transition_is_pending(
        self,
    ):
        self.relationship.seniority_date = date(2024, 2, 29)
        self.relationship.save()
        report = semester_extra(
            self.relationship, 2026, 1, ROUND_HALF_UP, date(2026, 7, 1)
        )
        self.assertIsNotNone(report["result"])
        self.assertEqual(report["rows"][1]["seniority"], Decimal(100))
        self.relationship.seniority_date = date(2026, 1, 1)
        self.relationship.save()
        self.condition.employee_insurance_exempt_cents = None
        self.condition.save()
        report = semester_extra(
            self.relationship, 2026, 1, ROUND_HALF_UP, date(2026, 7, 1)
        )
        self.assertIsNone(report["result"])
        self.assertIn("seguros", report["rows"][0]["issue"])
        self.condition.employee_insurance_exempt_cents = 0
        self.condition.valid_until = date(2026, 4, 1)
        self.condition.save()
        self.condition.pk = None
        self.condition.valid_from = date(2026, 4, 1)
        self.condition.valid_until = None
        self.condition.payments_per_year = 12
        self.condition.save()
        report = semester_extra(
            self.relationship, 2026, 1, ROUND_HALF_UP, date(2026, 7, 1)
        )
        self.assertIsNone(report["result"])
        self.assertIn("12 y 14", report["issues"][0])

    def test_second_semester_projection_and_decimal_context(self):
        with localcontext() as context:
            context.prec = 3
            context.traps[Inexact] = True
            report = semester_extra(
                self.relationship, 2026, 7, ROUND_HALF_UP, date(2026, 11, 19)
            )
            self.assertEqual(report["result"].amount, Decimal(2000))
            self.assertTrue(report["projected"])
            self.assertEqual(report["result"].payment_month, date(2026, 12, 1))
            self.assertEqual(context.prec, 3)

    def test_view_deduplicates_semesters_and_attaches_detail_to_column_i(self):
        user = get_user_model().objects.create_user(
            username="semester-staff", is_staff=True
        )
        self.client.force_login(user)
        values = {
            "companies": [self.company.pk],
            "employees": [self.employee.pk],
            "years": ["2026"],
            "months": ["1", "2", "7", "12"],
            "columns": ["I"],
            "rounding": ROUND_HALF_UP,
            "base_only": "on",
        }
        url = reverse("employees:calculation")
        response = self.client.post(url, values)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["semester_extras"]), 2)
        self.assertEqual(
            len(response.context["semester_extras"][0]["rows"]), 6
        )
        self.assertContains(response, "Extra de Julio 2026")
        self.assertContains(response, "Extra de Diciembre 2026")
        response = self.client.post(
            url,
            {**values, "cell": f"{self.relationship.pk}:2026:1:I"},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "Extra de Julio 2026")
        self.assertContains(response, "06/2026")
        self.assertNotContains(response, "<!doctype html>")
        self.assertEqual(EmploymentCondition.objects.count(), 1)
        response = self.client.post(url, {**values, "months": ["7"]})
        self.assertEqual(len(response.context["semester_extras"]), 2)
        self.assertContains(response, "Extra de Julio 2026")

    def test_hire_weights_february_accrual_and_records_annual_salary_days(
        self,
    ):
        self.relationship.start_date = date(2026, 2, 15)
        self.relationship.seniority_date = date(2024, 2, 20)
        self.relationship.save()
        self.condition.valid_from = date(2026, 2, 15)
        self.condition.fixed_supplement_cents = 20000
        self.condition.save()
        with self.assertNumQueries(1):
            report = semester_extra(
                self.relationship, 2026, 1, ROUND_HALF_UP, date(2026, 8, 1)
            )
        self.assertEqual(report["result"].amount, Decimal("1586.67"))
        self.assertEqual(
            [row["salary_days"] for row in report["rows"]],
            [0, 16, 30, 30, 30, 30],
        )
        self.assertEqual(report["rows"][1]["seniority"], Decimal(100))
        self.assertEqual(report["rows"][1]["accrued"], Decimal("186.67"))
        estimate = annual_extra_estimate(
            self.relationship, 2026, ROUND_HALF_UP, date(2026, 8, 1)
        )
        self.assertEqual(estimate["amount"], Decimal("3686.67"))
        self.assertEqual(estimate["issues"], [])
        self.assertEqual(estimate["annual_salary_days"], 316)

    def test_termination_keeps_accrued_gross_and_does_not_invent_post_termination_payment(
        self,
    ):
        self.relationship.end_date = date(2026, 2, 16)
        self.relationship.save()
        self.condition.valid_until = date(2026, 2, 16)
        self.condition.save()
        report = semester_extra(
            self.relationship, 2026, 1, ROUND_HALF_UP, date(2026, 8, 1)
        )
        self.assertEqual(report["result"].amount, Decimal("500.00"))
        self.assertEqual(
            [row["salary_days"] for row in report["rows"]],
            [30, 15, 0, 0, 0, 0],
        )
        self.assertIsNone(report["payment"])
        self.assertIn("liquidación", report["payment_issue"])
