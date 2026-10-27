"""
Keep a session alive while its visitor keeps coming back.

A session expires `SESSION_COOKIE_AGE` after its last save,
and most requests only read it,
so without a save a logged-in player or a browser holding its warriors
is dropped on a fixed date however often they visit.
`SESSION_SAVE_EVERY_REQUEST` would save on every request;
this saves at most once a day.
"""
from django.utils import timezone


REFRESHED_ON_KEY = 'session_refreshed_on'


class SlidingSessionMiddleware:
    """
    Must come after `SessionMiddleware`,
    so the save it asks for happens on the way out.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        session = request.session
        today = timezone.localdate().isoformat()
        # Empty means no cookie, an expired one, or a logout: nothing to keep alive.
        # Read first: loading is what empties a session that has expired.
        if session.get(REFRESHED_ON_KEY) != today and not session.is_empty():
            session[REFRESHED_ON_KEY] = today
        return response
