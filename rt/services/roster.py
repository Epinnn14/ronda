"""Night-watch (ronda) roster generator.

Rules, in priority order:
1. a guard is never scheduled on a weekday they marked unavailable;
2. nobody guards two nights in a row;
3. shifts are spread as evenly as possible (fewest shifts first),
   then whoever waited longest since their last shift,
   then a seeded shuffle so ties are fair but reproducible.

The core `plan()` is pure (no database) so it is easy to test exhaustively.
"""

import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db import transaction

from rt.models import Guard, Shift

from .months import add_months


@dataclass(frozen=True)
class Candidate:
    id: int
    unavailable: frozenset[int] = frozenset()


@dataclass
class Plan:
    nights: dict[date, list[int]]
    gaps: dict[date, int] = field(default_factory=dict)  # night -> missing guards

    def counts(self) -> Counter:
        return Counter(g for ids in self.nights.values() for g in ids)


def plan(
    candidates: list[Candidate],
    start: date,
    end: date,
    per_night: int,
    seed: str = "",
    history: dict[int, date] | None = None,
) -> Plan:
    """Assign `per_night` guards to every night from `start` to `end` inclusive.

    `history` maps guard id → last night they guarded before `start`.
    """
    if per_night < 1:
        raise ValueError("per_night must be at least 1")
    rng = random.Random(f"{seed}|{start}|{end}|{per_night}")
    order = {c.id: rng.random() for c in candidates}
    last: dict[int, date | None] = {c.id: (history or {}).get(c.id) for c in candidates}
    count: Counter = Counter()
    nights: dict[date, list[int]] = {}
    gaps: dict[date, int] = {}

    night = start
    while night <= end:
        yesterday = night - timedelta(days=1)
        eligible = [
            c.id for c in candidates if night.weekday() not in c.unavailable and last[c.id] != yesterday
        ]
        eligible.sort(key=lambda g: (count[g], last[g] or date.min, order[g]))
        chosen = eligible[:per_night]
        for g in chosen:
            count[g] += 1
            last[g] = night
        nights[night] = sorted(chosen)
        if len(chosen) < per_night:
            gaps[night] = per_night - len(chosen)
        night += timedelta(days=1)
    return Plan(nights, gaps)


def month_range(month: date) -> tuple[date, date]:
    return month, add_months(month, 1) - timedelta(days=1)


@transaction.atomic
def generate_month(month: date, per_night: int, seed: str = "") -> Plan:
    """Replace the roster for a month with a freshly planned one."""
    start, end = month_range(month)
    guards = list(Guard.objects.filter(active=True))
    history = {}
    for s in Shift.objects.filter(date__lt=start).order_by("date"):
        history[s.guard_id] = s.date
    result = plan(
        [Candidate(g.id, frozenset(g.unavailable_weekdays)) for g in guards],
        start,
        end,
        per_night,
        seed,
        history,
    )
    Shift.objects.filter(date__range=(start, end)).delete()
    Shift.objects.bulk_create(
        [Shift(date=night, guard_id=g) for night, ids in result.nights.items() for g in ids]
    )
    return result


class SwapError(Exception):
    pass


@transaction.atomic
def swap(a: Shift, b: Shift) -> None:
    """Exchange the guards of two shifts (tukar jadwal)."""
    if a.pk == b.pk or a.date == b.date:
        raise SwapError("pilih dua jadwal di malam yang berbeda")
    if (
        Shift.objects.filter(date=a.date, guard=b.guard).exists()
        or Shift.objects.filter(date=b.date, guard=a.guard).exists()
    ):
        raise SwapError("petugas sudah terjadwal di malam tujuan")
    for s, g in ((a, b.guard), (b, a.guard)):
        if s.date.weekday() in g.unavailable_weekdays:
            raise SwapError(f"{g.name} tidak bisa ronda hari {Guard.WEEKDAYS[s.date.weekday()]}")
    a.guard, b.guard = b.guard, a.guard
    a.save(update_fields=["guard"])
    b.save(update_fields=["guard"])
