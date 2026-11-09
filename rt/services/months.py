from datetime import date


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def months_between(first: date, last: date) -> list[date]:
    """Every first-of-month from `first` to `last`, inclusive."""
    out, cur, end = [], month_start(first), month_start(last)
    while cur <= end:
        out.append(cur)
        cur = add_months(cur, 1)
    return out


def parse_month(value: str | None, default: date) -> date:
    """Parse `YYYY-MM`; fall back to `default` on anything else."""
    try:
        y, m = (value or "").split("-")
        return date(int(y), int(m), 1)
    except ValueError:
        return month_start(default)


MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
MONTH_NAMES_LONG = [
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
]


def month_label(d: date, long: bool = True) -> str:
    names = MONTH_NAMES_LONG if long else MONTH_NAMES
    return f"{names[d.month - 1]} {d.year}"


def rupiah(amount: int | None) -> str:
    """12500 → 'Rp12.500' (Indonesian thousands separator)."""
    if amount is None:
        return "-"
    sign = "-" if amount < 0 else ""
    return f"{sign}Rp{abs(amount):,}".replace(",", ".")
