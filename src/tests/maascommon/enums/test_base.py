from maascommon.enums.base import enum_choices
from maastesting.testcase import MAASTestCase


class SampleEnum:
    ONE = "one"
    TWO = "two"


class TestEnumChoices:
    def test_values(self):
        assert enum_choices(SampleEnum) == (("one", "one"), ("two", "two"))

    def test_values_transform(self):
        assert enum_choices(SampleEnum, transform=str.upper) == (
            ("one", "ONE"),
            ("two", "TWO"),
        )
