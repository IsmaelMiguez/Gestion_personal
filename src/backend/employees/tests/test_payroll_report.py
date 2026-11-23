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
    def test_flexible_insurances_produce_cash_net_and_recharged_tax_detail(
        self,
    ):
        self.relationship.seniority_date = date(2024, 1, 1)
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
            ("AE", "2055.00"),
            ("BV", "159.63"),
            ("BZ", "308.25"),
            ("CA", "1537.12"),
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
        self.assertEqual(payment.cash_gross_amount, Decimal(2005))
        self.assertEqual(payment.cash_withholding_amount, Decimal("300.75"))
        self.assertEqual(payment.payment_on_account_amount, Decimal("7.50"))
        self.assertContains(response, "Ingreso a cuenta repercutido")
        self.assertContains(response, "Del bruto al ingreso bancario")
        self.assertNotContains(response, "<!doctype html>")
        self.condition.refresh_from_db()
        self.assertEqual(self.condition.salary_amount_cents, 2800000)
        self.assertEqual(self.condition.family_insurance_taxable_cents, 3000)

    def test_flexible_insurance_exceeding_cash_budget_leaves_specific_pending_reason(
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
        self.assertFalse(cell["available"])
        self.assertIn("superar el bruto", cell["note"])

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
        self.relationship.seniority_date = date(2011, 1, 1)
        self.relationship.save()
        response = self.client.post(self.url, self.values)
        cells = {
            cell["code"]: cell for cell in response.context["rows"][0]["cells"]
        }
        for code, value in (
            ("P", "700.00"),
            ("W", "2700.00"),
            ("X", "450.00"),
            ("AC", "3150.00"),
            ("BV", "204.76"),
            ("BY", "1012.73"),
            ("BZ", "405.00"),
            ("CA", "2090.24"),
            ("CB", "3712.73"),
        ):
            with self.subTest(code=code):
                self.assertTrue(cells[code]["available"])
                self.assertEqual(cells[code]["value"], Decimal(value))
        response = self.client.post(
            self.url,
            {**self.values, "cell": cells["X"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "5400.00 ÷ 12 = 450.00")
        self.assertContains(response, "Extra de Julio 2026")
        self.assertContains(response, "Extra de Diciembre 2026")
        self.assertNotContains(response, "<!doctype html>")

    def test_known_future_salary_change_distinguishes_reference_from_contribution(
        self,
    ):
        self.relationship.seniority_date = date(2011, 1, 1)
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
        self.assertEqual(first["X"]["value"], Decimal(495))
        self.assertEqual(first["J"]["value"], Decimal(3150))
        self.assertEqual(first["Z"]["value"], Decimal(3195))
        self.assertEqual(first["CA"]["value"], Decimal("2087.32"))
        self.assertEqual(second["W"]["value"], Decimal(3240))
        self.assertEqual(second["I"]["value"], Decimal(540))
        self.assertEqual(second["X"]["value"], Decimal(495))

    def test_twelve_payments_with_seniority_do_not_need_separate_extras(self):
        self.relationship.seniority_date = date(2011, 1, 1)
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
        self.relationship.seniority_date = date(2011, 1, 1)
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
        self.assertFalse(cells["CA"]["available"])
        response = self.client.post(
            self.url,
            {**self.values, "cell": cells["I"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "referencia por extra = 2735.00")
        self.assertContains(response, "455,83")
        self.assertContains(response, "no es el pago efectivo")

    def test_extra_reference_stays_pending_with_unknown_seniority_but_twelve_does_not_add_extras(
        self,
    ):
        self.relationship.seniority_date = date(2024, 1, 15)
        self.relationship.save()
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
            )["cells"]
        }
        self.assertFalse(cells["I"]["available"])
        self.condition.payments_per_year = 12
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
            )["cells"]
        }
        self.assertEqual(cells["I"]["value"], Decimal("0.00"))
        self.assertTrue(cells["I"]["available"])
        self.assertFalse(cells["P"]["available"])

    def test_seniority_cells_and_detail_include_insurances_but_not_fixed_supplement(
        self,
    ):
        self.relationship.seniority_date = date(2011, 1, 1)
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
        self.assertFalse(cells["CA"]["available"])
        response = self.client.post(
            self.url,
            {**self.values, "cell": cells["P"]["key"]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "735,00")
        self.assertContains(response, "base = 2100.00")

    def test_unknown_insurance_preserves_rate_and_mid_month_change_preserves_neither(
        self,
    ):
        self.relationship.seniority_date = date(2024, 1, 1)
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
            )["cells"]
        }
        self.assertTrue(cells["G"]["available"])
        self.assertFalse(cells["P"]["available"])
        self.assertIn("seguros", cells["P"]["note"])
        self.relationship.seniority_date = date(2024, 1, 15)
        self.relationship.save()
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
            )["cells"]
        }
        for code in ("G", "P"):
            self.assertFalse(cells[code]["available"])
            self.assertIn("fecha de efectos", cells[code]["note"])

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
        )
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
        row = report_row(
            self.relationship,
            2026,
            1,
            ROUND_HALF_UP,
            annual_extra_estimate(
                self.relationship, 2026, ROUND_HALF_UP, date(2026, 11, 19)
            ),
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
        )
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
        row = report_row(
            self.relationship,
            2026,
            1,
            ROUND_HALF_UP,
            annual_extra_estimate(
                self.relationship, 2026, ROUND_HALF_UP, date(2026, 11, 19)
            ),
        )
        self.assertIn("antigüedad", " ".join(row["issues"]))
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
