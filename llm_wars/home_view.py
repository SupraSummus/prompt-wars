from django.template.response import TemplateResponse

from hill.display import home_card


def home(request):
    return TemplateResponse(request, 'home.html', {
        'hill_card': home_card(),
    })
