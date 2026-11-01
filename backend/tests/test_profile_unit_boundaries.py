"""SCRUM-18 and SCRUM-19: unit boundaries for profile input validation.

These tests exercise the input schema without a database or HTTP server.
The existing profile API tests separately verify persistence and atomicity.
The lengths below are explicit examples from the supported phone rules and
the responsibilities limit, so off-by-one regressions are easy to locate.
"""

import pytest
from pydantic import ValidationError

from app.schemas.user import UserProfileUpdate


@pytest.mark.parametrize(
    ("country", "digits", "valid"),
    [
        pytest.param("+65", 7, False, id="singapore-below"),
        pytest.param("+65", 8, True, id="singapore-exact"),
        pytest.param("+65", 9, False, id="singapore-above"),
        pytest.param("+60", 8, False, id="malaysia-below"),
        pytest.param("+60", 9, True, id="malaysia-minimum"),
        pytest.param("+60", 10, True, id="malaysia-maximum"),
        pytest.param("+60", 11, False, id="malaysia-above"),
    ],
)
def test_scrum18_ac3_phone_length_boundaries(country, digits, valid):
    """Accept both ends of each country's range and reject adjacent lengths."""
    number = "9" * digits
    if valid:
        assert UserProfileUpdate(phone_country_code=country, phone_number=number).phone_number == number
    else:
        with pytest.raises(ValidationError) as error:
            UserProfileUpdate(phone_country_code=country, phone_number=number)
        assert any(item["loc"] == ("phone_number",) for item in error.value.errors())


@pytest.mark.parametrize("length", [999, 1000])
def test_scrum19_ac3_responsibilities_at_and_below_limit(length):
    """Accept the maximum responsibilities length and one character below it."""
    text = "x" * length
    assert UserProfileUpdate(responsibilities=text).responsibilities == text


def test_scrum19_ac3_responsibilities_above_limit():
    """Reject one character beyond the limit and identify the offending field."""
    with pytest.raises(ValidationError) as error:
        UserProfileUpdate(responsibilities="x" * 1001)
    assert any(item["loc"] == ("responsibilities",) for item in error.value.errors())
