# Scan execution and result linkage

## Plan

Local scans previously selected the latest uploaded snapshot after Agent exit,
and the UI loaded `/api/scans/latest` on completion. A concurrent upload could
replace the result of the user's scan. Bind each execution to a specific snapshot
and reject stale UI responses instead.

## Implementation

- Each local scan reserves a UUID (`runId`). Its snapshot uses the same UUID.
- Backend passes `--snapshot-id` to Agent. Standalone CLI scans still generate
  fresh snapshot IDs when this option is omitted.
- The worker queries this exact snapshot after Agent exit. An unrelated upload
  cannot turn a missing upload into a successful scan.
- `GET /api/scans/{scan_id}` returns the persisted diagnosis for that snapshot;
  unknown IDs return 404, without falling back to the latest snapshot.
- The UI uses the completed state's `scanId`, checks the response ID, and rereads
  scan status before displaying the result. A newer execution suppresses the old
  response. Refresh/reconnect completion follows the same path.
- `/api/scans/latest` remains for initial history when no completed execution is
  being restored. While collecting/loading, an existing result is labeled as
  the previous diagnosis.

## Verification

- Backend regressions: ID-specific diagnosis despite a newer upload, missing-ID
  404, exact worker association, missing expected upload, reserved launch ID.
- Agent regressions: explicit UUID preservation, unique standalone IDs, invalid
  ID rejection.
- UI regressions: exact ID request, missing/mismatched IDs rejected, newer running,
  completed, or failed executions suppress late responses; existing reconnect
  and monitor tests remain in place.
- Run `npm run test:backend`, `npm run test:agent`, `npm run test:ui`,
  `npx tsc --noEmit`, and `npm run build`.

Verified on 2026-09-28: Backend 100 tests, Agent 76 tests, UI 8 tests passed;
TypeScript and production build passed. The backend was restarted while idle,
and the live ID-specific endpoint returned the same scan ID as the stored
diagnosis. No synthetic snapshot was inserted into the live database.

These tests simulate Agent execution and AI output; they do not establish that
UAC approval or a live Gemma scan succeeds on this machine. Server execution
state is still in memory, so restoring execution after a backend restart remains
separate work. Existing completed states from an older server use their stored
`scanId`; new executions adopt the UUID linkage after backend restart.
