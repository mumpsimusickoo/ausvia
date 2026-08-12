# Phase 7 Remediation

**Ausbildung Career Agent** · 12 August 2026
**Verdict: 12 of 12 findings resolved** (3 Blocking, 9 Worth Fixing Now)

Every Blocking and Worth Fixing Now finding from the Phase 7 QA pass has been fixed, tested, and re-verified live against the running dev server — not just read from code. The three blocking issues (a crash on document deletion, no way to navigate on a phone, and a landing page that cut off mid-word on mobile) are gone; all nine smaller accessibility and correctness findings are closed alongside them.

| Tests passing | Blocking fixed | Worth-fixing done | Pages, no overflow |
|---|---|---|---|
| 135/135 | 3/3 | 9/9 | 10/10 |

---

## Blocking, now fixed

### B1 — Deleting a document no longer crashes application generation
Deleting a document still selected on an application threw an unhandled 500 the moment you tried to generate an email or approve the package.

**Fix:** `Document` now cascades to its `ApplicationDocument` rows, and SQLite foreign-key enforcement is on for good — this whole class of orphaned-record bug now fails loudly in dev/test instead of silently corrupting data in production. Regression test added.

### B2 — A phone user can now reach every page, not just the one they landed on
The sidebar was `hidden` below 768px with nothing in its place — no way to move between Dashboard, Applications, Documents, or anywhere else.

**Fix:** a sticky top bar with a hamburger opens a slide-over drawer mirroring every desktop destination, including admin links for admin users. Verified live: focus moves into the drawer on open and back to the trigger on close, Escape and backdrop-click both close it, screen readers get proper `aria-expanded`/`role="dialog"` state.

### B3 — The landing page no longer cuts off mid-word on a phone
At 390px, the headline, both CTA buttons, and the hero graphic were all sliced off at the right edge — unreadable without a sideways scroll most visitors would never find.

**Fix:** root-caused to the hero's percentage-positioned labels and fixed at the source, not papered over with `overflow-x: hidden`. Confirmed with real mobile-viewport emulation that the page's rendered width now exactly matches the 390px viewport.

Screenshots: `screenshots/phase7-remediation/01-landing-mobile-390.png`, `03-dashboard-mobile-nav-open.png`

---

## Worth Fixing Now — all nine closed

| # | Finding | Fix |
|---|---|---|
| W1 | Invitation-code race | Redemption is now an atomic conditional `UPDATE` — two concurrent requests can no longer both redeem the same single-use admin code. |
| W2 | FK enforcement never enabled | Same fix as B1 — `PRAGMA foreign_keys=ON` is now on for every connection. |
| W3 | Leaked error detail | Background-task failures now show a plain message to the user; full exception detail (including server file paths) stays server-side in logs. |
| W4 | Color-only status markers | "Skipped" and "not reached yet" now differ by size, ring weight, and fill — not color alone. |
| W5 | Color-only flash messages | Flash messages now carry an icon plus `role="alert"`/`aria-live`, so a screen reader announces them. |
| W6 | Unlabeled form fields | All six previously proximity-only-labeled fields now have real `for`/`id` associations. |
| W7 | Unlinked validation errors | Field errors are now `aria-describedby`-linked in the one shared macro every form uses. |
| W8 | Soft prompt delimiting | Untrusted external text in AI prompts now sits behind structural fencing, not just a text label — plus a new adversarial injection test. |
| W9 | Application-detail overflow | Closed by the same B3 root-cause fix and the full-page audit below. |

---

## Mobile overflow — every page audited

Beyond the landing page and application detail, every other authenticated page was checked for genuine page-level overflow — real `scrollWidth` vs. viewport width, not a screenshot guess.

| Page | Route | 390px |
|---|---|---|
| Dashboard | `/dashboard` | ✅ clean |
| Candidate profile | `/profile/` | ✅ clean |
| Documents | `/documents/` | ✅ clean |
| Job search | `/jobs/` | ✅ clean |
| Saved jobs | `/jobs/saved` | ✅ clean |
| Applications list | `/applications/` | ✅ clean |
| Job detail | `/jobs/<id>` | ✅ clean |
| Company detail | `/companies/<id>` | ✅ clean |
| Application detail | `/applications/<id>` | ✅ clean |
| Gmail integration | `/integrations/gmail` | ✅ clean |

---

## Verification

**Test suite** — full suite re-run after every change, no regressions, nothing skipped or weakened to get there:

```
$ pytest -q
135 passed in 50.62s   (113 baseline + 22 new)
```

**Reusable verification script** — the overflow audit above is now a repeatable script rather than a one-off pass. It drives a local Edge/Chrome install over the DevTools protocol and asserts real `scrollWidth`-vs-viewport overflow, no browser-automation framework required:

```
$ python scripts/check_mobile_overflow.py --email you@example.com --password '...'
```

One tooling bug worth flagging for anyone reusing it: Edge silently re-execs itself under a new PID on launch, which broke naive process cleanup. Fixed at the root (`--edge-skip-compat-layer-relaunch`) so the script tears down cleanly on its own.

**Screenshots** — full set in `screenshots/phase7-remediation/`: landing page and dashboard at 390px, the mobile nav drawer open, and the desktop dashboard at 1280px confirming the new mobile top bar correctly disappears above the `md` breakpoint.
