from datetime import date, timedelta
from itertools import pairwise

import pytest

from rt.models import Shift
from rt.services import roster
from rt.services.roster import Candidate, SwapError, plan

NOV_1 = date(2026, 11, 1)
NOV_30 = date(2026, 11, 30)


def people(n, unavailable=None):
    unavailable = unavailable or {}
    return [Candidate(i, frozenset(unavailable.get(i, ()))) for i in range(n)]


def test_fills_every_night_and_is_balanced():
    p = plan(people(10), NOV_1, NOV_30, per_night=2, seed="x")
    assert len(p.nights) == 30 and not p.gaps
    assert all(len(ids) == 2 for ids in p.nights.values())
    counts = p.counts()
    assert max(counts.values()) - min(counts.values()) <= 1


def test_never_two_nights_in_a_row():
    p = plan(people(5), NOV_1, NOV_30, per_night=2, seed="y")
    for (_, a), (_, b) in pairwise(sorted(p.nights.items())):
        assert not set(a) & set(b)


def test_respects_unavailable_weekdays():
    p = plan(people(8, {0: {4}, 1: {5, 6}, 2: {0, 1, 2, 3}}), NOV_1, NOV_30, per_night=2, seed="z")
    for night, ids in p.nights.items():
        if 0 in ids:
            assert night.weekday() != 4
        if 1 in ids:
            assert night.weekday() not in (5, 6)
        if 2 in ids:
            assert night.weekday() >= 4


def test_deterministic_per_seed():
    a = plan(people(9), NOV_1, NOV_30, per_night=3, seed="rt05")
    b = plan(people(9), NOV_1, NOV_30, per_night=3, seed="rt05")
    c = plan(people(9), NOV_1, NOV_30, per_night=3, seed="other")
    assert a.nights == b.nights
    assert a.nights != c.nights


def test_reports_gaps_when_not_enough_people():
    p = plan(people(3), NOV_1, NOV_1 + timedelta(days=3), per_night=2)
    # 3 people, 2 per night, no back-to-back → every other night is short
    assert p.gaps and all(v == 1 for v in p.gaps.values())


def test_history_prevents_back_to_back_across_months():
    p = plan(people(4), NOV_1, NOV_1, per_night=2, history={0: date(2026, 10, 31), 1: date(2026, 10, 31)})
    assert p.nights[NOV_1] == [2, 3]


def test_rejects_bad_per_night():
    with pytest.raises(ValueError):
        plan(people(3), NOV_1, NOV_30, per_night=0)


@pytest.mark.django_db
def test_generate_month_replaces_existing(guards):
    first = roster.generate_month(NOV_1, per_night=2, seed="a")
    assert Shift.objects.count() == 60 and not first.gaps
    roster.generate_month(NOV_1, per_night=1, seed="b")
    assert Shift.objects.filter(date__month=11).count() == 30


@pytest.mark.django_db
def test_swap_rules(guards):
    roster.generate_month(NOV_1, per_night=1, seed="s")
    shifts = list(Shift.objects.select_related("guard"))
    a, b = shifts[0], shifts[5]
    ga, gb = a.guard, b.guard
    if b.date.weekday() not in ga.unavailable_weekdays and a.date.weekday() not in gb.unavailable_weekdays:
        roster.swap(a, b)
        a.refresh_from_db()
        b.refresh_from_db()
        assert (a.guard, b.guard) == (gb, ga)
    with pytest.raises(SwapError):
        roster.swap(a, a)

    friday_hater = guards[2]  # unavailable on Fridays
    friday = Shift.objects.filter(date=date(2026, 11, 6)).exclude(guard=friday_hater).first()
    other = Shift.objects.filter(guard=friday_hater).exclude(date__week_day=6).first()
    with pytest.raises(SwapError, match="tidak bisa"):
        roster.swap(friday, other)
