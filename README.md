# UOMS — Unit Operations Management System
## Phase 1 Deliverable: Architecture, Auth, RBAC, Personnel, Dashboard

---

## 1. Folder Structure

```
uoms/
├── docker-compose.yml            # PostGIS database container
├── .gitignore
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example              # copy to .env and fill in secrets
│   ├── config/
│   │   ├── settings.py           # PostGIS, DRF, JWT, CORS, Swagger config
│   │   ├── urls.py               # root URL routing
│   │   ├── wsgi.py / asgi.py
│   └── apps/
│       ├── core/                 # BaseModel, AuditLog, RBAC permissions, middleware
│       │   ├── models.py
│       │   ├── middleware.py     # auto audit-logging
│       │   ├── audit.py          # log_action() helper
│       │   ├── permissions.py    # IsAdmin, ReadOnlyOrAdmin, etc.
│       │   ├── pagination.py
│       │   └── management/commands/seed_demo_data.py
│       ├── accounts/              # Custom User model, JWT auth, user/role mgmt
│       │   ├── models.py          # User (role, unit, RBAC)
│       │   ├── managers.py
│       │   ├── serializers.py
│       │   ├── views.py           # login/logout/refresh/me/users CRUD
│       │   └── urls.py
│       ├── personnel/             # Personnel Management module (full CRUD)
│       │   ├── models.py          # Rank, Unit, Position, Qualification, Personnel
│       │   ├── serializers.py
│       │   ├── views.py
│       │   └── urls.py
│       ├── vehicles/              # minimal model — full module in later phase
│       ├── aircraft/              # minimal model — full module in later phase
│       ├── missions/              # minimal model — full module in later phase
│       ├── risk/                  # minimal model — full module in later phase
│       └── dashboard/             # aggregation endpoint for the main dashboard
│           ├── views.py
│           └── urls.py
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── tsconfig.json
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx                # routes
        ├── index.css              # Tailwind + ops theme
        ├── api/
        │   ├── client.ts          # axios instance + JWT refresh interceptor
        │   └── endpoints.ts       # typed API calls
        ├── contexts/AuthContext.tsx
        ├── types/index.ts
        ├── components/
        │   ├── common/            # ProtectedRoute, StatCard, StatusBreakdown,
        │   │                      # RiskAlertsPanel, RecentActivityPanel, OperationalMap
        │   └── layout/            # Sidebar, Header, DashboardLayout
        └── pages/
            ├── Login.tsx
            ├── Dashboard.tsx
            ├── Personnel.tsx
            └── UserManagement.tsx
```

---

## 2. Database Schema (Phase 1)

**accounts_user** (custom User, AUTH_USER_MODEL)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| username | varchar unique | |
| email | varchar unique | |
| password | varchar | hashed |
| role | varchar(20) | ADMIN / COMMANDER / STAFF / OPERATOR / VIEWER |
| unit | varchar(150) | free-text AOR/unit scoping |
| phone_number | varchar(30) | |
| must_change_password | bool | |
| last_login_ip | inet | |
| is_active, is_staff, is_superuser | bool | |
| created_at, updated_at, last_login, date_joined | timestamp | |

Indexes: `role`, `unit`.

**personnel_rank** — id (UUID), name (unique), abbreviation (unique), order (int), is_active
**personnel_unit** — id, name (unique), code (unique), parent_unit_id (FK self, nullable), description
**personnel_position** — id, title (unique), description
**personnel_qualification** — id, name (unique), description, validity_period_days

**personnel_personnel**
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| service_number | varchar unique | |
| first_name, last_name, middle_name | varchar | |
| rank_id | FK → Rank (PROTECT) | |
| unit_id | FK → Unit (PROTECT) | |
| position_id | FK → Position (SET_NULL, nullable) | |
| status | varchar(20) | ACTIVE / ON_LEAVE / DEPLOYED / TRAINING / MEDICAL / SEPARATED |
| date_of_birth, date_enlisted | date | |
| contact_number, email | varchar | |
| photo | image | |
| linked_account_id | FK → User (SET_NULL, one-to-one, nullable) | |
| remarks | text | |
| is_active | bool | soft-delete |

M2M: `personnel_personnel_qualifications` (Personnel ↔ Qualification)

Indexes: `status`; `(unit_id, status)`; `(last_name, first_name)`.

**vehicles_vehicle** (minimal, expands in Vehicle Tracking phase)
id (UUID), plate_number (unique), make, model, vehicle_type, status (AVAILABLE/ON_MISSION/MAINTENANCE/OUT_OF_SERVICE), assigned_driver_id (FK → Personnel), **last_known_location** (PostGIS `POINT`, SRID 4326, geography), last_location_updated_at.

**aircraft_aircraft** (minimal): id, tail_number (unique), aircraft_type, flying_status (GROUNDED/SCHEDULED/IN_FLIGHT/MAINTENANCE).

