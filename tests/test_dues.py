from datetime import date

import pytest

from rt.models import DuesPayment, Expense
from rt.services import dues
from rt.services.dues import Cell, DuesError
from rt.services.months import add_months, months_between, parse_month

pytestmark = pytest.mark.django_db


def test_month_helpers():
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 1)
    assert add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert months_between(date(2026, 11, 30), date(2027, 1, 2)) == [
        date(2026, 11, 1),
        date(2026, 12, 1),
        date(2027, 1, 1),
    ]
    assert parse_month("2026-02", date(2000, 1, 5)) == date(2026, 2, 1)
    assert parse_month("garbage", date(2026, 3, 9)) == date(2026, 3, 1)
    assert parse_month("2026-13", date(2026, 3, 9)) == date(2026, 3, 1)


def test_rate_changes_over_time(rates):
    assert dues.rate_for(date(2025, 12, 1)) is None
    assert dues.rate_for(date(2026, 6, 1)) == 30_000
    assert dues.rate_for(date(2026, 7, 31)) == 40_000


def test_expected_months_respect_join_leave_exempt_and_first_rate(rates, houses):
    until = date(2026, 8, 15)
    # joined 2025 but dues only exist from Jan 2026
    assert dues.expected_months(houses["a1"], until)[0] == date(2026, 1, 1)
    assert len(dues.expected_months(houses["a1"], until)) == 8
    assert dues.expected_months(houses["a2"], until)[0] == date(2026, 5, 1)
    assert dues.expected_months(houses["a3"], until)[-1] == date(2026, 3, 1)
    assert dues.expected_months(houses["b1"], until) == []


def test_arrears_use_the_rate_of_each_month(rates, houses):
    a2 = houses["a2"]
    dues.record_payment(a2, date(2026, 5, 1))
    owed = dues.arrears(a2, date(2026, 8, 3))
    assert [(a.month.month, a.amount) for a in owed] == [(6, 30_000), (7, 40_000), (8, 40_000)]
    assert owed[0].label == "Jun 2026"


def test_record_payment_validates(rates, houses):
    a1 = houses["a1"]
    p = dues.record_payment(a1, date(2026, 7, 19))
    assert (p.month, p.amount) == (date(2026, 7, 1), 40_000)
    with pytest.raises(DuesError, match="sudah bayar"):
        dues.record_payment(a1, date(2026, 7, 1))
    with pytest.raises(DuesError, match="tidak wajib"):
        dues.record_payment(houses["b1"], date(2026, 7, 1))
    with pytest.raises(DuesError, match="tidak wajib"):
        dues.record_payment(houses["a3"], date(2026, 6, 1))  # already moved out
    # paying ahead is allowed
    assert dues.record_payment(a1, date(2026, 12, 1)).amount == 40_000

    dues.undo_payment(a1, date(2026, 7, 1))
    with pytest.raises(DuesError):
        dues.undo_payment(a1, date(2026, 7, 1))


def test_matrix_states(rates, houses):
    dues.record_payment(houses["a1"], date(2026, 1, 1))
    rows = {r.household.address: r for r in dues.matrix(2026, today=date(2026, 6, 10))}
    a1 = dict(rows["A-1"].cells)
    assert a1[date(2026, 1, 1)] == Cell.PAID
    assert a1[date(2026, 2, 1)] == Cell.DUE
    assert a1[date(2026, 7, 1)] == Cell.FUTURE
    assert rows["A-1"].due_count == 5
    a2 = dict(rows["A-2"].cells)
    assert a2[date(2026, 4, 1)] == Cell.NOT_APPLICABLE
    assert all(c == Cell.NOT_APPLICABLE for _, c in rows["B-1"].cells)
    a3 = dict(rows["A-3"].cells)
    assert a3[date(2026, 3, 1)] == Cell.DUE and a3[date(2026, 4, 1)] == Cell.NOT_APPLICABLE
    # households that left before the year are hidden
    assert "A-3" not in {r.household.address for r in dues.matrix(2027, today=date(2027, 1, 5))}


def test_cash_book_running_balance(rates, houses):
    DuesPayment.objects.create(
        household=houses["a1"], month=date(2025, 12, 1), amount=50_000, paid_on=date(2025, 12, 20)
    )
    p = dues.record_payment(houses["a1"], date(2026, 1, 1))
    p.paid_on = date(2026, 1, 5)
    p.save()
    Expense.objects.create(
        spent_on=date(2026, 2, 2), category="keamanan", amount=20_000, description="senter"
    )
    opening, months = dues.cash_book(2026)
    assert opening == 50_000
    assert (months[0].income, months[0].balance) == (30_000, 80_000)
    assert (months[1].expense, months[1].balance) == (20_000, 60_000)
    assert months[-1].balance == 60_000
    assert dues.current_balance() == 60_000


def test_collection_rate_and_reminder(rates, houses):
    dues.record_payment(houses["a1"], date(2026, 6, 1))
    assert dues.collection_rate(date(2026, 6, 14)) == (1, 2)  # a1, a2 expected; a3 left; b1 exempt
    text = dues.reminder_text(houses["a2"], dues.arrears(houses["a2"], date(2026, 7, 1)), "RT 05")
    assert "Bu Ani (A-2)" in text and "Rp100.000" in text and "Mei 2026, Jun 2026, Jul 2026" in text
