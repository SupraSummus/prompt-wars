from django.template import Library


register = Library()


@register.filter
def percentage(value, digits=0):
    if value is None:
        return '-'
    return f'{value:.{digits}%}'
