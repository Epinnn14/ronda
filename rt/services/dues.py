"""Monthly dues (iuran): who owes what, and recording payments."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from django.db import IntegrityError, transaction
from django.db.models import Sum

from rt.models import DuesPayment, DuesRate, Expense, Household

from .months import add_months, month_label, month_start, months_between, rupiah


class DuesError(Exception):
    pass


def rate_for(month: date, rates: list[DuesRate] | None = None) -> int | None:
    """Amount due for a month, or None if no rate was in effect yet."""
    rates = rates if rates is not None else list(DuesRate.objects.all())
    applicable = [r for r in rates if r.effective_from <= month_start(month)]
    return max(applicable, key=lambda r: r.effective_from).amount if applicable else None


def expected_months(hh: Household, until: date, rates: list[DuesRate] | None = None) -> list[date]:
    """Months this household is supposed to pay for, up to and including `until`."""
    if hh.exempt:
        return []
    rates = rates if rates is not None else list(DuesRate.objects.all())
    if not rates:
        return []
    first_rate = min(r.effective_from for r in rates)
    start = max(month_start(hh.joined_on), first_rate)
    end = month_start(until)
    if hh.left_on:
        end = min(end, month_start(hh.left_on))
    return months_between(start, end) if start <= end else []


@dataclass(frozen=True)
class Arrear:
    month: date
    amount: int

    @property
    def label(self):
        return month_label(self.month, long=False)


def arrears(hh: Household, until: date, rates: list[DuesRate] | None = None) -> list[Arrear]:
    rates = rates if rates is not None else list(DuesRate.objects.all())
    paid = set(hh.payments.values_list("month", flat=True))
    return [Arrear(m, rate_for(m, rates) or 0) for m in expected_months(hh, until, rates) if m not in paid]


def record_payment(hh: Household, month: date, user=None, note: str = "") -> DuesPayment:
    month = month_start(month)
    rates = list(DuesRate.objects.all())
    if month not in expected_months(hh, month, rates):
        raise DuesError(f"{hh.address} tidak wajib iuran untuk {month_label(month)}")
    try:
        with transaction.atomic():
            return DuesPayment.objects.create(
                household=hh, month=month, amount=rate_for(month, rates), recorded_by=user, note=note
            )
    except IntegrityError as e:
        raise DuesError(f"{hh.address} sudah bayar {month_label(month)}") from e


def undo_payment(hh: Household, month: date) -> None:
    deleted, _ = DuesPayment.objects.filter(household=hh, month=month_start(month)).delete()
    if not deleted:
        raise DuesError("pembayaran tidak ditemukan")


class Cell(StrEnum):
    PAID = "paid"
    DUE = "due"
    FUTURE = "future"
    NOT_APPLICABLE = "na"


@dataclass
class MatrixRow:
    household: Household
    cells: list[tuple[date, Cell]]

    @property
    def due_count(self):
        return sum(1 for _, c in self.cells if c == Cell.DUE)


def cell_state(hh: Household, month: date, today: date, paid: set[date], expected: set[date]) -> Cell:
    if month in paid:
        return Cell.PAID
    if month > month_start(today):
        return Cell.FUTURE if expected_future(hh, month) else Cell.NOT_APPLICABLE
    return Cell.DUE if month in expected else Cell.NOT_APPLICABLE


def expected_future(hh: Household, month: date) -> bool:
    return (
        not hh.exempt
        and month_start(hh.joined_on) <= month
        and (hh.left_on is None or month <= month_start(hh.left_on))
    )


def matrix(year: int, today: date) -> list[MatrixRow]:
    """Households × 12 months of the year with each cell's payment state."""
    rates = list(DuesRate.objects.all())
    months = [date(year, m, 1) for m in range(1, 13)]
    rows = []
    households = Household.objects.prefetch_related("payments").all()
    for hh in households:
        if hh.left_on and month_start(hh.left_on) < months[0]:
            continue
        paid = {p.month for p in hh.payments.all()}
        expected = set(expected_months(hh, min(months[-1], month_start(today)), rates))
        rows.append(MatrixRow(hh, [(m, cell_state(hh, m, today, paid, expected)) for m in months]))
    return rows


@dataclass
class MonthBook:
    month: date
    income: int
    expense: int
    balance: int

    @property
    def label(self):
        return month_label(self.month)


def cash_book(year: int) -> tuple[int, list[MonthBook]]:
    """Opening balance for the year and income/expense/running balance per month (by paid date)."""
    start = date(year, 1, 1)
    opening = _sum(DuesPayment.objects.filter(paid_on__lt=start)) - _sum(
        Expense.objects.filter(spent_on__lt=start)
    )
    balance, rows = opening, []
    for m in range(1, 13):
        first = date(year, m, 1)
        nxt = add_months(first, 1)
        income = _sum(DuesPayment.objects.filter(paid_on__gte=first, paid_on__lt=nxt))
        expense = _sum(Expense.objects.filter(spent_on__gte=first, spent_on__lt=nxt))
        balance += income - expense
        rows.append(MonthBook(first, income, expense, balance))
    return opening, rows


def current_balance() -> int:
    return _sum(DuesPayment.objects.all()) - _sum(Expense.objects.all())


def _sum(qs) -> int:
    return qs.aggregate(total=Sum("amount"))["total"] or 0


def collection_rate(month: date) -> tuple[int, int]:
    """(paid, expected) household count for a month."""
    rates = list(DuesRate.objects.all())
    month = month_start(month)
    expected = [hh for hh in Household.objects.all() if month in expected_months(hh, month, rates)]
    paid = DuesPayment.objects.filter(month=month, household__in=expected).count()
    return paid, len(expected)


def reminder_text(hh: Household, items: list[Arrear], rt_name: str) -> str:
    total = sum(a.amount for a in items)
    months = ", ".join(a.label for a in items)
    return (
        f"Assalamu'alaikum / Salam sejahtera Bapak/Ibu {hh.head_name} ({hh.address}).\n"
        f"Mengingatkan iuran warga {rt_name} untuk {months} sebesar {rupiah(total)}. Terima kasih 🙏"
    )
