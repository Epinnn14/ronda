from datetime import date
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ExpenseForm, GenerateRosterForm, GuardForm, HouseholdForm
from .models import Expense, Guard, Household, Shift
from .services import dues, roster
from .services.dues import Cell, DuesError
from .services.months import add_months, month_start, parse_month


def _today() -> date:
    return timezone.localdate()


def _year(request: HttpRequest) -> int:
    try:
        return max(2000, min(2100, int(request.GET.get("year", ""))))
    except ValueError:
        return _today().year


def wa_link(phone: str, text: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    return f"https://wa.me/{digits}?text={quote(text)}" if digits else ""


# --------------------------------------------------------------------------- dashboard


@login_required
def dashboard(request):
    today = _today()
    paid, expected = dues.collection_rate(today)
    rates = list(dues.DuesRate.objects.all())
    owing = [
        (hh, items)
        for hh in Household.objects.prefetch_related("payments")
        if (items := dues.arrears(hh, today, rates))
    ]
    tonight = Shift.objects.filter(date=today).select_related("guard")
    return render(
        request,
        "rt/dashboard.html",
        {
            "households": Household.objects.filter(left_on__isnull=True).count(),
            "paid": paid,
            "expected": expected,
            "percent": round(paid * 100 / expected) if expected else 0,
            "arrears_total": sum(a.amount for _, items in owing for a in items),
            "owing_count": len(owing),
            "balance": dues.current_balance(),
            "tonight": tonight,
            "recent_expenses": Expense.objects.all()[:5],
            "month": month_start(today),
        },
    )


# --------------------------------------------------------------------------- households


@login_required
def household_list(request):
    return render(
        request,
        "rt/household_list.html",
        {"households": Household.objects.all()},
    )


@login_required
def household_form(request, pk=None):
    hh = get_object_or_404(Household, pk=pk) if pk else None
    form = HouseholdForm(request.POST or None, instance=hh)
    if request.method == "POST" and form.is_valid():
        hh = form.save()
        messages.success(request, f"Data {hh.address} disimpan.")
        return redirect("household_detail", pk=hh.pk)
    return render(request, "rt/household_form.html", {"form": form, "household": hh})


@login_required
def household_detail(request, pk):
    hh = get_object_or_404(Household, pk=pk)
    items = dues.arrears(hh, _today())
    reminder = dues.reminder_text(hh, items, settings.RT_NAME) if items else ""
    return render(
        request,
        "rt/household_detail.html",
        {
            "household": hh,
            "arrears": items,
            "arrears_total": sum(a.amount for a in items),
            "payments": hh.payments.all()[:24],
            "guards": hh.guards.all(),
            "wa": wa_link(hh.phone, reminder) if reminder else "",
            "reminder": reminder,
        },
    )


# --------------------------------------------------------------------------- dues


@login_required
def dues_matrix(request):
    year = _year(request)
    rows = dues.matrix(year, _today())
    months = [date(year, m, 1) for m in range(1, 13)]
    return render(
        request,
        "rt/dues_matrix.html",
        {"rows": rows, "months": months, "year": year, "rate": dues.rate_for(_today())},
    )


def _cell(request, hh: Household, month: date, error: str = "") -> HttpResponse:
    rows = [r for r in dues.matrix(month.year, _today()) if r.household.pk == hh.pk]
    state = dict(rows[0].cells)[month] if rows else Cell.NOT_APPLICABLE
    return render(
        request, "rt/partials/dues_cell.html", {"hh": hh, "month": month, "state": state, "error": error}
    )


@login_required
@require_POST
def dues_toggle(request, pk, ym):
    hh = get_object_or_404(Household, pk=pk)
    month = parse_month(ym, date.min)
    if month == date.min.replace(day=1):
        return HttpResponseBadRequest("bulan tidak valid")
    error = ""
    try:
        if hh.payments.filter(month=month).exists():
            dues.undo_payment(hh, month)
        else:
            dues.record_payment(hh, month, user=request.user)
    except DuesError as e:
        error = str(e)
    return _cell(request, hh, month, error)


@login_required
def arrears_list(request):
    today = _today()
    rates = list(dues.DuesRate.objects.all())
    rows = []
    for hh in Household.objects.prefetch_related("payments"):
        items = dues.arrears(hh, today, rates)
        if items:
            text = dues.reminder_text(hh, items, settings.RT_NAME)
            rows.append(
                {
                    "hh": hh,
                    "items": items,
                    "total": sum(a.amount for a in items),
                    "wa": wa_link(hh.phone, text),
                }
            )
    rows.sort(key=lambda r: -r["total"])
    return render(
        request,
        "rt/arrears.html",
        {"rows": rows, "grand_total": sum(r["total"] for r in rows), "today": today},
    )


# --------------------------------------------------------------------------- ronda


def _schedule_context(month: date, request) -> dict:
    start, end = roster.month_range(month)
    shifts = Shift.objects.filter(date__range=(start, end)).select_related("guard", "guard__household")
    by_day: dict[date, list[Shift]] = {}
    for s in shifts:
        by_day.setdefault(s.date, []).append(s)
    days = []
    d = start
    while d <= end:
        days.append((d, by_day.get(d, [])))
        d = date.fromordinal(d.toordinal() + 1)
    counts: dict[str, int] = {}
    for s in shifts:
        counts[s.guard.name] = counts.get(s.guard.name, 0) + 1
    return {
        "month": month,
        "prev": add_months(month, -1),
        "next": add_months(month, 1),
        "days": days,
        "leading_blanks": range(start.weekday()),
        "weekdays": Guard.WEEKDAYS,
        "counts": sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])),
        "today": _today(),
        "rt_name": settings.RT_NAME,
        "form": GenerateRosterForm(),
        "can_edit": request.user.is_authenticated,
    }


