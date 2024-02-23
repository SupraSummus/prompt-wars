from django.template import Library


register = Library()


@register.filter
def percentage(value):
    return f'{value:.0%}'
