from django.template import Library


register = Library()


@register.filter
def percentage(value):
    if value is None:
        return '-'
    return f'{value:.0%}'
