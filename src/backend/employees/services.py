"""Validated writes shared by API, administration and future forms."""

from django.db import transaction


@transaction.atomic
def create_record(model, values):
    instance = model(**values)
    instance.full_clean()
    instance.save()
    return instance


@transaction.atomic
def update_record(instance, values):
    instance = type(instance).objects.select_for_update().get(pk=instance.pk)
    for field, value in values.items():
        setattr(instance, field, value)
    instance.full_clean()
    instance.save()
    return instance
