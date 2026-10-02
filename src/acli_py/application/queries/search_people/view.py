"""`PeopleView`: people's profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.domain.meta import Profile


def profile_json(profile: Profile) -> dict[str, Any]:
    """Return a profile as JSON."""
    user = profile.user
    return {
        "accountId": user.account_id,
        "name": user.name,
        "email": user.email or None,
        "accountType": profile.account_type or None,
        "active": user.active,
        "timeZone": profile.time_zone or None,
        "locale": profile.locale or None,
        "groups": list(profile.groups),
    }


@dataclass(frozen=True)
class PeopleView:
    """People."""

    people: tuple[Profile, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return the people as JSON."""
        return [profile_json(p) for p in self.people]
