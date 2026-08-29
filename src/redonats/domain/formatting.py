"""Pure rendering of domain objects."""

from redonats.domain.models import Donation


def format_donation(donation: Donation) -> str:
    """Render a donation as a human-readable line."""
    return (
        f"[{donation.created_at}] {donation.username}: "
        f"{donation.amount:.2f} {donation.currency} — {donation.message}"
    )