**missions_mission** (minimal): id, name, status (PLANNED/APPROVED/ONGOING/COMPLETED/CANCELLED), **location** (PostGIS `POINT`), start_date, end_date.

**risk_riskalert**: id, mission_id (FK, nullable), title, description, severity (LOW/MEDIUM/HIGH/CRITICAL), is_resolved.

**core_auditlog** (append-only, admin read-only)
id (bigint PK), user_id (FK, SET_NULL), action (CREATE/UPDATE/DELETE/LOGIN/LOGIN_FAILED/LOGOUT/APPROVE/REJECT/ISSUE/RETURN/OTHER), model_name, object_id, method, path, ip_address (inet), description, metadata (JSONB), created_at.
Indexes: `-created_at`; `(user, -created_at)`; `(model_name, object_id)`.

All domain tables inherit a common `BaseModel` (UUID PK, `created_at`, `updated_at`, `is_active` soft-delete flag) for consistency.

---

## 3. Installation Commands

### Prerequisites
- Python 3.12+
- Node.js 20+
- PostgreSQL 15+ with PostGIS 3.4+ (or use the provided `docker-compose.yml`)
- GDAL/GEOS system libraries (required by GeoDjango)

### 3.1 Start the database
```bash
cd uoms
docker compose up -d
```
(Or point `.env` at your own PostgreSQL/PostGIS instance.)

### 3.2 Backend setup
```bash
cd uoms/backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env            # edit DJANGO_SECRET_KEY and DB_PASSWORD
```

Generate a real secret key:
```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
Paste the output into `DJANGO_SECRET_KEY` in `.env`.

### 3.3 Frontend setup
```bash
cd uoms/frontend
npm install
```

---

## 4. Migration Commands

```bash
cd uoms/backend
python manage.py makemigrations core accounts personnel vehicles aircraft missions risk
python manage.py migrate

# Create your own admin account (recommended over the seeded one for production):
python manage.py createsuperuser

# Optional: seed demo data (ranks, units, personnel, vehicles, aircraft, missions, alerts)
python manage.py seed_demo_data
```

`seed_demo_data` also creates a superuser `admin` / `ChangeMe!2024` **only if no `admin` user exists yet** — change that password immediately in a real deployment.

---

## 5. Running the App

```bash
# Terminal 1 — backend
cd uoms/backend
python manage.py runserver

# Terminal 2 — frontend
cd uoms/frontend
npm run dev
```

Frontend: http://localhost:5173 (proxies `/api` to Django on port 8000)
Backend admin: http://localhost:8000/admin/
API docs (Swagger UI): http://localhost:8000/api/docs/
API docs (ReDoc): http://localhost:8000/api/redoc/
Raw OpenAPI schema: http://localhost:8000/api/schema/

---

## 6. Test Instructions

### Backend — manual smoke test via curl
```bash
# 1. Log in (returns access + refresh JWT)
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"ChangeMe!2024"}'

# 2. Call a protected endpoint (replace <ACCESS_TOKEN>)
curl http://localhost:8000/api/v1/dashboard/summary/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"

# 3. List personnel
curl http://localhost:8000/api/v1/personnel/records/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"

# 4. Confirm RBAC: a VIEWER-role user gets 403 trying to create personnel
curl -X POST http://localhost:8000/api/v1/personnel/records/ \
  -H "Authorization: Bearer <VIEWER_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" -d '{...}'   # expect 403
```

### Backend — Django test runner
Phase 1 ships without a dedicated `tests.py` per app yet (added in Phase 2 alongside CI); in the meantime, `python manage.py check` validates the whole project (models, URLs, settings) and `python manage.py migrate --plan` confirms migrations are consistent.

### Frontend — manual walkthrough
1. Visit `/login`, sign in as `admin` / `ChangeMe!2024`.
2. Confirm the Dashboard loads stat cards, status breakdowns, the OpenLayers map (with seeded vehicle/mission points), risk alerts, and recent activity — all from one call to `/api/v1/dashboard/summary/`.
3. Visit **Personnel** — confirm the seeded records list and search works.
4. Visit **User Management** — confirm only ADMIN-role accounts can view it (log in as `viewer1` / `ChangeMe!2024` to see the access-denied state).
5. Sign out and confirm redirect to `/login`; confirm a stale/invalid token also redirects to `/login`.

> **Note on this environment:** the backend's Python files were verified with `python -m py_compile` (syntactically valid) but could not be run end-to-end here because this sandbox has no outbound network access to install PyPI/npm packages. Everything is written to run correctly against the versions pinned in `requirements.txt`/`package.json` — run the commands above in your own environment to bring it up.

---

## 7. API Documentation (Phase 1 endpoints)

All endpoints are prefixed `/api/v1/`. Full interactive docs at `/api/docs/`.

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/auth/login/` | none | Obtain JWT access + refresh tokens |
| POST | `/auth/refresh/` | none | Refresh an access token |
| POST | `/auth/logout/` | JWT | Blacklist refresh token |
| GET/PATCH | `/auth/me/` | JWT | Current user's own profile |
| POST | `/auth/change-password/` | JWT | Change own password |
| GET/POST | `/auth/users/` | JWT + ADMIN | List/create system accounts |
| GET/PUT/PATCH/DELETE | `/auth/users/{id}/` | JWT + ADMIN | Manage a specific account (DELETE = deactivate) |
| GET/POST | `/personnel/ranks/` | JWT | Rank reference data (write = ADMIN/COMMANDER) |
| GET/POST | `/personnel/units/` | JWT | Unit/AOR reference data |
| GET/POST | `/personnel/positions/` | JWT | Position reference data |
| GET/POST | `/personnel/qualifications/` | JWT | Qualification reference data |
| GET/POST | `/personnel/records/` | JWT | List/create personnel (filter: `unit`, `rank`, `position`, `status`; search: name/service number/email) |
| GET/PUT/PATCH/DELETE | `/personnel/records/{id}/` | JWT | Manage a personnel record (DELETE = deactivate) |
| GET | `/dashboard/summary/` | JWT | Aggregated dashboard payload (all widgets) |

