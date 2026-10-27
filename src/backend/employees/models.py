from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Employee(models.Model):
    """Store personal identity independently of employment conditions."""

    internal_code = models.CharField("código interno", max_length=50, unique=True)
    first_name = models.CharField("nombre", max_length=150)
    last_name = models.CharField("apellidos", max_length=150)
    birth_date = models.DateField("fecha de nacimiento")
    tax_id = models.CharField("identificación fiscal", max_length=30, blank=True)

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
        ]

    def clean(self):
        super().clean()
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
