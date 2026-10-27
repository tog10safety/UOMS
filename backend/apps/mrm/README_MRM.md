# Mission Risk Management (MRM) — Django module

Port of the legacy Flask "MRM system" into UOMS. Backend: `apps/mrm` (this folder).
Frontend: `frontend/src/pages/mrm/*`, `frontend/src/api/mrmApi.ts`, `frontend/src/components/mrm/*`.

## Setup

```bash
cd backend
python manage.py migrate                 # accounts 0003 + mrm 0001
python manage.py test apps.mrm           # needs PostgreSQL/PostGIS — see "Running the tests on PostgreSQL"
```

1. In **User Management**, give each user their MRM **authority** and (where relevant) **decision designation**.
   Users with the UOMS `ADMIN` role automatically act as MRM Administrators.
2. Every approver needs a **signature** (Account → MRM Signature) — approving without one is refused.
3. Optional: `MRM_REQUIRE_FOR_MISSION_APPROVAL=True` in `.env` disables the old quick approve/reject
   endpoints for missions that have no MRM, so *all* mission risk approval goes through MRM.

### Migrating the legacy Flask data

```bash
python manage.py import_flask_mrm --dsn "postgresql://user:pass@host/mrm_db" \
    --static-dir  /old/mrm/static \
    --signatures-dir /old/mrm/signatures \
    --pdf-dir /old/mrm/approved_pdfs \
    --dry-run            # remove --dry-run to commit
```
Idempotent. Matches units by name and users by username; never overwrites an existing UOMS account's role/unit/password.
PBKDF2 password hashes are converted (users keep their password); scrypt hashes cannot be, so those users get
`must_change_password` and an administrator/USO resets them. Approved MRMs keep the tier they were signed at —
any that the official matrix would have escalated further are **listed in the report for safety review**.

## Authority model (kept from the legacy system)

| MRM authority | May |
|---|---|
| Administrator (= UOMS ADMIN) | everything, all units |
| Unit Safety Officer | read forms & manage hazards/users/feedback for assigned units + sub-units; analytics; logos |
| Evaluator | create forms; review forms assigned to them; manage own-unit hazards |
| Creator | create/submit/edit own forms; read own-unit hazards |
| *(none)* | see only approved MRMs they are tagged on, to give feedback |

Decision designations (Operator → Commander) are separate and decide who can *approve* at each residual-risk tier:
≤50% Operator (the creator) · 51–65% Supervisor (the reviewing evaluator) · 66–75% Squadron Commander ·
76–85% Director for Operations · 86–100% Commander.

UOMS role still gates the module (`MISSIONS: VIEW`) and UOMS `COMMANDER` keeps read-only oversight of all units.

## Adjustments made for UOMS (and why)

1. **One risk matrix.** The legacy app scored risk three different ways; the raw-score shortcut disagreed with the
   official matrix (`risk_matrix.png`) on 5E, 4E and 1A, so approval authority could be under-escalated. All paths now use
   the official matrix (`risk.py`). The "Commander" tier (>85%) was also unreachable on save; it is now reachable.
2. **MRM ↔ Mission.** An MRM can be linked to a UOMS mission and then drives its `risk_review_status`/`status`,
   approval log, risk levels (`overall_risk_level`, new `overall_residual_risk_level`) and a dashboard Risk Alert for
   elevated-risk forms. The old quick approval endpoints defer to the MRM when one exists.
3. **Users/units are UOMS's**, not duplicated. Rank/service number come from the linked Personnel record.
4. **Approver lookup walks up the unit hierarchy** (a Wing's Director for Operations can approve a Squadron's MRM) and
   never picks the creator/reviewer for higher tiers. Unfilled designations are surfaced ("needs approver") and can be fixed by
   an Administrator/USO — the legacy app silently left such forms stuck.
5. **Hazards are snapshotted** onto each MRM, so editing the registry can't change an approved record or its PDF.
   Overriding a hazard's residual risk away from the registry value requires a written justification.