**RBAC roles:** `ADMIN` (full access), `COMMANDER` (write access to operational data), `STAFF`, `OPERATOR`, `VIEWER` (read-only by default via `ReadOnlyOrAdmin`).

---

## 8. Phase 2 additions — Vehicle Tracking & Aircraft Flying Monitoring

**Vehicle Tracking and Monitoring** (`apps/vehicles`) — now full CRUD:
- `Vehicle` gained `year`, `capacity`, `fuel_type`, `odometer_km`, `assigned_mission`
- `VehicleLocationUpdate` — an immutable location/speed/heading trail (`POST /vehicles/registry/{id}/location/`, `GET .../location-history/`)
- `Trip` — trip history with odometer-based distance calculation and RBAC-protected writes
- `VehicleMaintenanceRecord` — maintenance log; logging a REPAIR/PREVENTIVE record auto-flips an AVAILABLE vehicle to MAINTENANCE status

**Aircraft Flying Monitoring** (`apps/aircraft`) — now full CRUD:
- `Aircraft` gained `manufacturer`, `model`, `capacity`, `base_unit` (AOR visibility)
- `Flight` — flight scheduling with origin/destination (+ optional PostGIS points), scheduled vs. actual departure/arrival, CAAP flight-plan fields, and `unit` for AOR-scoped visibility
- `FlightCrewAssignment` — aircrew roster per flight (PIC, co-pilot, loadmaster, etc.)
- `FlightWaypoint` — ordered itinerary stops
- Departure/arrival monitoring actions: `POST /aircraft/flights/{id}/depart/` and `.../arrive/` — these also flip the aircraft's flying status automatically and are audit-logged

**New API endpoints** (all under `/api/v1/`):

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/vehicles/registry/` | Vehicle registry |
| POST | `/vehicles/registry/{id}/location/` | Report a new location/status ping |
| GET | `/vehicles/registry/{id}/location-history/` | Location trail (last 200 pings) |
| GET/POST | `/vehicles/trips/` | Trip history |
| GET/POST | `/vehicles/maintenance/` | Maintenance records |
| GET/POST | `/aircraft/registry/` | Aircraft registry |
| GET/POST | `/aircraft/flights/` | Flight schedule |
| POST | `/aircraft/flights/{id}/depart/` | Mark flight departed |
| POST | `/aircraft/flights/{id}/arrive/` | Mark flight arrived |
| GET/POST | `/aircraft/flights/{id}/crew/` | View/assign aircrew |
| GET/POST | `/aircraft/flights/{id}/waypoints/` | View/add itinerary waypoints |
| GET/POST | `/aircraft/crew-assignments/` | Direct CRUD on crew assignments |

**Frontend**: `/vehicles` (registry table + live OpenLayers map of vehicle positions, status filter) and `/aircraft` (aircraft registry + flight schedule table with role-gated "Mark Departed"/"Mark Arrived" buttons) are now enabled in the sidebar.

**Re-run migrations after pulling Phase 2:**
```bash
python manage.py makemigrations vehicles aircraft
python manage.py migrate
python manage.py seed_demo_data   # now also seeds a trip, a maintenance record, and a flight
```

---

## 9. Phase 3 additions — Mission Risk Management

**Mission Risk Management** (`apps/missions`) — Mission moves from a Phase 1/2 stub to a full profile with an integrated risk-assessment and approval workflow:

- `Mission` gained `description`, `unit` (AOR), `mission_commander`, and the approval-workflow fields (`risk_review_status`, `submitted_by/at`, `reviewed_by/at`, `review_comments`)
- `HazardAssessment` — one row per identified hazard on a mission: `category`, `probability` × `severity` → **auto-computed `initial_risk_level`** via a standard 5×4 Risk Assessment Code (RAC) matrix, `existing_controls`, `additional_controls`, and an optional re-assessed `residual_probability`/`residual_severity` → **auto-computed `residual_risk_level`**. The risk level is computed server-side in `HazardAssessment.save()` — never trust a client-supplied risk level.
- `Mission.overall_risk_level` / `overall_residual_risk_level` — properties that roll up the highest risk level across all of a mission's active hazards, surfaced in both the list and detail serializers
- `MissionApprovalLog` — immutable audit trail of every submit/approve/reject/reopen transition
- **Approval workflow**, enforced server-side:
  ```
  DRAFT ──submit──▶ SUBMITTED ──approve──▶ APPROVED (mission.status also flips to APPROVED)
                         │
                         └──reject──▶ REJECTED ──submit──▶ SUBMITTED (resubmission)
  ```
  Submission requires at least one hazard assessment to exist. Approve/reject require ADMIN or COMMANDER role (checked server-side regardless of what the client sends) and reject requires a comment.

**New API endpoints** (all under `/api/v1/missions/`):

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/profiles/` | Mission profile CRUD |
| POST | `/profiles/{id}/submit-for-approval/` | DRAFT/REJECTED → SUBMITTED |
| POST | `/profiles/{id}/approve/` | SUBMITTED → APPROVED (ADMIN/COMMANDER only) |
| POST | `/profiles/{id}/reject/` | SUBMITTED → REJECTED, comment required (ADMIN/COMMANDER only) |
| GET/POST | `/profiles/{id}/hazards/` | View/add hazards on a mission |
| GET/POST | `/hazards/` | Direct CRUD on hazard assessments |
| GET | `/approval-logs/` | Read-only workflow history |

