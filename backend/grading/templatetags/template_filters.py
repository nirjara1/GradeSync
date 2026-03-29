from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def rubric_num(value):
    """Format numeric rubric values without unnecessary trailing zeros (e.g. 5 not 5.0)."""
    if value is None or value == "":
        return ""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value
    if d == d.to_integral():
        return str(int(d))
    s = format(d, "f").rstrip("0").rstrip(".")
    return s


@register.filter
def find_test(queryset, test_case_id):
    """Find a test result by test case ID from a queryset."""
    try:
        return queryset.get(test_case_id=test_case_id)
    except:
        return None
