from django import template

from rt.services.months import month_label as _month_label
from rt.services.months import rupiah as _rupiah

register = template.Library()


@register.filter
def rupiah(value):
    return _rupiah(value)


@register.filter
def month_label(value, short=""):
    return _month_label(value, long=not short)


@register.filter
def ym(value):
    """date → 'YYYY-MM' for URLs."""
    return f"{value:%Y-%m}"