**Frontend**: `/missions` (list with unit/commander/status/risk-review-status/overall-risk-level columns) and `/missions/:id` (mission profile, hazard table with an add-hazard form covering category/probability/severity/controls, and the full submit/approve/reject workflow UI with an approval-log timeline) are now enabled in the sidebar.

**Re-run migrations after pulling Phase 3:**
```bash
python manage.py makemigrations missions
python manage.py migrate
python manage.py seed_demo_data   # now also seeds 2 hazard assessments and submits one mission for approval
```

---

## 10. Phase 4 additions — Armory Management & Inventory Management

**Armory Management** (`apps/armory`):
- `Firearm` — registry with status (Serviceable/Issued/Unserviceable/In Repair/Decommissioned), owning unit, and an `accountable_personnel` custodian
- `AmmunitionStock` — quantity-tracked ammo lots per unit, with an `is_low_stock` flag (< 100 rounds)
- `FirearmIssuance` — issuing a firearm flips it to ISSUED; `POST /issuances/{id}/return/` flips it back to SERVICEABLE and records condition-on-return
- `AmmunitionIssuance` — issuing decrements `AmmunitionStock.quantity_on_hand` automatically, with a serializer-level check against over-issuing
- `ArmoryInspection` — a FAILED result auto-flips the firearm to UNSERVICEABLE, NEEDS_MAINTENANCE flips it to IN_REPAIR
- `GET /armory/transactions/` merges firearm and ammunition issuances into one chronological transaction-history feed

**Inventory Management** (`apps/inventory`) — built from scratch this phase:
- `ItemCategory` — reference lookup (Communications, Medical, etc.)
- `InventoryItem` — covers both **Equipment** (serialized/accountable, requires a `property_number`) and **Supplies** (consumable, tracked by `quantity_on_hand` vs. `reorder_level`) in one model, with `is_low_stock` computed for supplies
- `InventoryTransaction` — the single source of truth for Receiving, Issuance, Return, Adjustment, and Disposal; creating one automatically updates the item's `quantity_on_hand` and, for EQUIPMENT issuance/return, its `accountable_personnel` — this is how "Stock levels" and "Property accountability" stay in sync without manual bookkeeping
- `GET /inventory/report/` — item counts, total stock, and low-stock counts grouped by category (the "Inventory reports" view; full PDF/Excel export lands in the dedicated Reports phase)

