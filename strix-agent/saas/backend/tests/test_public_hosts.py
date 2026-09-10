import pytest

from app.public_hosts import live_https_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("app.example.com", "https://app.example.com"),
        ("https://app.example.com", "https://app.example.com"),
        ("https://app.example.com/", "https://app.example.com"),
        ("http://app.example.com/api", "https://app.example.com/api"),
        (
            "https://api-dev.techsophy.com/api/awgment-eqms/openproject",
            "https://api-dev.techsophy.com/api/awgment-eqms/openproject",
        ),
        (
            "https://https://api-dev.techsophy.com/api/awgment-eqms/openproject",
            "https://api-dev.techsophy.com/api/awgment-eqms/openproject",
        ),
        ("api.example.com/v1", "https://api.example.com/v1"),
    ],
)
def test_live_https_url_normalizes_hosts_and_pasted_urls(raw: str, expected: str) -> None:
    assert live_https_url(raw) == expected


def test_live_https_url_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        live_https_url("   ")
