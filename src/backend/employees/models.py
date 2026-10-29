from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Employee(models.Model):
    """Store personal identity independently of employment conditions."""

    class IdentificationType(models.TextChoices):
        DNI = "DNI", "DNI"
        NIE = "NIE", "NIE"
        PASSPORT = "PASSPORT", "Pasaporte"
        OTHER = "OTHER", "Otro documento"

    internal_code = models.CharField("código interno", max_length=50, unique=True)
    first_name = models.CharField("nombre", max_length=150)
    last_name = models.CharField("apellidos", max_length=150)
    birth_date = models.DateField("fecha de nacimiento")
    identification_type = models.CharField(
        "tipo de identificación", max_length=20,
        choices=IdentificationType.choices, blank=True,
    )
    tax_id = models.CharField("número de identificación", max_length=30, blank=True)

    class Meta:
        verbose_name = "trabajador"
        verbose_name_plural = "trabajadores"

    def __str__(self):
        return f"{self.internal_code} · {self.first_name} {self.last_name}"


class Company(models.Model):
    name = models.CharField("nombre", max_length=200)
    tax_id = models.CharField("identificación fiscal", max_length=30, unique=True)

    class Meta:
        verbose_name = "empresa"
        verbose_name_plural = "empresas"

    def __str__(self):
        return self.name


class EmploymentRelationship(models.Model):
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="employment_relationships"
    )
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="employment_relationships"
    )
    start_date = models.DateField("inicio")
    end_date = models.DateField("fin exclusivo", null=True, blank=True)
    seniority_date = models.DateField("fecha reconocida de antigüedad")

    class Meta:
        verbose_name = "relación laboral"
        verbose_name_plural = "relaciones laborales"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__isnull=True)
                | models.Q(end_date__gt=models.F("start_date")),
                name="employment_positive_interval",
            ),
        ]

    def clean(self):
        super().clean()
        if self.pk and self.start_date:
            conditions = self.conditions.all()
            if conditions.filter(valid_from__lt=self.start_date).exists():
                raise ValidationError(
                    {"start_date": "Existen condiciones anteriores al inicio."}
                )
            if self.end_date and conditions.filter(
                models.Q(valid_until__isnull=True)
                | models.Q(valid_until__gt=self.end_date)
            ).exists():
                raise ValidationError(
                    {"end_date": "Existen condiciones fuera de la relación."}
                )

    def __str__(self):
        return f"{self.employee} · {self.company} · {self.start_date}"


