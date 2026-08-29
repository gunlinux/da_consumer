from redonats.domain.formatting import format_donation
from redonats.domain.models import Donation


def test_format_donation() -> None:
    donation = Donation(
        id=1,
        amount=12.5,
        currency="RUB",
        username="alice",
        message="hello",
        created_at="2026-08-29T10:00:00Z",
    )
    assert format_donation(donation) == (
        "[2026-08-29T10:00:00Z] alice: 12.50 RUB — hello"
    )
