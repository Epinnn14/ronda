from datetime import date

import pytest

from rt.models import DuesRate, Guard, Household


@pytest.fixture
def rates(db):
    DuesRate.objects.create(amount=30_000, effective_from=date(2026, 1, 1))
    DuesRate.objects.create(amount=40_000, effective_from=date(2026, 7, 1))


@pytest.fixture
def houses(db):
    return {
        "a1": Household.objects.create(
            block="A", number=1, head_name="Pak Budi", joined_on=date(2025, 3, 10)
        ),
        "a2": Household.objects.create(block="A", number=2, head_name="Bu Ani", joined_on=date(2026, 5, 20)),
        "a3": Household.objects.create(
            block="A", number=3, head_name="Pak Hadi", joined_on=date(2025, 1, 1), left_on=date(2026, 3, 15)
        ),
        "b1": Household.objects.create(block="B", number=1, head_name="Pak RT", exempt=True),
    }


@pytest.fixture
def guards(houses):
    return [
        Guard.objects.create(name=f"Warga {i}", household=houses["a1"], unavailable_weekdays=un)
        for i, un in enumerate([[], [], [4], [5, 6], [], []])
    ]
