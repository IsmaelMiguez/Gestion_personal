"""Validated writes shared by API, administration and future forms."""

from django.db import transaction


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
