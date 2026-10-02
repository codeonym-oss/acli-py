"""What can go wrong outside the application, as the front ends catch it.

Infrastructure raises its own errors as subclasses of these, so a front end can say what went
wrong without knowing which adapter was behind the port.
"""

from __future__ import annotations


class SiteError(RuntimeError):
    """The site refused a request, or could not be reached."""


class SignInError(SiteError):
    """The site rejected the credentials."""


class NotFound(SiteError):  # noqa: N818 - it reads as what happened: the thing is not found
    """What a request named is not there, or the user can't see it."""


class SettingsError(RuntimeError):
    """The local settings or the token store can't be read or written."""
