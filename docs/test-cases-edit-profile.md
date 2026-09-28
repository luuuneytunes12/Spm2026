# Test Cases — Edit User Profile

Covers one product backlog item:

- **Edit User Profile.** *As a registered user (Event Organiser, Event
  Coordinator, Venue Staff, or Technical Support Staff), I want to update my
  own profile details (name, organisation, contact details, communication
  preferences), so that the people I work with in the system have accurate
  contact details.*

Every acceptance criterion below maps to at least one test case, and every
automated test is named after the criterion it proves, so a criterion can be
traced to the code that verifies it.

## How to run

| Layer | Command | Needs |
|---|---|---|
| Backend (pytest) | `cd backend && uv run pytest -q` | nothing — in-memory SQLite |
| Components (Vitest) | `cd frontend && npm test` | nothing — jsdom, API mocked |
| End-to-end (Playwright) | `cd frontend && npm run test:e2e` | a local throwaway postgres |
| All of the above | push to any branch | GitHub Actions runs them |

See `docs/test-cases-organiser-event-requests.md` for how to stand up the
local Playwright database — it is the same one this story's e2e spec runs
against.

Tests assert what a **user experiences** — visible text, labels,
`aria-invalid` — never CSS class names, so restyling the app cannot turn a
passing test red.

---

## AC1 — updating any profile field saves it and reflects it immediately

> *Given a registered user is on their profile page, when he updates any of
> the profile fields (name, organisation, contact info, and communication
> preference) and clicks save, then the changes are saved and reflected
> directly on his profile page.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-EP-1a | Updating name and organisation saves both | pytest | `test_updates_name_and_organisation` |
| TC-EP-1b | Updating the email address saves it | pytest | `test_updates_email` |
| TC-EP-1c | Updating phone and communication preference saves both | pytest | `test_updates_phone_and_communication_preference` |
| TC-EP-1d | A field not included in the request is left untouched | pytest | `test_partial_update_leaves_other_fields_untouched` |
| TC-EP-1e (form pre-fill) | The form is pre-filled with the current profile | Vitest | `Profile.test.tsx` › *pre-fills the form with the current profile* |
| TC-EP-1e (save) | Saving shows what was submitted and a confirmation | Vitest | `Profile.test.tsx` › *saves the edited fields and shows a confirmation* |
| TC-EP-1e | In a browser: edit fields, save, see them reflected without reload | Playwright | `edit-profile.spec.ts` › TC-EP-1e |

### AC1 boundary

| Test | Covers |
|---|---|
| `test_change_is_reflected_on_the_next_read` | The change is visible on a fresh read of the profile (`/auth/me`), not just in the response of the save itself. |

---

## AC2 — an invalid email format is rejected and nothing is saved

> *Given a registered user enters an email address in an invalid format
> (e.g. missing @ symbol or domain), when he attempts to save, then an error
> message identifying the email field is shown and no changes are saved.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-EP-2a | An invalid email is rejected and the rest of the request is not saved | pytest | `test_invalid_email_format_is_rejected` |
| TC-EP-2b | An email already used by another account is rejected (409) | pytest | `test_email_already_registered_to_another_user_is_rejected` |
| TC-EP-2a (UI) | The email field is flagged and the server's message is shown | Vitest | `Profile.test.tsx` › *flags the email field and shows the server error* |
| TC-EP-2c | In a browser: an invalid email blocks the save, nothing persists | Playwright | `edit-profile.spec.ts` › TC-EP-2c |

---

## AC3 — an invalid phone number is rejected and nothing is saved

