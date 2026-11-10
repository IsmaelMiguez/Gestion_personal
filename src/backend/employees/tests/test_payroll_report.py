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


class PayrollReportTests(TestCase):
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
            ("fixed_supplement_cents", 1000),
            ("social_security_regime", "Mar"),
        ):
            with self.subTest(name=name, value=value):
                EmploymentCondition.objects.filter(
                    pk=self.condition.pk
                ).update(**{name: value})
                row = report_row(self.relationship, 2026, 1, ROUND_HALF_UP)
                cells = {cell["code"]: cell for cell in row["cells"]}
                self.assertFalse(cells["CA"]["available"])
                self.assertTrue(cells["O"]["available"])
                self.assertTrue(row["issues"])
                self.condition.save()

    def test_year_without_rules_and_mid_month_change_are_explicit(self):
        row = report_row(self.relationship, 2027, 1, ROUND_HALF_UP)
        self.assertIn("ejercicio", " ".join(row["issues"]))
        self.condition.valid_until = date(2026, 1, 15)
        self.condition.save()
        row = report_row(self.relationship, 2026, 1, ROUND_HALF_UP)
        self.assertFalse(
            next(cell for cell in row["cells"] if cell["code"] == "CA")[
                "available"
            ]
        )
        self.assertIn("todo el mes", " ".join(row["issues"]))

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
        row = report_row(self.relationship, 2026, 1, ROUND_HALF_UP)
        cells = {cell["code"]: cell for cell in row["cells"]}
        self.assertEqual(cells["O"]["value"], Decimal("2000.01"))
        self.assertTrue(cells["CA"]["available"])
        row = report_row(self.relationship, 2026, 2, ROUND_HALF_UP)
        self.assertFalse(
            next(cell for cell in row["cells"] if cell["code"] == "O")[
                "available"
            ]
        )

    def test_seniority_anniversary_inside_month_and_technical_limit_are_pending(
        self,
    ):
        self.relationship.seniority_date = date(2024, 1, 15)
        self.relationship.save()
        row = report_row(self.relationship, 2026, 1, ROUND_HALF_UP)
        self.assertIn("antigüedad", " ".join(row["issues"]))
        self.relationship.seniority_date = date(2026, 1, 1)
        self.relationship.save()
        self.condition.salary_period = "MONTHLY"
        self.condition.salary_amount_cents = 999999999999
        self.condition.save()
        row = report_row(self.relationship, 2026, 1, ROUND_HALF_UP)
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
