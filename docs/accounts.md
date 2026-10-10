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
and the only proof that it and a Google account are one person's
is a browser session that holds both.
So the owner logs in with the password
and connects Google from *My prompts*.
Password login stays:
without an email there is no reset to move anyone off it.

## Not built: merging two accounts

Pressing *Continue with Google* without logging in first
gives a password account's owner a second, empty account,
and connecting that Google account to the first one is then refused.
A merge is cheap,
since a warrior's owners are many-to-many (`WarriorUserPermission`):
copy the rows, move the `GoogleAccount`, deactivate the emptied account.
Offer it at the refusal,
the one moment both accounts are proven in one session,
as a POST after a confirmation page
(see "Cross-device identity" in `docs/king-of-the-hill.md`).
Trigger: refusals in the logs,
where `users.google_login` warns of each.

## Open question: the email address

Google login asks only for the `openid` scope,
so the site never sees an address.
The digest email of `docs/strategy.md` would need the `email` scope,
a data policy change,
and an opt-in to mail;
until that digest exists, collecting addresses has no use.
