# iOS Output Access (ntfy + Click-to-Open)

This guide makes Milton outputs easy to open on iPhone while keeping access tailnet-only.

## 1) Enable Tailscale Serve (no Funnel)

Run the helper script from the repo root:

```bash
bash scripts/setup_tailscale_serve_outputs.sh
```

That script prints your HTTPS URL (example):

```
https://<node>.<tailnet>.ts.net
```

Set it in `.env` (no trailing slash):

```
OUTPUT_BASE_URL=https://<node>.<tailnet>.ts.net
```

**Tailnet-only reminder**: do not enable Funnel for this URL. The `tailscale serve` command is enough for tailnet-only access.

## 2) Click-to-Open on iPhone

- Install the **ntfy** app on iPhone and subscribe to your answer topic.
- When a response arrives, tap the notification.
- Safari opens the HTTPS link from `OUTPUT_BASE_URL`.

If the link does not open:
- Confirm you are connected to your tailnet (Tailscale app on iOS).
- Confirm `OUTPUT_BASE_URL` matches the output server URL.

## 3) Always attach files (optional)

To always save output files and include click-to-open links, set:

```
ALWAYS_FILE_ATTACHMENTS=true
```

## 4) Prefix routing (iPhone message formats)

Supported prefixes (case-insensitive):

```
CLAUDE:  <request>   # Run Claude pipeline
CODEX:   <request>   # Run Codex pipeline
RESEARCH:<request>   # Research only
REMIND:  <spec>      # Reminder (e.g., "in 10m | Stretch")
ALARM:   <spec>      # Alarm (same syntax as REMIND)
```

Anything without a prefix defaults to CHAT mode.
