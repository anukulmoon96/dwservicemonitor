# DWService Dashboard Monitor

Scheduled email status reports for your [DWService](https://www.dwservice.net/) devices. The script reads device status straight from your DWService dashboard, so **nothing is installed on the devices**.

A headless Chromium on a VM keeps the DWService web app open, logged in as a *trusted device*. Every few minutes it refreshes your **Shares** list and reads each agent's online/offline state from the app's own data. It logs every status change and emails your recipients a CSV + PDF status report at set times each day (09:00 and 21:00 by default).

- **Single file:** everything is in `dw_dashboard_monitor.py`. Its only dependency is [Playwright](https://playwright.dev/python/).
- **Free:** it sends mail through a Gmail app password, and the optional uptime check uses healthchecks.io's free tier.
- **Filters noise:** a device has to be offline for several checks in a row before it counts as offline.
- **Self-healing:** it logs itself back in, reloads the web app every 6 hours, and restarts if the browser hangs (with systemd).
- **Optional instant alerts:** an email the moment a device goes offline or comes back online.
- **Optional dashboard sync:** it can push every check's results to a backend API.

---

## Contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [One-time login](#one-time-login)
- [Commands](#commands)
- [Running as a service](#running-as-a-service)
- [What the reports contain](#what-the-reports-contain)
- [Dashboard backend sync](#dashboard-backend-sync)
- [Files created at runtime](#files-created-at-runtime)
- [Troubleshooting](#troubleshooting)
- [Security](#security)

---

## How it works

```
 ┌──────────────── VM ────────────────┐
 │  dw_dashboard_monitor.py           │
 │    │                               │        ┌──────────────────┐
 │    ├─ headless Chromium ───────────┼──────► │ DWService web app│
 │    │   (persistent profile,        │        │  (Shares list)   │
 │    │    "trusted device" login)    │        └──────────────────┘
 │    │                               │
 │    ├─ monitor-state.json  (history, events, per-device state)
 │    │                               │        ┌──────────────────┐
 │    ├─ Gmail SMTP ──────────────────┼──────► │ ALERT_EMAILS     │
 │    │                               │        └──────────────────┘
 │    ├─ healthchecks.io ping (opt.)  │
 │    └─ backend sync POST   (opt.)   │
 └────────────────────────────────────┘
```

1. **Read.** Each check clicks the web app's refresh button (or the **Shares** menu) and captures the share-list response the app loads. It falls back to a full page reload, then re-login through the saved trusted-device account.
2. **Filter.** Only devices whose name or group matches `INCLUDE_KEYWORDS`, and not `EXCLUDE_KEYWORDS`, are monitored.
3. **Track.** Each device's status is compared with the previous check. A device counts as **offline** only after `CONFIRM_CHECKS` offline checks in a row, which filters out brief blips. Devices that are already offline when monitoring starts never trigger an "offline" alert, but they do trigger a "back online" alert when they recover.
4. **Report.** At each `REPORT_TIMES` slot it emails a CSV + PDF report. A report more than 3 hours late is skipped instead of sent late (this happens if the monitor was down or couldn't read DWService).
5. **Alert (optional).** With `CHANGE_ALERTS=on`, it also emails immediately when devices change status.

Device status codes come from DWService: `N` Online, `F` Offline, `D` Disabled, `W` Waiting for install. Only `N` and `F` count toward availability and outages.

---

## Requirements

| | |
|---|---|
| OS | Ubuntu / Debian VM (any Linux that Playwright's Chromium supports) |
| Python | 3.8 or newer (3.9+ recommended, see the [time zone note](#configuration)) |
| Memory | About **1 GB of free RAM** for the headless browser |
| Accounts | A DWService account that can see the devices' shares, and a Gmail account with 2-Step Verification for sending mail |
| Network | Outbound HTTPS to `access.dwservice.net`, and SMTP to `smtp.gmail.com:465` |

### Gmail app password

1. Turn on **2-Step Verification** for the Gmail account that will send the emails.
2. Open <https://myaccount.google.com/apppasswords>, create an app password (any name), and copy the 16-character password.

> An app password can also **read** that mailbox, so use a separate Gmail account just for alerts rather than your personal one. Changing the account's Google password revokes the app password.

---

## Installation

```bash
sudo mkdir -p /opt/dw-monitor && sudo chown $USER /opt/dw-monitor
cd /opt/dw-monitor

python3 -m venv venv
venv/bin/pip install playwright
sudo venv/bin/playwright install-deps chromium
venv/bin/playwright install chromium
```

On Python 3.8, pip installs Playwright 1.48, the last release that supports 3.8. It works fine.

Copy `dw_dashboard_monitor.py` into `/opt/dw-monitor/`, then create the config file described below.

---

## Configuration

All settings are read from `/opt/dw-monitor/.env`, a file of `KEY=VALUE` lines in the same folder as the script. Real environment variables take precedence over `.env`.

### Required

```ini
GMAIL_USER=alerts.sender@gmail.com
GMAIL_APP_PASSWORD=abcdefghijklmnop
ALERT_EMAILS=person1@example.com, person2@example.com
```

Then lock the file down:

```bash
chmod 600 .env
```

### Optional

| Variable | Default | Description |
|---|---|---|
| `INCLUDE_KEYWORDS` | `Project` | Comma-separated, case-insensitive keywords matched against each device's **name and group**. Leave empty to monitor every device. |
| `EXCLUDE_KEYWORDS` | `GMEET` | Devices matching any of these keywords are skipped. |
| `ADMIN_EMAIL` | `GMAIL_USER` | Receives the "monitor can't read the device list" warnings, so recipients only get device emails. |
| `CHECK_INTERVAL_SECONDS` | `300` | How often the device list is read. This also sets how fresh the backend dashboard is. |
| `CHANGE_ALERTS` | `off` | `on` emails `ALERT_EMAILS` the moment a device goes offline or comes back online, with the same attachments as a report. |
| `CONFIRM_CHECKS` | `2` | Offline checks in a row before a device counts as offline. Alerts arrive after roughly `CHECK_INTERVAL_SECONDS × CONFIRM_CHECKS`. |
| `TIMEZONE` | `Asia/Kolkata` | IANA time zone used for report times and timestamps. |
| `REPORT_TIMES` | `09:00,21:00` | 24-hour times (in `TIMEZONE`) for the daily report, comma-separated. Leave empty to turn scheduled reports off. |
| `REPORT_TITLE` | *`<first include keyword>` device status report* | Heading of the PDF report and the email subject. |
| `DWS_ACCOUNT` | *(first saved account)* | The saved account email to click on DWService's login page. Only needed if more than one account is listed there. |
| `HC_PING_URL` | | A [healthchecks.io](https://healthchecks.io/) ping URL, pinged after every successful check, so you're told if the monitor itself stops. |
| `BACKEND_SYNC_URL` | | Dashboard endpoint, `https://<backend>/api/v1/dw-mapping/devices/sync`. See [Dashboard backend sync](#dashboard-backend-sync). |
| `BACKEND_SYNC_KEY` | | The backend's `DW_MONITOR_KEY`, sent as the `x-api-key` header. Sync runs only when both sync settings are set. |

> **Warning:** If `CHANGE_ALERTS=off` and `REPORT_TIMES` is empty, no device emails are sent at all. The script logs a warning at startup when this happens.

<details>
<summary><b>Advanced settings</b> (rarely needed)</summary>

| Variable | Default | Description |
|---|---|---|
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server. |
| `SMTP_PORT` | `465` | `465` uses implicit TLS. Any other port uses STARTTLS when the server offers it. |
| `START_URL` | `https://access.dwservice.net/login.dw` | Page opened on every full reload. |
| `SHARES_LABEL` | `Shares` | Text of the Shares menu item, if your DWService UI language differs. |
| `DEBUG_PORT` | `9222` | Chrome remote-debugging port used by `--login` (bound to `127.0.0.1` only). |
| `PROFILE_DIR` | `./browser-profile` | Where the persistent browser profile, including the login session, is kept. |

</details>

**Time zone note:** Python 3.8 has no `zoneinfo` module. On 3.8, `Asia/Kolkata` still works because India has no daylight saving time and a fixed +05:30 offset is used. Any other `TIMEZONE` falls back to the VM's local time, so use Python 3.9+ if you need another zone.

---

## One-time login

The VM has no screen, so you log in through **Chrome's remote inspector** from your own PC.

1. **On the VM**, start the login helper:
   ```bash
   venv/bin/python dw_dashboard_monitor.py --login
   ```
2. **On your PC**, open an SSH tunnel and leave it open:
   ```bash
   ssh -L 9222:127.0.0.1:9222 <user>@<vm-ip>
   ```
3. In Chrome on your PC, open `chrome://inspect/#devices`, click **Configure…**, add `localhost:9222`, and click **Done**. Under **Remote Target**, click **inspect** on the DWService page. A window shows the VM's browser, and you can click and type in it.
4. Log in to DWService, **tick "trusted device"**, and open **Shares**.

The script detects your agents, checks that automatic re-login works, and exits. It waits up to 30 minutes for you to finish. After this, the monitor logs itself back in by clicking your saved account on the DWService login page, which is why **"trusted device" is required**.

---

## Commands

Run these from `/opt/dw-monitor`. The report commands work while the service is running.

| Command | What it does |
|---|---|
| `venv/bin/python dw_dashboard_monitor.py` | Runs the monitor (this is what the service runs). |
| `… --test-email` | Sends a test email to `ALERT_EMAILS` describing what they'll receive. |
| `… --login` | One-time interactive login (see [above](#one-time-login)). |
| `… --check` | Reads the agent list once, prints a per-group summary, and tests a repeat refresh. With backend sync set up, it also sends one sync to the backend. |
| `… --report` | Builds a CSV + PDF from the latest saved data into `reports/`. |
| `… --send-report` | Same as `--report`, and also emails the report to `ALERT_EMAILS`. |

### Recommended first-run order

```bash
venv/bin/python dw_dashboard_monitor.py --test-email   # 1. email works
venv/bin/python dw_dashboard_monitor.py --login        # 2. log in once
venv/bin/python dw_dashboard_monitor.py --check        # 3. reading works
# 4. install the systemd service (below)
```

---

## Running as a service

Create `/etc/systemd/system/dw-monitor.service`:

```ini
[Unit]
Description=DWService offline monitor
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/dw-monitor
ExecStart=/opt/dw-monitor/venv/bin/python /opt/dw-monitor/dw_dashboard_monitor.py
Restart=always
RestartSec=30
KillMode=mixed
TimeoutStopSec=30
User=ubuntu

[Install]
WantedBy=multi-user.target
```

Change `User=` to your VM user, who must own `/opt/dw-monitor`. Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dw-monitor
```

| Task | Command |
|---|---|
| Follow the logs | `journalctl -u dw-monitor -f` |
| Apply `.env` changes | `sudo systemctl restart dw-monitor` |
| Stop (for example, before `--login`) | `sudo systemctl stop dw-monitor` |

A built-in watchdog exits the process if a check makes no progress for `max(15 min, 3 × CHECK_INTERVAL_SECONDS)`. `Restart=always` then starts a fresh browser.

---

## What the reports contain

Every report email, scheduled or change alert, carries two attachments. Copies are kept in `reports/` (the latest 200 files).

### CSV: `<slug>-devices-YYYY-MM-DD_HHMM.csv`

One row per monitored device, with these columns: Device, Group, Status, Changed in this alert, Status since, Time in status, Last seen online, Status changes (7 days), Availability (7 days), Hardware, Access, Shared by, Agent ID.

The file is UTF-8 with a BOM, so Excel opens device names correctly.

### PDF: `<slug>-status-report-YYYY-MM-DD_HHMM.pdf`

An A4 report rendered by Chromium, with these sections:

- **Summary figures:** online, not online, changes in the last 24 hours, and average availability.
- **Changes in this report:** devices that just went offline or came back online.
- **Fleet map:** one colored cell per device, grouped by DWService group.
- **Last 24 hours:** online devices against total devices, and status changes per hour.
- **By group:** device counts, online share, and availability per group.
- **Currently offline:** each offline device, when it went offline, and when it was last online.
- **Needs attention:** the devices with the lowest availability and the most status changes.
- **Recent status changes:** the latest 40 changes from the last 24 hours.

Availability is the share of time a device was online over the last 7 days, or since monitoring began if that's more recent. It is measured at each check, so drops shorter than the check interval aren't seen.

### Other emails

| Email | Sent to | When |
|---|---|---|
| 📊 Status report | `ALERT_EMAILS` | At each `REPORT_TIMES` slot, or with `--send-report` |
| 🔴 / 🟢 Status change | `ALERT_EMAILS` | Only with `CHANGE_ALERTS=on` |
| ⚠️ Monitor can't read the device list | `ADMIN_EMAIL` | After 3 failed checks in a row |
| ✅ Monitor is working again | `ADMIN_EMAIL` | After recovering from the above |

Emails that fail to send are queued and retried after the next check, keeping up to 20.

---

## Dashboard backend sync

When both `BACKEND_SYNC_URL` and `BACKEND_SYNC_KEY` are set, every successful check `POST`s the monitored devices to the dashboard's **Device Mapping** page. Devices that went offline or came back online are included as `changes`, which notify the support accounts on the site and as a Windows notification.

```http
POST /api/v1/dw-mapping/devices/sync
Content-Type: application/json
x-api-key: <BACKEND_SYNC_KEY>
```

```json
{
  "devices": [
    { "agent_id": "…", "name": "…", "group": "…", "state": "N", "hardware": "…" }
  ],
  "changes": [
    { "agent_id": "…", "change": "offline", "at": 1731400000, "offline_since": 1731399400 },
    { "agent_id": "…", "change": "online",  "at": 1731403600, "down_seconds": 3600, "down_known": true }
  ]
}
```

- Changes the backend didn't receive are resent with the next sync, up to the latest 500. The backend ignores duplicates.
- A backend failure never stops the checks or the emails.
- If the backend replies with `changes_stored: false`, apply `sql/dw-device-events-schema.sql` on the backend. That file is part of the backend, not this repo.

---

## Files created at runtime

All of these are created next to the script:

| Path | Contents |
|---|---|
| `.env` | Your configuration. **Keep it private** (`chmod 600`). |
| `browser-profile/` | Persistent Chromium profile holding the DWService login. **Keep it private** (created with mode `700`). |
| `monitor-state.json` | Per-device state, 7 days of fleet history, and 30 days of status-change events. |
| `reports/` | Copies of every CSV and PDF sent (the latest 200 files). |
| `debug/` | `last-failure.png`, `last-failure.html`, and `last-failure-steps.txt` from the most recent failed check. |

If you keep this folder under version control, ignore these files:

```gitignore
.env
browser-profile/
monitor-state.json
reports/
debug/
venv/
```

---

## Troubleshooting

**The monitor can't read the device list.** After each failed check it saves:

- `debug/last-failure.png`: a screenshot of what the browser saw.
- `debug/last-failure.html`: the page's HTML.
- `debug/last-failure-steps.txt`: the browser's recent steps.

If DWService logged the VM out, stop the service, run `--login` again, then start the service:

```bash
sudo systemctl stop dw-monitor
venv/bin/python dw_dashboard_monitor.py --login
sudo systemctl start dw-monitor
```

**Gmail rejected the login.** Check `GMAIL_USER` and `GMAIL_APP_PASSWORD`. Spaces in the app password are ignored. Changing the Google account password revokes app passwords, so create a new one.

**No emails arrive.** Run `--test-email`. Its message lists exactly what recipients will receive. Also check that `REPORT_TIMES` isn't empty, or turn on `CHANGE_ALERTS`.

**A scheduled report was skipped.** If no check succeeded within 3 hours of a report time, that report is skipped and logged rather than sent late.

**More than one saved account on the login page.** Set `DWS_ACCOUNT` to the email address to click.

**Wrong report times.** On Python 3.8, any `TIMEZONE` other than `Asia/Kolkata` falls back to the VM's local time. Upgrade to Python 3.9+, or set the VM's time zone.

---

## Security

- The `browser-profile/` folder can open your DWService account **without a password**; that's what "trusted device" means. Keep it private, and ideally log in with a **separate DWService account** that has only the shares it needs.
- The Gmail app password in `.env` can read the sending mailbox. Use a dedicated Gmail account and `chmod 600 .env`.
- The Chrome remote-debugging port opened by `--login` binds to `127.0.0.1` only, so you reach it through the SSH tunnel.
