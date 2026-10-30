/**
 * Provides a shared future year for related event and venue fixtures.
 * A shared date keeps bookings and event windows aligned, while staying valid
 * when the suite is run in a later calendar year.
 */
export const E2E_TEST_YEAR = new Date().getFullYear() + 2
