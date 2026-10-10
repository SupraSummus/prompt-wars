from django.template.response import TemplateResponse
from dominate.tags import a, h1, h2, hgroup, li, main, p, section, strong, ul

from djsfc import Router, parse_template


router = Router(__name__)


# Create a template that extends base.html and includes our Dominate-generated content
template = parse_template('''
{% extends "base.html" %}

{% block title %}Data policy - Prompt Wars{% endblock %}

{% block content %}
{{ privacy_content|safe }}
{% endblock %}
''', router=router)


@router.route('GET', '')
def root(request):
    main_el = main(cls="container")

    with main_el:
        with hgroup():
            h1("Data Policy")
            p("what we do with your data")

        with section():
            h2("Submitted Prompts")
            p("Your submitted prompts are stored in our database and used in battles.")
            p(strong("Do not include sensitive information"), " in your prompts. Once submitted, they may become visible to other users.")
            p("We currently do not support deleting prompts from our system.")

        with section():
            h2("The Model's Replies")
            p("The model's replies in a battle are generated from two players' prompts, glued into one message. Please note:")
            with ul():
                li("The model's replies are always visible to the other participant in the battle")
                li("If either participant has ticked \"Make the model's replies public\", the replies in the battle will be publicly viewable")
                li("We currently do not support deleting the model's replies from our system.")

        with section():
            h2("Logging in with Google")
            p(
                "Logging in with Google takes you to Google's sign-in page. "
                "The site asks Google only for your Google account's identifier, which it stores to log you in; "
                "it receives neither your name nor your email address.",
            )

        with section():
            h2("King of the Hill")
            p("What a player writes for the hill stays private to them, with one exception:")
            with ul():
                li(
                    "When a prompt takes the hill, its text, the name and author given to it, "
                    "and the model's replies in the battle that won it are published. "
                    "The attack form asks for this consent with every attack.",
                )
                li(
                    "Every other attack's text, the names given to it and the model's replies "
                    "are shown only in the browser session it was sent from.",
                )
                li(
                    "An attack's score is shown without them: "
                    "in the round's standings, as \"Attacker #k\", "
                    "and to anyone who opens the attack's link.",
                )
                li(
                    "The hill tells players apart by a random key in the session cookie. "
                    "Logging out, clearing cookies or two weeks without an attack ends it, "
                    "and with it access to earlier attacks.",
                )
                li("The attack form uses Google reCAPTCHA, which sends the visitor's IP address to Google. The hill stores no IP address.")
                li(
                    "To have a published prompt taken down, contact the operator through the project's ",
                    a("GitHub page", href="https://github.com/SupraSummus/prompt-wars"),
                    ".",
                )

    return TemplateResponse(request, template, {
        'privacy_content': main_el.render(),
    })
