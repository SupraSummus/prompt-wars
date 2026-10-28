# Accounts

An account logs in with a password,
with Google (`users/google_login.py`),
or with both.

## Google login is written in-house

django-allauth was the alternative,
turned down for its size:
its own login and signup views, templates and email-address model
make a second account system beside `users/`
to serve one provider.
The flow is a few dozen lines,
and the part worth a library, checking the ID token, is `google-auth`'s.

## Password accounts link to Google by their owners

No migration links existing accounts to Google accounts:
a password account has no email to match on,
so only its owner can show that it and a Google account are one person's.
They log in with the password
and connect Google from *My prompts*.
Password login stays:
without an email there is no reset to move anyone off it.

## Two accounts of one person become the password account

Pressing *Continue with Google* without logging in first
gives a password account's owner a second, Google-only account,
and connecting that Google account from the first one is then refused.
The way out starts from the Google-only account:
it logs in to the password account, which takes it over (`users.connect_password`).
The password account is the one kept,
since it has the name its owner chose and a password.

The typed password proves the other account,
so nothing waits in the session between requests.
Offering the merge at the refusal is the rejected alternative:
the Google account's proof would wait in the session for a confirmation page,
with an expiry to pick,
and a player who left the page would be stuck again.

## Open question: the email address

Google login asks only for the `openid` scope,
so the site never sees an address.
The digest email of `docs/strategy.md` would need the `email` scope,
a data policy change,
and an opt-in to mail;
until that digest exists, collecting addresses has no use.
