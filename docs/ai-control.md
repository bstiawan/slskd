# Local AI control of Soulseek

slskd connects to Soulseek and manages transfers. The stdlib Python helper
`scripts/soulseek.py` lets an agent use its API without clicking through the UI.
No separate AI server or model subscription is required for this helper.

## This Mac's installation

- Official Apple Silicon release: [0.26.2](https://github.com/slskd/slskd/releases/tag/0.26.2).
  Its archive SHA-256 was checked against GitHub release metadata before extraction.
- Runtime, configuration, logs, and files: `.local/ai-control/`, excluded from Git.
  The directory is private; credential files have mode `0600`.
- Download and shared library: `/Users/bstiawan/Library/Mobile Documents/com~apple~CloudDocs/Music`.
  Network transfers remain in `.local/ai-control/incomplete/` until complete.
  The library's `.incoming/` folder holds completed files pending sorting and is
  excluded from sharing. Share scans run hourly (the supported minimum).
- API/UI binds: `127.0.0.1:5030` and `100.85.127.22:5030`.
  HTTPS is disabled; Tailscale provides encryption between tailnet devices.
- Local helper: `http://127.0.0.1:5030`, with a generated API key restricted to
  `127.0.0.1/32`. The installed release requires an administrator key to read server
  state. Do not print or paste `.local/ai-control/client.json` or `data/slskd.yml`.
- LaunchAgent label: `local.slskd`, visible in LaunchControl under User Agents.
  It runs from the repository's private plist, with a stable executable path,
  explicit working directory, separate stdout/stderr logs, `umask 077`,
  `KeepAlive: SuccessfulExit=false`, and `ThrottleInterval: 15`.
- Login startup is **not enabled**. The job was bootstrapped for the current login.
  Do not create another supervisor or manually background a second instance.

The installed release and this source checkout can differ. Check the live schema
at `/swagger/v0/swagger.json` when adding commands.

## Enter account credentials

Run this yourself in Terminal; the Soulseek password prompt is hidden:

```sh
python3 /Users/bstiawan/Documents/GitHub/slskd/scripts/configure-soulseek.py
```

This saves credentials privately and restarts the prepared service to connect.
It also displays the separate web UI login in your Terminal. It refuses to replace
an already configured account so active transfers can be checked before changes.
Ask the agent to verify login afterward. Never paste the config into chat.

## Agent commands

Run from this repository, or use the helper's absolute path:

```sh
python3 scripts/soulseek.py status
python3 scripts/soulseek.py search 'artist album'
python3 scripts/soulseek.py results SEARCH_ID
python3 scripts/soulseek.py downloads
python3 scripts/soulseek.py download PEER --file 'remote\folder\track.flac' --size 123456
python3 scripts/soulseek.py cancel PEER TRANSFER_ID
```

Use the exact peer, filename, and byte size returned by the search. Search returns
an ID while results arrive asynchronously; fetch results again when appropriate.
Compare format, size, reported audio attributes, locked status, upload slots, and
queue length before selecting files. Report ambiguity rather than silently
choosing a different release or format. Only queue downloads requested by Bayu.

Enqueue success is not download completion. Check transfer state and the saved
file before saying a download finished. Files depend on peer availability and
queues; failed or stalled downloads require inspection before retrying.

The helper's download command currently queues one file per request using the
supported per-peer endpoint; it does not automatically download every result.
For folders, inspect the file list and queue the selected files.

## Service checks

```sh
launchctl print gui/$(id -u)/local.slskd
curl --noproxy '*' http://127.0.0.1:5030/health
python3 scripts/soulseek.py status
```

HTTP health confirms the application is responding; authenticated server state
must separately confirm Soulseek login. Before restarts, inspect current downloads
and uploads. Logs are `.local/ai-control/logs/stdout.log` and `stderr.log`.

For a future login after this job is unloaded:

```sh
launchctl bootstrap gui/$(id -u) /Users/bstiawan/Documents/GitHub/slskd/.local/ai-control/local.slskd.plist
```

Bootstrap only if the job is absent. For a loaded inactive job use `launchctl
kickstart gui/$(id -u)/local.slskd`. Do not use `kickstart -k` without checking
active work. No logout/reboot test has been performed.

An idle crash-recovery test passed: after terminating the unconnected process,
launchd created a new process and HTTP health returned `200` without a manual start.

Tailscale access must pass an HTTP probe before advertising it as ready. macOS
requested an incoming-connection decision for the new slskd executable; tailnet
requests initially timed out, then a host-side Tailscale HTTP probe returned `200`.
Access from a second device has not been tested. No firewall rules were changed by the agent.
Loopback access is independent of that prompt. Soulseek uses port 50300 for incoming
peer connections; no router forwarding was configured.

## Music organization

The `DownloadFileComplete` hook runs `scripts/organize-download.py` with the private
`organizer-env` Python environment and Mutagen 1.47.0. It reads the event JSON from
`SLSKD_SCRIPT_DATA`, without passing peer-provided data through a shell.

Completed audio is sorted as `Music/Artist/Album/01 - Track Title.mp3` when title
and track-number tags exist; otherwise its original filename is preserved.
Multi-disc tags add `Disc 01`, `Disc 02`, etc. under the album folder. The artist tag
is preferred, with album artist as a fallback. Missing album tags use `Tracks`;
missing artist tags use `Unknown Artist`. Embedded tags are used as supplied, not
looked up online. Existing library files are not reorganized. Artist/album names
are sanitized and output stays inside the library. Name collisions get a numeric
suffix; existing files are never overwritten. Duplicate event deliveries are safe.
Staging directories stay in place across downloads: deleting and recreating them
during an active batch caused iCloud `Resource deadlock avoided` errors in a real
album test. Transfer `Completed, Succeeded` alone is insufficient: inspect its
`exception` field and final library files. Complete files left in the local
incomplete directory after a failed final move can be recovered without another
network download after checking sizes and metadata.

Non-audio attachments and unreadable audio remain in the unshared `.incoming`
folder for inspection. The hook does not reorganize cover art or other sidecars.
Rescan shares in the UI after a download if it should be shared before the hourly
scan. Preserve iCloud's local copies if files should stay continuously available to
Soulseek; online-only files depend on iCloud fetching them again.

The transfer list keeps the remote filename; use the sorted library path for the
saved file. slskd's library file browser can still browse the artist/album folders.
The prior private configuration is backed up as
`.local/ai-control/data/slskd.before-music-library.json`.

## Helper tests

```sh
PYTHONDONTWRITEBYTECODE=1 .local/ai-control/organizer-env/bin/python -m unittest discover -s tests/ai-control -p 'test_*.py'
```