6. **Rejected / needs-revision forms can be revised and re-submitted** (legacy dead-ended). Editing after signatures resets them.
7. **Separation of duties:** a creator can never be their own reviewer (legacy allowed it for Evaluators).
8. **Soft delete + event timeline** (`MRMEvent`) replace hard deletes and the `edit_history` blob; actions also go to the UOMS `AuditLog`.
9. Hazard registry: Evaluators were not unit-scoped on edit/delete/bulk-delete in the legacy app (cross-unit IDOR) — now enforced.
   Hazards from mother units are selectable ("inherited library").
10. Feedback: reviewers must supply likelihood/severity when creating a registry hazard from feedback (legacy invented 3C/2D).
11. State-changing actions are `POST` (legacy submitted forms via `GET`).

### Security fix in existing UOMS code
`PATCH /auth/me/` used the full user serializer, so any user could set their own `role`, `unit` or MRM authority.
It now accepts only first/last name, email and phone.

## Not ported (superseded by UOMS or out of scope)
Flask login/session/CSRF/rate-limit (UOMS uses JWT) · 90-day password expiry (UOMS has none — consider adding) ·
user/unit CRUD pages (UOMS User Management & Units) · cache/DB-maintenance/debug routes · legacy chart pages
(replaced by `GET /mrm/analytics/`) · bulk MRM-PDF zip download · "send reminders" (the API lists who owes feedback; there is no
notification channel yet) · bulk hazard delete has an API (`hazards/bulk-delete/`) but no UI.

---

# Integration architecture, data ownership and runbook

## Ownership (single source of truth)

| Data | Owner | How other modules use it |
|---|---|---|
| Identity, login, role, active status | `accounts.User` (UOMS) | everything references it by FK; no second user table |
| MRM authority / designation / signature | `accounts.User` fields, enforced by `apps.mrm.access` | read via `User.effective_mrm_authority` |
| Person, rank, service number, unit | `personnel.Personnel` / `personnel.Unit` | MRM reads rank via `User.personnel_record` |
| Risk assessment, hazards, approval chain, feedback | `apps.mrm` | missions only *read* it (`Mission.active_mrm`) |
| Mission schedule, location, commander, status | `missions.Mission` | MRM may advance `status` PLANNED → APPROVED on approval |
| Mission risk level | **derived** from the MRM (`overall_risk_level`, `overall_residual_risk_level`) | never stored |
| Mission `risk_review_status` + `submitted_*`/`reviewed_*`/`review_comments` + `MissionApprovalLog` | **MRM** — columns are a *read-only projection* | API ignores writes; `check_mrm_consistency [--fix]` detects drift |
| Legacy `HazardAssessment` | frozen | write-blocked once a mission has an MRM (or when `MRM_REQUIRE_FOR_MISSION_APPROVAL=True`) |
| Dashboard `RiskAlert` | UOMS (`apps.risk`) | the MRM creates/resolves alerts titled `[MRM <number>] …` |

### Why the Mission columns are not dropped yet
Dropping them is irreversible and the legacy quick path (missions without an MRM) still writes them. They are therefore now a
**read-only projection** maintained only by the MRM services and verifiable with `check_mrm_consistency`.
Drop them in a *later* release, only after: (1) `MRM_REQUIRE_FOR_MISSION_APPROVAL=True` has run in production,
(2) `check_mrm_consistency` reports no drift, (3) the remaining readers are updated (reports and the admin screen now use the MRM-derived values; only `seed_demo_data.py` still writes the legacy fields), and
(4) you have a verified backup.

## Schema mapping (legacy Flask → UOMS)

| Flask table | UOMS table | Notes |
|---|---|---|
| `users` | `accounts_user` (+ `personnel_personnel` for rank/serial) | matched by email / service number; **never by name**; PBKDF2 hashes converted |
| `units` | `personnel_unit` | matched by name/acronym; hierarchy from `parent_id` |
| `unit_assignments` | `mrm_safetyofficerassignment` | |
| `unit_logos` | `mrm_unitlogo` | files copied |
| `hazard_registry` | `mrm_hazard` | `legacy_id` keeps the old id; ratings recomputed |
| `mrm_forms` | `mrm_mrmform` | `legacy_id`; `edit_history` → first `mrm_mrmevent` |
| `mission_hazards` | `mrm_missionhazard` | only *selected* rows; values snapshotted |
| `mrm_personnel` | `mrm_mrmpersonnel` | |
| `mrm_feedback`, `feedback_notifications` | `mrm_mrmfeedback`, `mrm_feedbacknotification` | |
| `user_activity` | `core_auditlog` (not imported) | history stays in the old DB |