**New API endpoints:**

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/armory/firearms/` | Firearms registry |
| GET/POST | `/armory/ammunition/` | Ammunition stock |
| GET/POST | `/armory/issuances/` | Firearm issuance |
| POST | `/armory/issuances/{id}/return/` | Return a firearm |
| GET/POST | `/armory/ammunition-issuances/` | Ammunition issuance (auto-decrements stock) |
| GET/POST | `/armory/inspections/` | Armory inspections |
| GET | `/armory/transactions/` | Merged transaction history |
| GET/POST | `/inventory/categories/` | Item categories |
| GET/POST | `/inventory/items/` | Equipment/supply catalog |
| GET/POST | `/inventory/transactions/` | Receiving/issuance/return/adjustment/disposal |
| GET | `/inventory/report/` | Category-level inventory report |

**Frontend**: `/armory` (firearms registry, ammunition stock, active issuances with a role-gated "Mark Returned" action, transaction history) and `/inventory` (report summary cards, category breakdown, filterable item catalog with low-stock and custodian columns) are now enabled in the sidebar.

**Re-run migrations after pulling Phase 4:**
```bash
python manage.py makemigrations armory inventory
python manage.py migrate
python manage.py seed_demo_data   # now also seeds 2 firearms, 2 ammo lots, a radio (equipment), and a low-stock first aid kit
```

---

## 11. Phase 5 additions — GIS/Operational Mapping & Reports

**GIS / Operational Mapping** (`apps/gis`) — built out from a standalone MGRS conversion utility into the full module:
- `AORBoundary` (polygon), `Checkpoint` and `LandingZone` (points), `MapHazard` (point + optional radius — distinct from `apps.missions.HazardAssessment`, which is the probability/severity risk-workflow record, not a map marker), `Route` (line string), and `MapLayer` (metadata driving the frontend's layer-visibility panel)
- Every geometry field is `geography=True, srid=4326` PostGIS, consistent with Vehicle/Mission from earlier phases
- `apps.gis.utils.latlon_to_mgrs()` — dependency-free WGS84→MGRS conversion (accurate to ~1m), computed server-side in every GIS serializer and exposed standalone at `/gis/mgrs-convert/?lat=..&lng=..`
- `GET /gis/overlay/` — the single aggregation endpoint the map screen consumes: AOR boundaries, checkpoints, landing zones, active hazards, routes, and live vehicle/mission positions, each already carrying `lat`/`lng`/`mgrs`

**Reports** (`apps.reports`) — built from scratch:
- `apps.reports.services` — one function per report type (Personnel, Vehicle, Flight, Mission, Risk, Inventory) pulling live data from every module built in Phases 1–4; each returns `(title, headers, rows)` as the single source of truth for both the on-screen table and the exported file
- `apps.reports.exporters` — `build_pdf()` (ReportLab, landscape letter, styled header row) and `build_xlsx()` (openpyxl, styled header, auto-sized columns)
- `ReportExportLog` — records every export (type, format, who, row count) for accountability, in addition to the usual `AuditLog` entry
- New Python dependencies: `reportlab`, `openpyxl` (added to `requirements.txt`)

**New API endpoints:**

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/gis/aor-boundaries/` | AOR boundary polygons |
| GET/POST | `/gis/checkpoints/` | Checkpoints |
| GET/POST | `/gis/landing-zones/` | Landing zones |
| GET/POST | `/gis/hazards/` | Map hazards |
| GET/POST | `/gis/routes/` | Routes |
| GET/POST | `/gis/layers/` | Map layer definitions |
| GET | `/gis/overlay/` | Aggregated map data (all layers + live positions, with MGRS) |
| GET | `/gis/mgrs-convert/?lat=&lng=` | Ad-hoc lat/lng → MGRS conversion |
| GET | `/reports/` | List available report types |
| GET | `/reports/{type}/` | On-screen report data as JSON |
| GET | `/reports/{type}/export/?format=pdf\|xlsx` | Download the report as a file |

