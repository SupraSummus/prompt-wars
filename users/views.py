from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from django.views.generic.edit import CreateView

from warriors.views import claim_session_warriors

from .forms import SignupForm


class LoginView(auth_views.LoginView):
    def form_valid(self, form):
        response = super().form_valid(form)
        claim_session_warriors(self.request)
        return response


class SignupView(auth_views.RedirectURLMixin, CreateView):
    """
    A new account is logged in at once and goes where the visitor was headed,
    so signing up from a spell's page lands back on that spell, now kept by the account.
    """
    form_class = SignupForm
    template_name = 'registration/signup.html'
    next_page = settings.LOGIN_REDIRECT_URL

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        claim_session_warriors(self.request)
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[self.redirect_field_name] = self.get_redirect_url()
        return context