Primary keys: UOMS uses UUIDs; legacy integer ids are kept in `legacy_id` on hazards, forms and feedback so the import is idempotent.

## Account policy
* One account per person. Ambiguous legacy accounts are **not imported** and are listed for a human decision (`--identity-map`).
* Every change to role, unit, section, MRM authority/designation, active status or superuser flag is written to the audit log with before/after values.
* A user cannot be deactivated (by an admin, the API, or a Safety Officer) while a form is waiting on them for review or approval, and nobody can
  deactivate themselves. Reassign first: **Reassign reviewer** (while awaiting review) or **Assign approver** (while awaiting approval).

## Commands

```bash
# 0. BACK UP FIRST (both databases)
pg_dump -Fc -h HOST -U USER uoms   > uoms_before_mrm_$(date +%F).dump
pg_dump -Fc -h HOST -U USER mrm_db > mrm_legacy_$(date +%F).dump

# 1. schema (adds accounts.0003 + mrm.0001; no existing column or table is changed or dropped)
cd backend && python manage.py migrate
python manage.py test apps.mrm

# 2. rehearse the data import — nothing is saved
python manage.py import_flask_mrm --dsn "postgresql://USER:PASS@HOST/mrm_db" \
    --static-dir /old/static --signatures-dir /old/signatures --pdf-dir /old/pdfs \
    --dry-run --identity-review-out identity_review.json

# 3. resolve ambiguous accounts: edit identity_review.json, e.g. {"jdoe": "john.doe"}  (or "NEW")
# 4. run for real (idempotent — safe to repeat)
python manage.py import_flask_mrm --dsn ... --identity-map identity_review.json

# 5. after go-live
python manage.py check_mrm_consistency          # add --fix to repair a drifted mission projection

# frontend / backend
cd frontend && npm install && npm run dev       # or npm run build
cd backend  && python manage.py runserver
```

## Rollback
* **Before step 4 (import):** nothing to undo — `--dry-run` rolls back, and `migrate` only *adds* columns/tables.
* **After import:** restore `uoms_before_mrm_*.dump` (`pg_restore -c -d uoms …`). The legacy DB is never written to.
* **Schema only:** `python manage.py migrate mrm zero && python manage.py migrate accounts 0002` removes the MRM tables and the three
  new `accounts_user` columns (tested; existing accounts survive both directions).
* **Enforcement flag:** set `MRM_REQUIRE_FOR_MISSION_APPROVAL=False` to re-enable the quick approval path instantly.

## Running the tests on PostgreSQL
The project is PostgreSQL/PostGIS only (`django.contrib.gis.db.backends.postgis`); there is no SQLite configuration and none should be added.
```bash
cd backend
./run_tests_postgres.sh                  # starts postgis/postgis:16 via docker-compose and runs `manage.py test apps.mrm`
# or against your own server:
DB_HOST=… DB_PORT=5432 DB_NAME=uoms DB_USER=… DB_PASSWORD=… ./run_tests_postgres.sh
```
The DB user needs `CREATEDB` and the right to `CREATE EXTENSION postgis` (the test runner builds a throw-away `test_<DB_NAME>`).
`test_postgres_safety.py` additionally enforces PostgreSQL's column-length and strict-UUID rules in Python.

## Verification status (be aware)
Verified in this build: 98 automated tests, with every UOMS app (aircraft, vehicles, armory, inventory, GIS, reports, dashboard) loaded and all migrations applied together — **but only on a development stand-in database in a sandbox that had no PostgreSQL server. That is NOT a PostgreSQL result.** Run `./run_tests_postgres.sh` to get one (workflow, authority, scoping, identity matching, audit, deactivation, freeze, projection drift,
migration forward/back, import idempotency), Django system check, no pending migrations, frontend type-check.
**Not verified:** running on real PostgreSQL/PostGIS (see above — the single most important check still to do), the other UOMS modules (aircraft, vehicles, armory,
inventory, GIS, reports — they have no test suite and could not be exercised without PostGIS), a built frontend in a browser, and the import against
your real Flask database. Run `python manage.py test apps.mrm` and a manual smoke test of those modules on staging before production.