**Frontend**: `/gis` (layer-toggle panel + OpenLayers map rendering polygons/points/routes, plus an MGRS coordinate table for active hazards) and `/reports` (report-type picker, on-screen table, PDF/Excel export buttons that trigger a real browser download via a blob fetch — since export requires the JWT auth header, a plain `<a href>` link wouldn't work) are now enabled in the sidebar.

**Re-run migrations after pulling Phase 5:**
```bash
pip install -r requirements.txt   # picks up reportlab + openpyxl
python manage.py makemigrations gis reports
python manage.py migrate
python manage.py seed_demo_data   # now also seeds default map layers, an AOR polygon, 2 checkpoints, an LZ, a hazard, and a route
```

---

## 12. Phase 5 wrap-up

All nine core modules from the original spec now have a working backend and frontend: Dashboard, Personnel, Vehicle Tracking, Aircraft Flying Monitoring, Mission Risk Management, Armory, Inventory, GIS/Operational Mapping, and Reports.

---

## 13. RBAC overhaul — granular module x action permissions, unit/section scoping

Per a follow-up request to move all data entry to the frontend (not Django Admin) and implement real granular RBAC, the permission system was rebuilt:

**New data model:**
- `Section` (`apps.personnel`) — sits under `Unit`, e.g. "Transportation" within "Motor Transport Company"
- `User.unit` changed from free-text to a real FK to `Unit`; `User.section` added as FK to `Section`. The old free-text value is preserved as `User.unit_legacy` (nothing is deleted). Run `python manage.py migrate_user_units` once after migrating to map any legacy text values onto real `Unit` rows by name/code.
- `RolePermission` (`apps.core`) — the module × action grant matrix: `role`, `module`, `action`, `is_granted`. Modules: Dashboard, Personnel, Vehicles, Aircraft, Missions, Armory, Inventory, GIS, Reports, Administration. Actions: View, Create, Edit, Delete, Approve, Dispatch, Issue, Return, Assign, Export, Report.

**New enforcement mechanism** (`apps/core/permissions.py`, `apps/core/rbac.py`):
- `has_module_permission(user, module, action)` — the single source of truth; ADMIN/superuser always pass, everyone else is checked against `RolePermission`
- `HasModulePermission` — a DRF permission class any view declares via `permission_module` (+ optional `action_permission_map` for custom `@action` methods, or `required_action` for plain `APIView`s). **Fails closed**: a view that forgets to declare its module is rejected, not allowed through.
- `ModulePermissionMixin` — convenience mixin applying `HasModulePermission` to a ViewSet
- `UnitScopedQuerysetMixin` — restricts `list`/`retrieve` results to the requesting user's `unit` unless they're ADMIN/COMMANDER. A user with no unit assigned sees nothing, not everything (fail closed here too). Override `unit_field` when the model's unit relation isn't a direct field (e.g. `Aircraft.unit_field = 'base_unit'`).
- `python manage.py seed_permissions` — seeds the default matrix for COMMANDER/STAFF/OPERATOR/VIEWER (ADMIN is never seeded — it always passes). Safe to re-run; runs automatically as part of `seed_demo_data`.

**Applied across every app:** Personnel, Vehicles, Aircraft, Missions, Armory, Inventory, GIS, Reports, Dashboard, and Accounts (user management itself is now gated by the `ADMINISTRATION` module rather than a hardcoded admin-only check — COMMANDER gets VIEW by default, fully configurable). Vehicles and Aircraft also got real backend-enforced status-workflow actions (`POST /vehicles/registry/{id}/dispatch/`, `/return/`; `/aircraft/flights/{id}/depart/`, `/arrive/`) that reject invalid transitions regardless of what the frontend sends.

**Known gaps in this pass** (flagged, not silently skipped):
- `apps/gis/views.py`'s `OperationalOverlayView` and the dashboard summary aggregate across units without per-unit filtering yet — the per-module ViewSets (`AORBoundaryViewSet`, etc.) *are* unit-scoped, but the combined map/dashboard views aren't. Scoping them would mean filtering each of the 6–8 sub-queries individually by `request.user.unit_id`.
- `InventoryTransactionViewSet` grants `Action.CREATE` uniformly for all transaction types (receipt/issuance/return/adjustment/disposal) rather than distinguishing `Action.ISSUE` vs `Action.RETURN` per request body — a role restricted to RETURN-only could currently also ISSUE. Splitting this needs a second permission check inside `perform_create` once the transaction type is known.
- No frontend changes yet for any of this — no Add/Edit forms for Vehicles/Aircraft/Armory/Inventory, no Administration console screens (Roles/Permissions matrix editor, Units, Sections, Audit Logs), and the frontend doesn't yet read the new `permissions` field on `/auth/me/` to hide unauthorized buttons.
- Audit log still records descriptive text only, not structured old-value/new-value diffs.

**Re-run migrations after pulling this change:**
```bash
python manage.py makemigrations personnel accounts core
python manage.py migrate
python manage.py migrate_user_units   # only if you had users with the old free-text unit field
python manage.py seed_permissions     # or just re-run seed_demo_data, which calls this automatically
```

---

## 14. Unit hierarchy management & AOR consolidation

- `Unit.category` — echelon field: HPAF > Command > Wing > Group > Squadron. Both `Model.clean()` (Django admin) and `UnitSerializer.validate()` (API) reject a unit being made subordinate to an equal-or-lower echelon, and reject a unit being set as its own ancestor.
- `Unit.get_descendant_ids()` / `get_all_descendants()` — recursive hierarchy traversal (Python loop, not a SQL recursive CTE — fine at organizational-tree scale).
- **Mother-unit visibility**: `UnitScopedQuerysetMixin` (used across Personnel, Vehicles, Aircraft, Missions, Armory, Inventory, GIS) now scopes to the user's unit **plus every subordinate unit**, not just their own — a Wing-level user sees their Wing's data and everything under its Groups/Squadrons.
- **AOR consolidation**: `GET /gis/aor-boundaries/consolidated/?unit=<id>` returns the actual PostGIS geometric union (`ST_Union`) of every AOR boundary belonging to that unit and all its subordinates — a Wing's consolidated AOR is the union of its Squadrons' AORs. Handles both the single-polygon and disjoint-multipolygon result cases.
- Demo data rebuilt into a real 5-level tree: `HPAF → Air Mobility Command / Ground Forces Command → Aviation Wing / 1st Infantry Battalion → 1st Aviation Group → Aviation Squadron Alpha/Bravo`, with AOR boundaries seeded at the two squadrons specifically so the consolidation endpoint has something real to union.
- **Frontend**: `/admin/units` — a recursive tree view (category badges, subordinate counts), an Add/Edit modal (name/code/category/parent-unit/description), and a "View Consolidated AOR" action per unit showing the union result.

**Re-run migrations after pulling this change:**
```bash
python manage.py makemigrations personnel
python manage.py migrate
python manage.py seed_demo_data   # rebuilds the unit hierarchy with categories
```

---

## 15. Frontend data-entry forms — Vehicles, Aircraft, Armory, Inventory

Per your follow-up ("why are all the inputs backend, not frontend") — every module that previously had read-only list pages now has full Add/Edit forms, workflow actions, and permission-gated buttons, closing the gap with Django Admin as the only way to enter operational data.

**New shared UI foundations** (used by all four forms below, and reusable for anything built later):
- `src/components/common/SearchableSelect.tsx` — type-to-filter dropdown, replacing plain `<select>` for personnel/unit/mission/aircraft/firearm/item pickers
- `src/components/common/ConfirmDialog.tsx` — confirmation dialog for destructive/state-changing actions (dispatch, return, archive, cancel)
- `src/contexts/ToastContext.tsx` — global success/error notifications (`useToast().showSuccess/showError`), wired in at the app root in `main.tsx`
- **`AuthContext.can(module, action)`** — a new permission check mirroring the backend's `HasModulePermission`, driven by the `permissions` map the backend already sent on `/auth/me/` but the frontend never consumed until now (the `User` type was missing `permissions`/`unit_name`/`section`/`section_name` entirely — fixed). Every button in the new forms is gated through `can()`, not a hardcoded role check — this is a UX convenience only, same as before: the API enforces authorization independently and must never be bypassed just because a button was hidden.

**Vehicles** (`/vehicles`): Add/Edit form (plate number, make/model/type/year/capacity/fuel type, driver and mission via `SearchableSelect`), Dispatch/Return workflow buttons (confirmed via dialog, calling the existing backend actions), Archive.

**Aircraft** (`/aircraft`): Add/Edit for both the aircraft registry and the flight schedule (flight number, aircraft/mission/unit pickers, `datetime-local` departure/arrival, CAAP flight-plan fields), Mark Departed/Arrived/Cancel with confirmations, aircraft Archive.
- **Bug fixed while wiring this up**: `FlightViewSet` had no `perform_destroy` override, so a DELETE call would have hard-deleted the row from the database instead of soft-deleting it like every other model in the system. Added the override (sets `is_active=False` and `status=CANCELLED`, matching the pattern used everywhere else).

**Armory** (`/armory`): Add/Edit Firearm, Add Ammunition Stock, a dedicated "Issue Firearm" form (firearm/personnel pickers, expected return date, condition, purpose), Return (existing action) and Archive with confirmations.
- **Backend tightened while wiring this up**: `Firearm.status` and `accountable_personnel` were writable via a direct PATCH, which would have let the new Edit form (or any API caller) bypass the issue/return/inspection workflow entirely — set a firearm to ISSUED without ever creating a `FirearmIssuance` record. Both fields are now `read_only` on `FirearmSerializer`; they only change through the workflow actions, enforcing the controlled-status-transition requirement for real.

**Inventory** (`/inventory`): Add/Edit Item (name, category and unit via `SearchableSelect`, Equipment vs. Supply type with property-number validation, reorder level, condition), a "Log Transaction" form covering all five transaction types (Receipt/Issuance/Return/Adjustment/Disposal) with per-type conditional fields, Archive. `quantity_on_hand` and `accountable_personnel` were already correctly read-only on the item serializer (adjustable only via transactions) — no backend change needed there.

**What's still not covered**, to be upfront about it:
- No UI yet for Aircraft crew assignment or flight waypoints/itinerary (the backend endpoints exist: `/aircraft/flights/{id}/crew/`, `/aircraft/flights/{id}/waypoints/`)
- No UI yet for Vehicle trip-history or maintenance-record logging (backend: `/vehicles/trips/`, `/vehicles/maintenance/`)
- No UI yet for Mission profile Add/Edit (only the hazard-assessment workflow inside Mission Detail has a form) or Personnel Add/Edit
- Inline category creation isn't in the Inventory item form — categories must already exist (via Django Admin) before they appear in the picker

---

## 16. Permission-matrix audit: real gaps found and fixed

Per your enhancement request's own methodology (inspect → inventory → identify gaps → fix → report), here's the actual audit, not a restatement of the request.

### Module & endpoint inventory (Phase 1 deliverable)

| Module | Backend endpoints | Frontend coverage |
|---|---|---|
| Accounts/Admin | users, login, logout, refresh, me, change-password | List only — no create/edit/disable user form |
| Personnel | ranks, units, sections, positions, qualifications, records | **List only** — no Add/Edit Personnel form |
| Vehicles | registry, trips, maintenance, +dispatch/return/location | Registry: full CRUD + workflow. No trip/maintenance UI |
| Aircraft | registry, flights, crew-assignments, +depart/arrive | Registry+flights: full CRUD + workflow. No crew/waypoint UI |
| Missions | profiles, hazards, approval-logs, +submit/approve/reject | Hazard workflow only — **no Create Mission form** |
| Armory | firearms, ammunition, issuances, ammunition-issuances, inspections, transactions | Firearms/ammo/issuance: full CRUD. No ammo-issuance/inspection UI |
| Inventory | categories, items, transactions, report | Full CRUD |
| GIS | aor-boundaries, checkpoints, landing-zones, hazards, routes, layers, overlay, mgrs-convert | **Read-only map only** — no Add/Edit for any layer |
| Reports | list, data, export | Full |
| Risk (`apps.risk`) | **none** — model + Django admin only | Not reachable from the API at all, by design from Phase 1 (a lightweight dashboard-alert feed, distinct from Mission Risk Management's hazard workflow) |

### Real gaps found and fixed this pass

1. **`MissionApprovalLogViewSet` bypassed the permission matrix entirely** — it only checked `IsAuthenticated`, so any logged-in user (even VIEWER) could read mission approval history regardless of their configured `RolePermission` grants. Fixed: now uses `ModulePermissionMixin` with `Module.MISSIONS`, same as every other mission endpoint.

2. **`InventoryTransactionViewSet` couldn't actually distinguish ISSUE from RETURN from ADJUSTMENT** — every transaction type required the same blanket `Action.CREATE`. This was worse than it sounds: the default matrix grants OPERATOR `{VIEW, ISSUE, RETURN}` on INVENTORY but *no CREATE at all* — meaning an OPERATOR was being rejected at the permission-class level before ever reaching the transaction-type logic, so they **could not actually issue or return inventory items despite being granted that permission**. Fixed with a two-tier check: an outer gate (`_CanAttemptInventoryTransaction`) that passes if the user holds *any* transaction-capable permission, then `perform_create` enforces the precise action for the actual `transaction_type` sent (RECEIPT→CREATE, ISSUANCE→ISSUE, RETURN→RETURN, ADJUSTMENT→EDIT, DISPOSAL→DELETE).

3. **`Firearm.status`/`accountable_personnel` writable via direct PATCH** (caught in the previous session, included here for completeness) — would have let an Edit form bypass the issue/return workflow. Already fixed: both are `read_only` on `FirearmSerializer`.

4. **Frontend permission checks didn't match backend-enforced permissions in three places** — `MissionDetail.tsx`, `Units.tsx`, and `UserManagement.tsx` used hardcoded `hasRole('ADMIN', 'COMMANDER', ...)` checks instead of reading the actual configured `RolePermission` matrix via `can()`. Concretely: the default matrix grants COMMANDER `VIEW` on `ADMINISTRATION`, but `UserManagement.tsx`'s hardcoded `hasRole('ADMIN')` check hid the page from COMMANDER anyway — contradicting what the backend actually allows them to do. All three now use `can(module, action)`, reading the same matrix the API enforces. **I almost repeated this exact mistake while fixing it**: I first wired the Sidebar's "Units" nav item to `Module.ADMINISTRATION`, then caught that `UnitViewSet` actually declares `permission_module = Module.PERSONNEL` — fixed before shipping.

5. **Sidebar showed every module to every user regardless of permission** — the nav list was fully static. Now filtered through `can(module, 'VIEW')` per item, driven by the same matrix.

### What this pass did NOT do — explicitly, not silently

- **No new permission types or modules were added to the matrix.** The fixes above close *enforcement* gaps in the existing Module/Action taxonomy; they don't expand it. If you need finer-grained permissions than the existing 10 modules × 11 actions (e.g. splitting "Mission" into separate profile-edit vs. hazard-edit permissions), that's a taxonomy change, not a bug fix, and is worth deciding deliberately rather than bundling into an audit pass.
- **No Help Center / user guide was built.** This is a substantial, standalone piece of work — accurate module-by-module and role-by-role instructions that stay honest about what each role can't do. Building it before the frontend CRUD gaps above are closed would mean documenting features that don't exist yet.
- **No audit-log before/after value diffs.** Still descriptive text only, as flagged in section 13.
- **No formal permission test matrix** (role × module × action, pass/fail). The fixes above were verified by code review and `py_compile`/`tsc` checks, not by running the app against real requests — this sandbox still can't install dependencies to actually execute the server.
- **GIS overlay and Dashboard endpoints still aren't unit-scoped** (flagged in section 14) — they aggregate across all units regardless of the requesting user's hierarchy position.

### Recommended next steps, in priority order

1. Build the missing frontend CRUD for Personnel, Mission profiles, and GIS layers — these are the modules where Django Admin is still functionally required, which is the core problem your request is about.
2. Decide whether the Module/Action taxonomy needs to grow before building more permission checks on top of it.
3. Build the Help Center once the above stabilizes, so it documents the real interface rather than a moving target.
4. Add unit-scoping to the GIS overlay and Dashboard endpoints.

---

**Ready for your review.**
