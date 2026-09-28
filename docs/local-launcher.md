# Local launcher

## Plan

Unify startup readiness, service identity, port conflicts, browser opening, and
owned-process cleanup. Keep local production serving independent of Wrangler
and avoid using stale development lock PIDs as authority to terminate processes.

## Usage

Run `Start-SpecCheck.bat` from normal Windows Explorer/terminal, or run
`npm run start:local` / `pnpm start:local` after installing dependencies.
Default address: http://127.0.0.1:3000/ (Backend: http://127.0.0.1:8000).
Keep the launcher terminal open. Ctrl+C stops only servers it started.

Environment options:

- `SPECCHECK_UI_PORT` / `SPECCHECK_BACKEND_PORT`: valid, different TCP ports.
- `SPECCHECK_PYTHON`: optional Python executable override.
- `SPECCHECK_NO_BROWSER=1`: do not open a browser automatically.

## Implementation

- Invoke Vinext build directly through Node, avoiding npm/pnpm command syntax
  differences. Build with `SPECCHECK_SIMPLE_DEV=1` and serve with `vinext start`
  on loopback, without Wrangler/Miniflare for the local experience. Deployment
  `npm run build` keeps the existing Cloudflare path unchanged.
- Backend `/health` and UI `/api/local-status` identify this project. Reuse only
  a healthy matching project with compatible backend URL/CORS/upload settings.
  The project hash is a diagnostic identity, not an authentication mechanism.
- An occupied, unverified, or unresponsive port fails with an actionable message.
  No existing process is killed and no development cache directory is deleted.
- Probe readiness with bounded waits, detect premature child exit, and render
  the page before opening the browser. Startup failure cleans up owned children.
- On Windows cleanup targets only live child PIDs owned by this launcher,
  including their subprocess trees; reused servers are not owned or stopped.
- BAT dependency preparation remains, but browser timing and stale lock handling
  are now controlled by the Node launcher. UAC approval still belongs to the user.

## Verification

Unit tests cover port validation, identity checks, reuse, foreign-port rejection,
readiness timeout, and early exit. Live verification used separate ports
3011/8011: npm startup built and served the page, a second launcher reused both
servers without rebuilding, and Ctrl+C closed those test ports while the existing
Backend on 8000 remained available. No synthetic collection fixture was uploaded.
Changing the UI port while reusing an incompatible backend was also rejected
before building or starting another UI. Backend identity/settings regression
test, frontend/launcher tests, TypeScript, and both local/deployment builds are
included in verification. BAT installation and browser auto-opening were not
rerun; live launcher checks used `SPECCHECK_NO_BROWSER=1` to avoid unwanted tabs.

An old server without project identity is deliberately not reused. Close that
server manually and relaunch. Stale Vinext development locks do not affect the
production launcher. Run outside the restricted agent sandbox for UAC-dependent
collection, as documented in `scan-failure-recovery.md`. Dependency installation
still requires network access on first use. Concurrent builds from different
launchers or deployment builds in this same checkout should be avoided.