class EmploymentCondition(models.Model):
    """Describe conditions over an interval with an exclusive end date."""

    class SalaryPeriod(models.TextChoices):
        ANNUAL = "ANNUAL", "Anual"
        MONTHLY = "MONTHLY", "Mensual por paga ordinaria"

    class PaymentCount(models.IntegerChoices):
        TWELVE = 12, "12 pagas"
        FOURTEEN = 14, "14 pagas"

    money_fields = (
        "salary_amount_cents",
        "employee_insurance_exempt_cents",
        "employee_insurance_taxable_cents",
        "family_insurance_exempt_cents",
        "family_insurance_taxable_cents",
        "fixed_supplement_cents",
    )

    employment_relationship = models.ForeignKey(
        EmploymentRelationship, on_delete=models.PROTECT, related_name="conditions"
    )
    valid_from = models.DateField("vigente desde")
    valid_until = models.DateField("vigente hasta (excluido)", null=True, blank=True)
    contract_type = models.CharField("modalidad contractual", max_length=150)
    working_time_percentage = models.DecimalField(
        "porcentaje de jornada", max_digits=5, decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01")),
            MaxValueValidator(Decimal("100")),
        ],
    )
    social_security_regime = models.CharField("régimen", max_length=150)
    collective_agreement = models.CharField("convenio", max_length=200)
    job_title = models.CharField("puesto de trabajo", max_length=150, blank=True)
    salary_amount_cents = models.PositiveBigIntegerField(
        "importe salarial (céntimos)", null=True, blank=True,
        validators=[MaxValueValidator(999999999999)],
    )
    salary_period = models.CharField(
        "unidad del salario", max_length=10, choices=SalaryPeriod.choices,
        blank=True,
    )
    payments_per_year = models.PositiveSmallIntegerField(
        "número de pagas", choices=PaymentCount.choices, null=True, blank=True,
    )
    employee_insurance_exempt_cents = models.PositiveBigIntegerField(
        "seguro trabajador exento (céntimos)", null=True, blank=True,
        validators=[MaxValueValidator(999999999999)],
    )
    employee_insurance_taxable_cents = models.PositiveBigIntegerField(
        "seguro trabajador sujeto (céntimos)", null=True, blank=True,
        validators=[MaxValueValidator(999999999999)],
    )
    family_insurance_exempt_cents = models.PositiveBigIntegerField(
        "seguro familia exento (céntimos)", null=True, blank=True,
        validators=[MaxValueValidator(999999999999)],
    )
    family_insurance_taxable_cents = models.PositiveBigIntegerField(
        "seguro familia sujeto (céntimos)", null=True, blank=True,
        validators=[MaxValueValidator(999999999999)],
    )
    fixed_supplement_cents = models.PositiveBigIntegerField(
        "complemento fijo (céntimos)", null=True, blank=True,
        validators=[MaxValueValidator(999999999999)],
    )
    withholding_rate_basis_points = models.PositiveSmallIntegerField(
        "IRPF (centésimas de porcentaje)", null=True, blank=True,
        validators=[MaxValueValidator(10000)],
    )

    class Meta:
        verbose_name = "condición laboral"
        verbose_name_plural = "condiciones laborales"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valid_until__isnull=True)
                | models.Q(valid_until__gt=models.F("valid_from")),
                name="condition_positive_interval",
            ),
            models.CheckConstraint(
                condition=models.Q(working_time_percentage__gt=0)
                & models.Q(working_time_percentage__lte=100),
                name="condition_valid_percentage",
            ),
            models.CheckConstraint(
                condition=models.Q(payments_per_year__isnull=True)
                | models.Q(payments_per_year__in=[12, 14]),
                name="condition_valid_payment_count",
            ),
            models.CheckConstraint(
                condition=models.Q(withholding_rate_basis_points__isnull=True)
                | models.Q(withholding_rate_basis_points__lte=10000),
                name="condition_valid_withholding_rate",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        salary_amount_cents__isnull=True, salary_period=""
                    )
                    | (
                        models.Q(
                            salary_amount_cents__isnull=False,
                            salary_period__in=["ANNUAL", "MONTHLY"],
                            payments_per_year__isnull=False,
                        )
                    )
                ),
                name="condition_salary_has_unit_and_payments",
            ),
        ]

    def clean(self):
        super().clean()
        if self.salary_amount_cents is None and self.salary_period:
            raise ValidationError({
                "salary_period": "Indica también el importe del salario."
            })
        if self.salary_amount_cents is not None:
            errors = {}
            if not self.salary_period:
                errors["salary_period"] = "Indica si el importe es anual o mensual."
            if self.payments_per_year is None:
                errors["payments_per_year"] = "Indica el número de pagas."
            if errors:
                raise ValidationError(errors)
        if not self.employment_relationship_id or not self.valid_from:
            return
        relationship = EmploymentRelationship.objects.filter(
            pk=self.employment_relationship_id
        ).first()
        if relationship is None:
            return
        if self.valid_from < relationship.start_date:
            raise ValidationError(
                {"valid_from": "Anterior al inicio de la relación laboral."}
            )
        if relationship.end_date and (
            self.valid_until is None or self.valid_until > relationship.end_date
        ):
            raise ValidationError(
                {"valid_until": "Debe quedar dentro de la relación laboral."}
            )
        overlapping = relationship.conditions.exclude(pk=self.pk).filter(
            models.Q(valid_until__isnull=True)
            | models.Q(valid_until__gt=self.valid_from)
        )
        if self.valid_until:
            overlapping = overlapping.filter(valid_from__lt=self.valid_until)
        if overlapping.exists():
            raise ValidationError(
                {"valid_from": "La vigencia se solapa con otra condición."}
            )

    def __str__(self):
        return f"{self.employment_relationship} · {self.valid_from}"
