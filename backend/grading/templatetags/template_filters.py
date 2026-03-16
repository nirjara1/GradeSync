from django import template

register = template.Library()


@register.filter
def find_test(queryset, test_case_id):
    """Find a test result by test case ID from a queryset."""
    try:
        return queryset.get(test_case_id=test_case_id)
    except:
        return None
