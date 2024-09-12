#  Copyright 2024 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from typing import Any, Callable


def enum_choices(
    enum: Any, transform: Callable[[str], str] = lambda value: value
) -> tuple[[str, str], ...]:
    """Return sequence of tuples for Django's `choices` field from an enum-like class.

    Enum-like classes have the following structure:

      class MyEnum:
          VAL1 = "value1"
          VAL2 = "value2"

    Each element in a 2-tuple, with the enum value both as database value and
    human readable value (e.g. (("value1", "value1"), ("value2", "value2")) for
    the example above).

    If a `transform` callable is provided, it's called on the human-readable
    value to get a processed version.

    TODO:
      This should be dropped and classes become subclasses of django.db.models.TextChoices
      once we move to Django 3.0 which has native support for Enum types.
      The `choices` property of TextChoices replaces this function.
    """

    return tuple(
        (value, transform(value))
        for attr, value in enum.__dict__.items()
        if not attr.startswith("_")
    )