> *Given a registered user enters a phone number that does not match the
> required format (e.g. contains letters, or is not a valid number of
> digits for the selected country code), when he attempts to save, then an
> error message identifying the phone number field is shown and no changes
> are saved.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-EP-3a | A phone number containing letters is rejected | pytest | `test_phone_number_with_letters_is_rejected` |
| TC-EP-3b | A phone number with the wrong digit count for its country code is rejected | pytest | `test_phone_number_with_wrong_digit_count_for_country_is_rejected` |
| TC-EP-3c | An unsupported country code is rejected | pytest | `test_unsupported_country_code_is_rejected` |
| TC-EP-3d | A phone number valid for its country code is accepted | pytest | `test_phone_number_valid_for_its_country_code_is_accepted` |
| TC-EP-3a (UI) | The phone field is flagged when it contains letters | Vitest | `Profile.test.tsx` › *flags the phone field when it contains letters* |
| TC-EP-3b (UI) | The phone field is flagged when the digit count is wrong | Vitest | `Profile.test.tsx` › *flags the phone field when the digit count is wrong for the country* |
| TC-EP-3e | In a browser: a phone number with letters blocks the save, nothing persists | Playwright | `edit-profile.spec.ts` › TC-EP-3e |

The supported country codes and their expected digit counts live in exactly
one place — `PHONE_DIGIT_RANGE` in `backend/app/core/phone.py`. The form
holds no copy of the validation rule, only the same list for the `<select>`
and the hint text, so the two cannot silently drift apart.

### AC3 additional case

| Test | Covers |
|---|---|
| `test_phone_number_without_a_country_code_is_rejected` | A number sent without a country code (or vice versa) is refused rather than silently accepted with an ambiguous format. |

---

## AC4 — a saved profile change persists across logout/login

> *Given that a registered user has saved profile changes, when he logs out
> and signs back in again, then his updated profile page is still displayed
> correctly.*

| ID | Test case | Type | Where |
|---|---|---|---|
| TC-EP-4a | A saved change is still present after a logout/login cycle | pytest | `test_profile_update_persists_across_logout_and_login` |
| TC-EP-4b | In a browser: log out, log back in, the saved value is still shown | Playwright | `edit-profile.spec.ts` › TC-EP-4b |

This is a thin criterion to test in isolation, since nothing about
login/logout is profile-specific — it is proved by combining the existing
auth flow (`backend/tests/test_auth.py`) with a write that outlives the
request that made it (an ordinary database commit).

---

## Additional cases beyond the acceptance criteria

| Test | Covers |
|---|---|
| `test_unauthenticated_request_is_rejected` | A signed-out request cannot edit anyone's profile. |
| `test_blank_name_is_rejected` | Boundary: whitespace-only counts as blank, mirroring the events form's treatment of empty required fields. |
| `test_unsupported_communication_preference_is_rejected` | An unrecognised preference value is refused rather than silently stored. |
| Vitest › *shows a fallback message when the server cannot be reached* | A network failure (not a validation error) shows a distinct, honest message. |

---

## Manual test script

The only case left to a human: visual judgement, which no assertion
captures well.

**Setup:** `cd backend && uv run uvicorn app.main:app --reload` and
`cd frontend && npm run dev`, then sign in as any registered user.

| # | Step | Expected result | Pass/Fail |
|---|---|---|---|
| 1 | Open **My profile** from the sidebar | Form shows name, organisation, email, phone (country + number), communication preference, all pre-filled | |
| 2 | Change a field and click **Save changes** | A confirmation message appears; the field keeps the new value | |
| 3 | Reload the page | The new value is still there | |
| 4 | Enter an email with no `@` and save | An error appears naming the email field; the email input is visibly marked | |
| 5 | Pick a country code, type a phone number with letters, and save | An error appears naming the phone field | |
| 6 | Pick Singapore (+65) and type 3 digits, save | Rejected — 8 digits are required for Singapore | |
| 7 | Log out, log back in, revisit **My profile** | Every earlier change is still shown | |
| 8 | Narrow the window to roughly phone width | No horizontal scrolling; the country/number fields stack rather than squash | |
| 9 | Switch the OS or browser theme to dark | All text remains legible; the flagged-field colour is still clearly an error | |

**Tester:** ______________  **Date:** ____________  **Build/commit:** ____________

---

## Evidence for submission

Every CI run attaches downloadable artefacts:

- `pytest-results.xml` — JUnit results for the backend suite.
- `playwright-report/` — HTML report with traces and screenshots of any
  failure.
