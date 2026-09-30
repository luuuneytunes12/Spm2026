1. Acceptance Criteria & Story Completion
   All ACs satisfied and demonstrated to the Product Owner
   Product Owner has reviewed and accepted the story
2. Testing — Automated
   Backend unit tests: pytest passing (in-memory SQLite for speed)
   Backend integration tests: pytest passing against the production database engine (e.g. Postgres via Testcontainers), wherever the story touches persistence, transactions, or conflict handling
   Frontend: Vitest passing (jsdom, API mocked)
   End-to-end: Playwright passing, wherever the story touches DB + UI
   Every AC maps to ≥1 test, named after the AC it proves (traceability)
3. Testing — Negative & Edge Cases
   Access-denied path tested (wrong role / wrong org / not-yours data)
   No data or notifications reach users outside the intended role, org, or recipient set (explicit negative test)
   Invalid status transition blocked, state unchanged, error shown
   Field-level input validation tested (bad format blocks save, no partial write)
   Duplicate/repeat action handled correctly (idempotency)
   Resource conflicts tested with concurrent requests, not just sequential ones (double-booking, overcommitted equipment), run against the production database engine
4. Audit Trail (if the story changes state)
   Actor identity and timestamp recorded on the action
   Log entry is read-only / immutable
5. Data & Persistence
   Data persists correctly across logout/login and reload
   Reason/comment captured where the AC requires one (e.g. rejection reason)
   Schema changes include a migration that applies cleanly to a copy of the current schema and has a working downgrade
6. Code Quality & CI
   Code reviewed via PR (no direct pushes to main)
   CI green: lint, type-check, build, and all test layers
   uv.lock / package-lock.json in sync with dependencies
   Secret scanning passes in CI (e.g. gitleaks); no secrets or .env values committed
7. Security
   Authorization enforced server-side, not only hidden in the UI
   pip-audit and npm audit report no new high or critical vulnerabilities
8. Accessibility (if the story changes UI)
   Automated axe checks pass in Playwright with no serious or critical violations
   New UI is keyboard-navigable, with visible focus and labelled form fields
9. Documentation
   Docs / C4 architecture views updated when the story adds or changes an endpoint, adds a container or service, changes data flow between components, or adds/changes environment variables
   .env.example updated when environment variables change
10. Deployment
    Deployed to the staging/test environment
    Smoke-tested there
    Integrated into the Increment
