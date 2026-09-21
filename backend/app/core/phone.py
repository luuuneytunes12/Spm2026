"""Curated phone country codes and their expected national-number length.

Not exhaustive -- a reasonable set of countries for this project's scope,
not a general-purpose phone library. Mirrored (identical dial codes and
digit ranges) in `frontend/src/lib/phone.ts`; keep both in sync if this
list changes.

Each entry is (dial code, label, (min_digits, max_digits)) for the
*national* number, i.e. everything typed after the dial code, digits only.
A single fixed length is expressed as min == max.
"""

PHONE_COUNTRY_CODES: list[tuple[str, str, tuple[int, int]]] = [
    ("+65", "Singapore", (8, 8)),
    ("+60", "Malaysia", (9, 10)),
    ("+1", "US/Canada", (10, 10)),
    ("+44", "United Kingdom", (10, 10)),
    ("+61", "Australia", (9, 9)),
    ("+91", "India", (10, 10)),
    ("+86", "China", (11, 11)),
    ("+81", "Japan", (10, 10)),
    ("+62", "Indonesia", (9, 12)),
    ("+63", "Philippines", (10, 10)),
    ("+66", "Thailand", (9, 9)),
    ("+84", "Vietnam", (9, 10)),
    ("+852", "Hong Kong", (8, 8)),
    ("+886", "Taiwan", (9, 9)),
    ("+82", "South Korea", (9, 10)),
    ("+49", "Germany", (10, 11)),
    ("+33", "France", (9, 9)),
    ("+971", "United Arab Emirates", (9, 9)),
    ("+64", "New Zealand", (8, 9)),
    ("+966", "Saudi Arabia", (9, 9)),
]

# Fast lookup used by validation: dial code -> (min_digits, max_digits).
PHONE_DIGIT_RANGE: dict[str, tuple[int, int]] = {
    code: digit_range for code, _label, digit_range in PHONE_COUNTRY_CODES
}
