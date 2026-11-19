# Agent bootstrap

This repository contains upstream **slskd** source plus Bayu's local Soulseek
control helpers. Help Bayu search, download, organize music, and configure the
running client. Prefer the local API helper over browser automation.

## Read first

- For music discovery, downloads, or organization, read and use the
  [soulseek-music skill](/Users/bstiawan/.codex/skills/soulseek-music/SKILL.md).
  It owns source selection, quality preferences, verification, and recovery.
- Read [docs/ai-control.md](docs/ai-control.md) for this Mac's installation,
  configuration paths, service management, organizer, and troubleshooting.
- For substantive work, use the installed
  [agent-delegation skill](/Users/bstiawan/.codex/skills/agent-delegation/SKILL.md):
  check its usage policy and quota helper, choose an available approved OpenRouter
  worker explicitly, and keep integration and final verification with the primary.
  Keep small or inseparable tasks local. Disclose unavailable telemetry or routes.
- If a referenced skill is missing, report that limitation; do not claim to have
  used it. Continue independent diagnostics from repository documentation.

## Working style and scope

State material assumptions and give a brief plan for multi-step work. Resolve
routine implementation choices independently; ask when ambiguity affects the
requested release, configuration, or permissions. Make surgical changes and
verify the result. Report outcomes concisely.

A request to search alone does not authorize downloads. A requested download
authorizes the selected files within that request; do not add unrelated releases.
Avoid duplicate copies, silent format downgrades, and unrelated library cleanup.
Reuse the attached checkout unless a new worktree is explicitly requested.

## Local control

Run from the repository root:

```sh
python3 scripts/soulseek.py status
python3 scripts/soulseek.py search 'artist album'
python3 scripts/soulseek.py results SEARCH_ID
python3 scripts/soulseek.py downloads
python3 scripts/soulseek.py download PEER --file 'exact\remote\track.mp3' --size BYTES
python3 scripts/soulseek.py cancel PEER TRANSFER_ID
```

Search results arrive asynchronously. Keep the search ID and allow responses to
arrive before concluding that nothing was found. Use exact remote filenames and
sizes from results. The helper queues one file per download command. For album
batches, consult the running `/swagger/v0/swagger.json`, retain batch IDs, and
reconcile their state before retrying.

Bayu prefers **MP3, 320 kbps**, complete correct editions, accurate track sequence,
and tidy `01 - Track Title.mp3` names. Follow the music skill for detailed selection
and verification. Never report completion from an enqueue response or transfer
state alone: inspect exceptions and the final files and parsed audio metadata.

## Storage and credentials

- Download and shared library:
  `/Users/bstiawan/Library/Mobile Documents/com~apple~CloudDocs/Music`.
- `.local/ai-control/` is private and Git-ignored. It contains the installed binary,
  API credentials, `data/slskd.yml`, incomplete transfers, logs, and organizer env.
- Let helpers load credentials internally. Additional API operations may read the
  private configuration locally, but never print its full contents or put secrets
  in prompts, URLs, shell arguments, source files, commits, or reports.
- The completion hook runs `scripts/organize-download.py`; the music skill explains
  tag-based naming, disc folders, and missing-tag behavior. `.incoming` is unshared.
  Keep its staging directories during batches to avoid iCloud delete/recreate races.
- macOS may deny direct iCloud reads. Empty glob results can hide access errors;
  use the authenticated file-browser and local-share APIs described in the skill.
  Do not weaken privacy protections or assume local saving proves cloud sync.

## Configuration and service changes

1. Inspect current state and relevant effective options without exposing secrets.
   The runtime is separate from this checkout; source edits do not change the
   installed application. Match API calls to the installed schema.
2. Back up private configuration privately, preserve unrelated settings, and write
   changes atomically with mode `0600`. Do not edit credentials into example config.
3. Verify the effective settings and intended behavior. Check whether hot reload
   suffices before restarting. Inspect downloads, uploads, and other active work
   before any planned restart; do not interrupt active work without authorization.
4. Use the existing launchd User Agent **`local.slskd`**, managed in LaunchControl.
   Inspect the job, process/ports, and HTTP health before starting anything. Reuse a
   healthy instance; do not create a second background process or supervisor.
   Keep crash recovery `SuccessfulExit=false` and a 15-second throttle. Login
   startup requires Bayu's request; check its current state rather than assuming.

The local API is `http://127.0.0.1:5030`; the web UI is available on Tailscale at
`http://100.85.127.22:5030`. Verify the current Tailscale IP before changing binds,
and require a successful HTTP probe before advertising remote access as ready.
Do not broaden binds, firewall rules, sharing, or public exposure implicitly.
HTTP health, Soulseek login, final-file verification, and remote cloud sync are
separate checks.

## Verification

For changes to the Python helpers or organizer:

```sh
PYTHONDONTWRITEBYTECODE=1 .local/ai-control/organizer-env/bin/python -m unittest discover -s tests/ai-control -p 'test_*.py'
git diff --check
```

For upstream backend/frontend changes, follow [docs/build.md](docs/build.md) and
the applicable project checks. Avoid changing upstream code for configuration-only
requests. Do not commit private runtime data or downloaded music.
