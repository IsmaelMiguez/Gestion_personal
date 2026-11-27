from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from ..models import (
    Company,
    Employee,
    EmploymentCondition,
    EmploymentRelationship,
    NcmPeriod,
)
from ..payroll_columns import COLUMNS
from ..payroll_semester import annual_extra_estimate
from ..services import delete_employee, save_ncm_period, update_record


class NcmPeriodTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="ncm-staff",
            is_staff=True,
        )
        cls.company = Company.objects.create(name="Empresa NCM", tax_id="NCM")
        cls.employee = Employee.objects.create(
            internal_code="NCM-1",
            first_name="Alex",
            last_name="Example",
            birth_date=date(1990, 1, 1),
        )
        cls.relationship = EmploymentRelationship.objects.create(
            employee=cls.employee,
            company=cls.company,
            start_date=date(2026, 1, 1),
            seniority_date=date(2026, 1, 1),
        )
        cls.condition = EmploymentCondition.objects.create(
            employment_relationship=cls.relationship,
            valid_from=date(2026, 1, 1),
            working_time_percentage=Decimal(50),
            contract_type="Indefinido",
            social_security_regime="General",
            collective_agreement="Prueba",
            contribution_group=5,
            occupational_risk_rate=Decimal("1.50"),
            salary_amount_cents=1400000,
            salary_period="ANNUAL",
            payments_per_year=14,
            withholding_rate_basis_points=1500,
            employee_insurance_exempt_cents=0,
            employee_insurance_taxable_cents=0,
            family_insurance_exempt_cents=0,
            family_insurance_taxable_cents=0,
            fixed_supplement_cents=0,
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.add_url = reverse(
            "employees:ncm-add",
            args=[
                self.employee.pk,
                self.relationship.pk,
            ],
        )
        self.fields = {
            "start_date": "2026-02-01",
            "end_date": "2026-03-01",
            "rest_percentage": "50.00",
            "recognized_daily_base": "50.1234",
        }
        self.filters = {
            "companies": [self.company.pk],
            "employees": [self.employee.pk],
            "years": [2026],
            "months": [2],
            "columns": [code for code, label in COLUMNS],
            "rounding": ROUND_HALF_UP,
            "base_only": "on",
        }

    def create_period(self, fields):
        return save_ncm_period(
            NcmPeriod(
                employment_relationship=self.relationship,
                **fields,
            )
        )

    def test_frontend_creates_edits_and_lists_period_without_changing_contract(
        self,
    ):
        response = self.client.get(self.add_url)
        self.assertContains(response, "Base reguladora diaria")
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, 'type="date"')
        response = self.client.post(self.add_url, self.fields)
        self.assertRedirects(
            response, reverse("employees:detail", args=[self.employee.pk])
        )
        period = self.relationship.ncm_periods.get()
        self.assertEqual(period.recognized_daily_base, Decimal("50.1234"))
        self.assertEqual(period.end_date, date(2026, 3, 1))
        response = self.client.get(
            reverse("employees:detail", args=[self.employee.pk])
        )
        self.assertContains(response, "Editar descanso")
        edit_url = reverse(
            "employees:ncm-edit", args=[self.employee.pk, period.pk]
        )
        response = self.client.post(
            edit_url,
            {**self.fields, "rest_percentage": "100"},
            HTTP_HX_REQUEST="true",
        )
        self.assertIn("HX-Redirect", response.headers)
        period.refresh_from_db()
        self.assertEqual(period.rest_percentage, Decimal(100))
        self.condition.refresh_from_db()
        self.assertEqual(self.condition.working_time_percentage, Decimal(50))
        self.assertEqual(self.condition.salary_amount_cents, 1400000)

    def test_invalid_forms_keep_values_and_do_not_write(self):
        for field, value in (
            ("end_date", "2026-02-01"),
            ("start_date", "2025-12-01"),
            ("rest_percentage", "0"),
            ("rest_percentage", "100.01"),
            ("recognized_daily_base", "0"),
            ("recognized_daily_base", "12.12345"),
        ):
            with self.subTest(field=field, value=value):
                response = self.client.post(
                    self.add_url,
                    {**self.fields, field: value},
                    HTTP_HX_REQUEST="true",
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
                self.assertNotContains(response, "<!doctype html>")
                self.assertFalse(NcmPeriod.objects.exists())

    def test_overlap_is_rejected_but_adjacent_exclusive_periods_are_valid(
        self,
    ):
        first = self.create_period(
            {
                "start_date": date(2026, 2, 1),
                "end_date": date(2026, 2, 15),
                "rest_percentage": Decimal(50),
                "recognized_daily_base": Decimal(50),
            }
        )
        with self.assertRaisesMessage(ValidationError, "solapa"):
            self.create_period(
                {
                    "start_date": date(2026, 2, 14),
                    "end_date": date(2026, 3, 1),
                    "rest_percentage": Decimal(100),
                    "recognized_daily_base": Decimal(50),
                }
            )
        second = self.create_period(
            {
                "start_date": first.end_date,
                "end_date": date(2026, 3, 1),
                "rest_percentage": Decimal(100),
                "recognized_daily_base": Decimal(50),
            }
        )
        second.full_clean()
        self.assertEqual(self.relationship.ncm_periods.count(), 2)

    def test_contract_dates_cannot_exclude_ncm_in_either_direction(self):
        self.client.post(self.add_url, self.fields)
        for field, value in (
            ("start_date", date(2026, 2, 2)),
            ("end_date", date(2026, 2, 28)),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError) as caught:
                    update_record(self.relationship, {field: value})
                self.assertIn(field, caught.exception.message_dict)
        update_record(self.condition, {"valid_until": date(2026, 3, 1)})
        update_record(self.relationship, {"end_date": date(2026, 3, 1)})
        with self.assertRaises(ValidationError) as caught:
            self.create_period(
                {
                    "start_date": date(2026, 3, 1),
                    "end_date": date(2026, 3, 5),
                    "rest_percentage": Decimal(50),
                    "recognized_daily_base": Decimal(50),
                }
            )
        self.assertIn("end_date", caught.exception.message_dict)

    def test_database_constraints_reject_invalid_numeric_and_date_ranges(self):
        fields = {
            "employment_relationship": self.relationship,
            "start_date": date(2026, 2, 1),
            "end_date": date(2026, 3, 1),
            "rest_percentage": Decimal(50),
            "recognized_daily_base": Decimal(50),
        }
        for field, value in (
            ("end_date", date(2026, 2, 1)),
            ("rest_percentage", Decimal(0)),
            ("rest_percentage", Decimal(101)),
            ("recognized_daily_base", Decimal(0)),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    NcmPeriod.objects.create(**{**fields, field: value})

    def test_report_uses_partial_contract_and_separates_benefit_from_net(self):
        self.client.post(self.add_url, self.fields)
        response = self.client.post(
            reverse("employees:calculation"), self.filters
        )
        row = response.context["rows"][0]
        cells = {cell["code"]: cell for cell in row["cells"]}
        self.assertEqual(cells["F"]["value"], Decimal(25))
        self.assertEqual(cells["N"]["value"], Decimal(50))
        self.assertEqual(cells["K"]["value"], Decimal("50.1234"))
        self.assertEqual(cells["M"]["value"], Decimal(14))
        self.assertEqual(cells["CC"]["value"], Decimal("701.73"))
        self.assertNotIn("hours_form", row)
        for code in ("O", "W", "AC", "CA", "CB", "CE", "CF", "CG", "CJ", "CK"):
            with self.subTest(code=code):
                self.assertFalse(cells[code]["available"])
        response = self.client.post(
            reverse("employees:calculation"),
            {**self.filters, "cell": cells["CC"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "Periodos NCM del mes")
        self.assertContains(response, "50,1234")
        self.assertNotContains(response, "<!doctype html>")
        self.assertEqual(
            response.context["detail"]["value"], Decimal("701.73")
        )

    def test_cross_month_period_uses_calendar_days_and_exclusive_end(self):
        self.create_period(
            {
                "start_date": date(2026, 1, 31),
                "end_date": date(2026, 3, 2),
                "rest_percentage": Decimal(100),
                "recognized_daily_base": Decimal(50),
            }
        )
        response = self.client.post(
            reverse("employees:calculation"),
            {
                **self.filters,
                "months": [1, 2, 3],
            },
        )
        rows = response.context["rows"]
        amounts = [
            next(
                cell["value"] for cell in row["cells"] if cell["code"] == "CC"
            )
            for row in rows
        ]
        self.assertEqual(amounts, [Decimal(50), Decimal(1400), Decimal(50)])
        cells = {cell["code"]: cell for cell in rows[0]["cells"]}
        self.assertFalse(cells["F"]["available"])
        self.assertEqual(
            cells["CC"]["ncm_segments"][0][
                "result"
            ].effective_working_percentage,
            0,
        )

    def test_multiple_periods_explain_separate_values_without_fake_average(
        self,
    ):
        for first, end, rest, base in (
            (1, 15, "50", "50"),
            (15, 22, "100", "60"),
        ):
            self.create_period(
                {
                    "start_date": date(2026, 2, first),
                    "end_date": date(2026, 2, end),
                    "rest_percentage": Decimal(rest),
                    "recognized_daily_base": Decimal(base),
                }
            )
        response = self.client.post(
            reverse("employees:calculation"), self.filters
        )
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertEqual(cells["CC"]["value"], Decimal(770))
        for code in ("F", "K", "N"):
            self.assertFalse(cells[code]["available"])
        self.assertEqual(len(cells["CC"]["ncm_segments"]), 2)

    def test_missing_conditions_do_not_publish_partial_benefit(self):
        self.client.post(self.add_url, self.fields)
        self.condition.delete()
        response = self.client.post(
            reverse("employees:calculation"), self.filters
        )
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertFalse(cells["CC"]["available"])
        self.assertContains(response, "Faltan condiciones únicas")

    def test_ncm_blocks_semester_and_dependent_annual_cotization(self):
        self.client.post(self.add_url, self.fields)
        estimate = annual_extra_estimate(
            self.relationship, 2026, ROUND_HALF_UP, date(2026, 11, 26)
        )
        self.assertIsNone(estimate["amount"])
        self.assertIsNone(estimate["semesters"][0]["result"])
        self.assertIsNone(estimate["semesters"][0]["payment"])
        self.assertIn("NCM", " ".join(estimate["issues"]))
        response = self.client.post(
            reverse("employees:calculation"),
            {
                **self.filters,
                "months": [1],
                f"hours-{self.relationship.pk}-2026-1-worked_hours": "80",
            },
        )
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertTrue(cells["O"]["available"])
        self.assertFalse(cells["AC"]["available"])
        self.assertFalse(cells["CA"]["available"])

    def test_ncm_in_extra_payment_month_blocks_payment_of_otherwise_known_extra(
        self,
    ):
        self.create_period(
            {
                "start_date": date(2026, 7, 1),
                "end_date": date(2026, 8, 1),
                "rest_percentage": Decimal(50),
                "recognized_daily_base": Decimal(50),
            }
        )
        estimate = annual_extra_estimate(
            self.relationship, 2026, ROUND_HALF_UP, date(2026, 11, 26)
        )
        first = estimate["semesters"][0]
        self.assertIsNotNone(first["result"])
        self.assertIsNone(first["payment"])
        self.assertIn("NCM en el mes de abono", first["payment_issue"])

    def test_deletion_requires_confirmation_and_restores_ordinary_calculation(
        self,
    ):
        self.client.post(self.add_url, self.fields)
        period = self.relationship.ncm_periods.get()
        url = reverse(
            "employees:ncm-delete", args=[self.employee.pk, period.pk]
        )
        self.client.get(url)
        self.client.post(url, {})
        self.assertTrue(NcmPeriod.objects.filter(pk=period.pk).exists())
        response = self.client.post(url, {"confirm": "on"})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            reverse("employees:calculation"),
            {
                **self.filters,
                f"hours-{self.relationship.pk}-2026-2-worked_hours": "80",
            },
        )
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        self.assertTrue(cells["CA"]["available"])
        self.assertTrue(
            EmploymentCondition.objects.filter(pk=self.condition.pk).exists()
        )

    def test_delete_employee_includes_ncm_and_preserves_company(self):
        self.client.post(self.add_url, self.fields)
        response = self.client.get(
            reverse("employees:delete", args=[self.employee.pk])
        )
        self.assertEqual(response.context["ncm_count"], 1)
        delete_employee(self.employee)
        self.assertFalse(NcmPeriod.objects.exists())
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())

    def test_access_checks_and_csrf_protect_every_write(self):
        self.client.post(self.add_url, self.fields)
        period = self.relationship.ncm_periods.get()
        urls = [
            self.add_url,
            reverse("employees:ncm-edit", args=[self.employee.pk, period.pk]),
            reverse(
                "employees:ncm-delete", args=[self.employee.pk, period.pk]
            ),
        ]
        anonymous = Client()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        ordinary = get_user_model().objects.create_user(
            username="ncm-nonstaff"
        )
        self.client.force_login(ordinary)
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(anonymous.get(url).status_code, 302)
                self.assertEqual(
                    self.client.post(url, self.fields).status_code, 403
                )
                self.assertEqual(
                    csrf_client.post(url, self.fields).status_code, 403
                )
        self.client.force_login(self.user)
        response = self.client.get(
            reverse(
                "employees:ncm-edit", args=[self.employee.pk + 100, period.pk]
            )
        )
        self.assertEqual(response.status_code, 404)
