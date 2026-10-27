# Mission planning: categories, Ground Operations, vehicle trips, authority approval, MRM hand-off

## Root causes of the reported MRM bugs
1. **"I selected an evaluator but it says none is selected."** `SelectField` (the shared native `<select>`) never rendered a blank option
   for *required* fields. With state `''` matching no `<option>`, the browser **displayed the first evaluator** while React state stayed
   empty. The user saw a selection they had never made; "Save & submit" (a non-submit button that bypasses native validation) sent
   `reviewer: null` and the server answered "Please select an evaluator". Fix: a placeholder option is always present until a real choice is
   made, so display == state (`components/common/FormFields.tsx`).
2. **Same defect = the "MRM form field shows an unintended value" symptom.** `SearchableSelect` also rendered "— None —" in place of its own
   placeholder. It now shows the placeholder when nothing is chosen and only offers "clear" once something is.
3. **Latent: administrators editing an MRM** requested the evaluator list without the form's unit, got `[]`, so the saved evaluator looked
   "unavailable". The list is now always scoped to the form's unit.
4. **Error handling:** server errors were collapsed into one banner and the form could look reset. Errors now map to their field
   (`utils/formErrors.ts`), client validation mirrors the server (`utils/mrmValidation.ts`), and no selection is ever cleared on failure.

## What was built
* **Categories** — `Mission.category` (Air / Ground). A registry (`ground.py: CATEGORY_SPECS`, `components/missions/categories.tsx`) is the extension
  point. Air Operations is registered but disabled (backend refuses it, UI shows "coming soon") until its fields are specified:
  implement `AirOperationsSpec` + replace `AirOperationsForm`; nothing else changes. Existing missions stay uncategorised ("legacy") and keep working.
* **Ground Operations form** — Mission/Activity, Estimated start/end (end ≥ start, also a DB CHECK), UPR (unit), O/SPR (section of that unit),
  personnel from the Personnel Inventory with roles (Team Leader / Assistant / Member / Driver / Other + description), exactly one Team Leader
  (DB-enforced), no duplicate people, optional vehicle trips, authority, MRM assignee.
* **Vehicle trips** — optional; many vehicles per mission, many itinerary *legs* per vehicle, each leg = origin → ordered stops → destination
  with map click, direct MGRS entry (parsed/validated by the server, shown on the map), lat/lng, reorder/add/edit/remove. **POV** has its own form and
  tables carry no odometer; a POV can never create a fleet `Vehicle` or `Trip` (DB CHECK: a vehicle is fleet XOR POV).
  `MissionVehicle` is the *plan*; `vehicles.Trip` remains the executed-trip/odometer log (not duplicated).
* **Approval** — Draft → Pending → Approved/Rejected, independent of MRM. Candidates = active commanders/designated authorities in the unit or mother
  units **who hold `MISSIONS:APPROVE`**; the creator is never a candidate and can never decide their own mission. Rejection needs a reason; a rejected
  mission can be edited and resubmitted. Submit/decide are row-locked and idempotent.
* **Notifications** — UOMS had **no** general notification mechanism, so `core.Notification` (+ API + header bell) was added. Delivery is
  `transaction.on_commit` (nothing is sent for rolled-back work) and de-duplicated per submission/decision.
* **MRM hand-off** — on submit the MRM assignee is notified with a link to `/mrm/new?mission=<id>`; "MRM preparation" status
  (Not started / In progress / Revision required / Submitted / Approved) is **derived** from the real MRM form, never stored or set by hand.
  Approving a mission does not touch the MRM and an MRM never approves a mission (the earlier MRM→mission-status coupling was removed).
* **Visibility** — beyond unit scope, a mission is visible to its creator, authority, MRM assignee and assigned crew with accounts.
* **Details page** — nine sections (information, category, UPR/O-SPR, personnel, vehicles, itineraries, authority/approval, MRM, activity & notifications).
* **Idempotency** — `client_request_id` makes a repeated create return the same mission; buttons are guarded against double clicks.

## Files
**New (backend):** `missions/ground.py`, `missions/migrations/0002_mission_planning.py`, `missions/tests/*`, `core/notifications.py`, `core/views.py`,
`core/urls.py`, `core/migrations/0002_notification.py`, `gis/tests/*`.
**Modified (backend):** `missions/{models,views,serializers}.py`, `core/models.py`, `gis/{utils,views,urls}.py` (MGRS → lat/lng),
`personnel/{serializers,views}.py` (`has_account`, `mrm_ready`), `mrm/{services,views}.py`, `config/urls.py`.
**New (frontend):** `pages/missions/MissionEditor.tsx`, `components/missions/*` (GroundOperationsForm, AirOperationsForm, categories, PersonnelAssignments,
VehicleTripModal, ItineraryEditor, LocationPicker, MapPicker, MissionPlanSections), `components/layout/NotificationBell.tsx`, `api/missionOps.ts`,
`types/missionOps.ts`, `utils/{formErrors,mrmValidation,missionForm}.ts` (+ `*.test.ts`).
**Modified (frontend):** `components/common/{FormFields,SearchableSelect}.tsx`, `pages/mrm/MrmFormEditor.tsx`, `pages/{Missions,MissionDetail}.tsx`,
`components/layout/{Header,Sidebar}.tsx`, `App.tsx`, `types/{index,mrm}.ts`, `tsconfig.json`, `package.json`.

## Apply and run
```bash
cd backend
python manage.py migrate                  # core.0002 (notifications), missions.0002 (planning), earlier accounts/mrm migrations
python manage.py seed_permissions         # only if your RolePermission table is not seeded
./run_tests_postgres.sh                   # backend tests on PostGIS (never SQLite)
python manage.py runserver
cd ../frontend && npm install && npm run dev
npm run test:logic                        # Node ≥ 22.6: form/validation logic tests
```
Migrations only **add** tables/columns; existing missions are untouched (uncategorised, exempt from the new schedule constraint).
Rollback: `python manage.py migrate missions 0001 && python manage.py migrate core 0001` (tested on the stand-in database).

## Things you must know
* **Who can approve:** the Authority list only shows users who hold `MISSIONS:APPROVE` (by default the COMMANDER and ADMIN roles). A Squadron Commander
  with role STAFF will *not* appear until their role/permission is changed — by design ("existing permission rules").
* **MRM assignee:** must be assigned crew whose linked account has MRM Creator/Evaluator/Administrator authority.
* **Location search:** the map supports click-to-select, MGRS, lat/lng, and search of UOMS's own checkpoints/landing zones. Free-text place-name
  search (geocoding) would need an external service and was not added.
* **Air Operations:** extension points only, by design.

## Verification status
Passed here: 168 backend tests (planning, approval, notifications, MRM hand-off, constraints, migrations, MGRS round-trip over thousands of points,
column-length checks), Django checks, no pending migrations, 33 frontend logic tests, TypeScript type-check (only the 2 pre-existing `OperationalMap.tsx` errors).
**Not verified:** a real PostgreSQL/PostGIS run (sandbox has none — run `./run_tests_postgres.sh`), and the React screens in a browser
(no build tooling here — they are type-checked and their logic unit-tested, but not clicked through). Do a manual walk-through of: create Ground
mission → add vehicle/POV + itinerary → submit → approve/reject as the authority → prepare the MRM as the assignee.
