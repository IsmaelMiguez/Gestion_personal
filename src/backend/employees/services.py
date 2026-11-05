"""Validated writes shared by API, administration and future forms."""

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import EmploymentCondition


def save_record(instance):
    instance.full_clean()
    instance.save()
    return instance


@transaction.atomic
def create_record(model, values):
    return save_record(model(**values))


@transaction.atomic
def update_record(instance, values):
    instance = type(instance).objects.select_for_update().get(pk=instance.pk)
    for field, value in values.items():
        setattr(instance, field, value)
    return save_record(instance)


@transaction.atomic
def register_employee(employee, relationship, condition):
    """Save the complete registration or roll back every write."""
    save_record(employee)
    relationship.employee = employee
    save_record(relationship)
    condition.employment_relationship = relationship
    save_record(condition)
    return employee


@transaction.atomic
def change_conditions(previous, replacement):
    """Split a period, preserving its original end and remuneration history."""
    previous = type(previous).objects.select_for_update().get(pk=previous.pk)
    if (
        replacement.valid_from is None
        or replacement.valid_from <= previous.valid_from
    ):
        raise ValidationError(
            {
                "valid_from": "La fecha del cambio debe ser posterior al inicio del periodo anterior."
            }
        )
    if previous.valid_until and replacement.valid_from >= previous.valid_until:
        raise ValidationError(
            {
                "valid_from": "El cambio debe estar dentro del periodo seleccionado."
            }
        )
    if replacement.pk is not None:
        raise ValidationError(
            "Las nuevas condiciones deben ser un registro nuevo."
        )
    replacement.employment_relationship = previous.employment_relationship
    replacement.valid_until = previous.valid_until
    previous.valid_until = replacement.valid_from
    save_record(previous)
    return save_record(replacement)


@transaction.atomic
def delete_condition(condition):
    condition = (
        type(condition).objects.select_for_update().get(pk=condition.pk)
    )
    condition.delete()


@transaction.atomic
def delete_employee(employee):
    """Remove the confirmed employee's conditions and contracts, not the company."""
    employee = type(employee).objects.select_for_update().get(pk=employee.pk)
    relationships = employee.employment_relationships.all()
    EmploymentCondition.objects.filter(
        employment_relationship__in=relationships
    ).delete()
    relationships.delete()
    employee.delete()


@transaction.atomic
def add_conditions(relationship, condition):
    relationship = (
        type(relationship).objects.select_for_update().get(pk=relationship.pk)
    )
    condition.employment_relationship = relationship
    return save_record(condition)
