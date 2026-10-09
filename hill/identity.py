"""
Who a hill player is: one random key in the Django session, logged in or not.

A new session is a new player, so the per-player caps only set the pace;
the round budget is what bounds the cost.
"""
import uuid


SESSION_KEY = 'hill_player'


def peek_identity(request):
    """
    The visitor's hill identity, or None if they have never attacked.

    Read-only, so pages and polls that only need "is this you?"
    give crawlers and passers-by no session row and no cookie.
    """
    return request.session.get(SESSION_KEY)


def get_identity(request):
    """
    The visitor's hill identity, created on first use.

    Only an attack creates one.
    The key survives `login()`, and `logout()` ends it.
    """
    return request.session.setdefault(SESSION_KEY, uuid.uuid4().hex)
