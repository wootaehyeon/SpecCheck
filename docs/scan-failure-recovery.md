# Scan failure and timeout recovery

## Plan

Separate status connectivity errors from diagnosis errors. Bound automatic result
retries, preserve the last diagnosis, and expose a manual result reload that does
not run Agent again. Surface collection failure categories and prevent overlap
after an elevated Agent timeout when termination cannot be verified.

## Implementation

- Status requests retain a 5-second timeout and reconnect polling. A disconnected
  backend is not interpreted as a completed or failed scan.
- Diagnosis requests retain the configured timeout (90 seconds by default).
  Network errors, request timeouts, invalid JSON, and server error codes are
  reported separately, including timeouts during response-body reads.
- Result loading errors no longer mark the status service disconnected. Each
  completed execution has at most three automatic result attempts per monitor.
  After exhaustion the loading indicator stops, and the result reload button
  creates a fresh retry budget without calling the Agent start API.
- Existing diagnosis data is not cleared on collection or result failure.
- Scan status includes `errorCode` and `retryAllowed`. Failure codes include
  `UPLOAD_MISSING`, `ADMIN_LAUNCH_FAILED`, `AGENT_FAILED`, `SCAN_TIMEOUT`, and
  `UNSUPPORTED_PLATFORM`. Fresh executions reset these values.
- Agent subprocess timeout remains five minutes. When Backend is elevated,
  subprocess.run terminates its direct Agent child on timeout. When Backend is
  not elevated, the elevated Agent launched through PowerShell may remain alive;
  `retryAllowed=false` blocks both UI and start API (409
  `SCAN_CLEANUP_REQUIRED`). Confirm that Agent has exited before restarting
  Backend. Restarting Backend alone is not proof of Agent termination.

## Verification

Backend regression tests cover timeout status and safe retry policies, server-side
retry blocking, and actionable permission failures. UI tests cover bounded
retries, manual budget reset, no false disconnection, and cleanup after unmount.
HTTP tests cover network/header/body timeouts, structured HTTP errors, and
malformed JSON. Tests use simulated failures, not actual UAC cancellation or a
five-minute live hang. No failure fixture is inserted into the live database.

Commands: `npm run test:backend`, `npm run test:agent`, `npm run test:ui`,
`npx tsc --noEmit`, `npm run build`.

Execution state remains in memory. Backend restart recovery, confirmed elevated
process termination, and cancellation of ongoing server-side AI generation are
not added here. A browser timeout does not cancel server-side diagnosis work;
the result cache and per-snapshot lock still prevent duplicate AI generation
within a single Backend process.

## Live collection recovery (2026-09-28)

The backend launched from the restricted execution environment failed before
Agent collection with Windows Start-Process error `0xc0000142`. Restarting that
backend outside the restricted environment restored elevated Agent execution.
The backend did not need to be permanently elevated; its Agent elevation path
worked after the restart. Launch the server from a normal Windows terminal,
not a sandboxed child process, when verifying UAC-dependent collection.

Run `38023c57-ecde-4f7a-b712-2006b60a8096` completed and uploaded its matching
snapshot in approximately 25 seconds. ID-specific diagnosis retrieval succeeded.
Hardware, performance, reliability, anomaly, and trajectory sections were `ok`;
storage, security, and correlation were `partial`. Storage reported unsupported
SMART status/data queries, not a collection startup failure. Sysmon's own status
was `ok`. No test failure fixture was used for this live verification.