def schedule(request):
    """Public night-watch schedule."""
    month = parse_month(request.GET.get("month"), _today())
    return render(request, "rt/schedule.html", _schedule_context(month, request))


@login_required
@require_POST
def schedule_generate(request):
    month = parse_month(request.POST.get("month"), _today())
    form = GenerateRosterForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Isian tidak valid.")
    elif not Guard.objects.filter(active=True).exists():
        messages.error(request, "Belum ada petugas ronda aktif.")
    else:
        plan = roster.generate_month(month, form.cleaned_data["per_night"], form.cleaned_data["seed"])
        if plan.gaps:
            messages.warning(request, f"{len(plan.gaps)} malam kekurangan petugas — tambah petugas aktif.")
        else:
            messages.success(request, "Jadwal ronda dibuat.")
    return redirect(f"/jadwal/?month={month:%Y-%m}")


@login_required
@require_POST
def schedule_swap(request):
    month = parse_month(request.POST.get("month"), _today())
    ids = request.POST.getlist("shift")
    ctx_error = ""
    if len(ids) != 2:
        ctx_error = "Pilih tepat dua jadwal untuk ditukar."
    else:
        a, b = (get_object_or_404(Shift.objects.select_related("guard"), pk=i) for i in ids)
        try:
            roster.swap(a, b)
        except roster.SwapError as e:
            ctx_error = str(e)
    ctx = _schedule_context(month, request)
    ctx["swap_error"] = ctx_error
    ctx["swap_ok"] = not ctx_error
    return render(request, "rt/partials/calendar.html", ctx)


@login_required
def guard_list(request):
    form = GuardForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        g = form.save()
        messages.success(request, f"{g.name} ditambahkan sebagai petugas ronda.")
        return redirect("guards")
    return render(
        request, "rt/guards.html", {"guards": Guard.objects.select_related("household"), "form": form}
    )


@login_required
@require_POST
def guard_toggle(request, pk):
    g = get_object_or_404(Guard, pk=pk)
    g.active = not g.active
    g.save(update_fields=["active"])
    return render(request, "rt/partials/guard_row.html", {"g": g})


# --------------------------------------------------------------------------- kas


def cash(request):
    """Public cash book — transparency for every resident."""
    year = _year(request)
    opening, months = dues.cash_book(year)
    expenses = Expense.objects.filter(spent_on__year=year)
    return render(
        request,
        "rt/cash.html",
        {
            "year": year,
            "opening": opening,
            "months": months,
            "income": sum(m.income for m in months),
            "spent": sum(m.expense for m in months),
            "closing": months[-1].balance,
            "expenses": expenses,
            "form": ExpenseForm(initial={"spent_on": _today()}) if request.user.is_authenticated else None,
            "rt_name": settings.RT_NAME,
        },
    )


@login_required
@require_POST
def expense_add(request):
    form = ExpenseForm(request.POST)
    if form.is_valid():
        e = form.save(commit=False)
        e.created_by = request.user
        e.save()
        messages.success(request, "Pengeluaran dicatat.")
        return redirect(f"/kas/?year={e.spent_on.year}")
    messages.error(request, "; ".join(f"{k}: {', '.join(v)}" for k, v in form.errors.items()))
    return redirect("cash")
