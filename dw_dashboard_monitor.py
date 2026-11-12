#!/usr/bin/env python3
"""
dw_dashboard_monitor.py: free twice-daily status reports (via Gmail) for your
DWService devices, read straight from your DWService dashboard. Nothing is
installed on the devices.

How it works: a headless Chromium on your VM keeps the real DWService web app
open (logged in as a "trusted device"), refreshes your Shares list every few
minutes, reads each agent's online/offline state from the app's own data, logs
every status change, and emails your recipients a status report twice a day
(REPORT_TIMES, default 09:00 and 21:00).

Each report email carries two attachments: a CSV of every monitored device with
its status and details, and a PDF status report (summary, fleet map, 24-hour
trend, groups, offline devices, least available and most unstable devices,
recent changes). Copies are kept in the reports/ folder.

No email is sent when a device goes offline or comes back online; those
changes appear in the next report. Set CHANGE_ALERTS=on to also get an
instant email (with the same attachments) for each change.

By default it monitors devices whose name or group contains "Barns", and skips
devices whose name contains "GMEET". Change this with INCLUDE_KEYWORDS and
EXCLUDE_KEYWORDS below.

GMAIL APP PASSWORD
  1. Turn on 2-Step Verification for the Gmail account that will send alerts.
  2. Open https://myaccount.google.com/apppasswords, create one (any name),
     and copy the 16-character password.
  An app password can also read that mailbox, so a separate Gmail account just
  for alerts is safer than your personal one. Changing the account's Google
  password revokes the app password.

SETUP ON THE VM (Ubuntu/Debian; the browser needs about 1 GB of free RAM)
  1. Install:
        sudo mkdir -p /opt/dw-monitor && sudo chown $USER /opt/dw-monitor
        cd /opt/dw-monitor
        python3 -m venv venv
        venv/bin/pip install playwright
     (On Python 3.8 pip installs Playwright 1.48, the last version for 3.8;
      that works fine.)
        sudo venv/bin/playwright install-deps chromium
        venv/bin/playwright install chromium
  2. Put this file in /opt/dw-monitor/ and create /opt/dw-monitor/.env:

        GMAIL_USER=alerts.sender@gmail.com
        GMAIL_APP_PASSWORD=abcdefghijklmnop
        ALERT_EMAILS=person1@example.com, person2@example.com

     Optional settings, one per line (defaults shown):

        INCLUDE_KEYWORDS=Project
        EXCLUDE_KEYWORDS=GMEET
        ADMIN_EMAIL=
        CHECK_INTERVAL_SECONDS=300
        CHANGE_ALERTS=off
        CONFIRM_CHECKS=2
        TIMEZONE=Asia/Kolkata
        REPORT_TIMES=09:00,21:00
        REPORT_TITLE=
        DWS_ACCOUNT=
        HC_PING_URL=
        BACKEND_SYNC_URL=
        BACKEND_SYNC_KEY=

     INCLUDE_KEYWORDS / EXCLUDE_KEYWORDS: comma-separated, case-insensitive,
     matched against each device's name and group. Leave INCLUDE_KEYWORDS
     empty to monitor everything.
     ADMIN_EMAIL: who gets "monitor can't read the device list" warnings
     (defaults to GMAIL_USER, so your recipients only get device alerts).
     CHECK_INTERVAL_SECONDS: how often the device list is read. Each check also
     updates the dashboard (BACKEND_SYNC_URL), so this is how fresh the
     dashboard's statuses are; 300 (5 minutes) is a good balance.
     CHANGE_ALERTS: on = also email ALERT_EMAILS the moment a device goes
     offline or comes back online. off (default) = only the scheduled reports
     are emailed.
     CONFIRM_CHECKS: a device must be offline this many checks in a row before
     it counts as offline (filters out brief blips), for the CHANGE_ALERTS
     emails and the dashboard notifications alike. Offline time before either
     is about CHECK_INTERVAL_SECONDS x CONFIRM_CHECKS.
     REPORT_TIMES: when the status report (CSV + PDF) is emailed to
     ALERT_EMAILS each day, as 24-hour times in TIMEZONE, comma-separated.
     Leave empty to stop the scheduled reports (with CHANGE_ALERTS off, that
     means no device emails at all).
     REPORT_TITLE: heading of the PDF report (default "Barns device status report").
     DWS_ACCOUNT: the saved account email to click on DWService's login page
     (only needed if more than one account is listed there).
     HC_PING_URL: optional free healthchecks.io URL that alerts you if this
     monitor itself stops running.
     BACKEND_SYNC_URL / BACKEND_SYNC_KEY: after every check, send the monitored
     devices and their status to the dashboard's Device Mapping page. The URL
     is https://<backend>/api/v1/dw-mapping/devices/sync and the key is the
     backend's DW_MONITOR_KEY. Each device that went offline or came back
     online since the last report is sent too, and the dashboard notifies the
     support accounts (on the site and as a Windows notification); changes the
     backend didn't receive are sent again with the next report. Leave both
     empty to turn this off; emails work either way.
     Then: chmod 600 .env
  3. Test email:      venv/bin/python dw_dashboard_monitor.py --test-email
  4. Log in once:     venv/bin/python dw_dashboard_monitor.py --login   (see below)
  5. Test reading:    venv/bin/python dw_dashboard_monitor.py --check
     (with BACKEND_SYNC_URL set, this also sends one report to the backend)
  6. Run as a service (systemd unit below).

REPORTS ON DEMAND (work while the service is running)
  venv/bin/python dw_dashboard_monitor.py --report        save CSV + PDF to reports/
  venv/bin/python dw_dashboard_monitor.py --send-report   email them to ALERT_EMAILS

ONE-TIME LOGIN (the VM has no screen, so you use Chrome's remote inspector)
  a. On the VM run:   venv/bin/python dw_dashboard_monitor.py --login
  b. On your PC open a tunnel in a terminal and leave it open:
        ssh -L 9222:127.0.0.1:9222 <user>@<vm-ip>
  c. In Chrome on your PC open chrome://inspect/#devices, click "Configure...",
     add  localhost:9222  and click Done. Under "Remote Target" click "inspect"
     on the DWService page. A window shows the VM's browser; you can click and
     type in it.
  d. Log in to DWService, TICK "trusted device", then open Shares.
     The script detects your agents, checks that automatic re-login works,
     and exits. Afterwards it logs itself back in by clicking your saved
     account on DWService's login page, so "trusted device" is required.

SYSTEMD (/etc/systemd/system/dw-monitor.service)

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

  Change User= to your VM user (it must own /opt/dw-monitor), then:
    sudo systemctl daemon-reload && sudo systemctl enable --now dw-monitor
  Logs: journalctl -u dw-monitor -f
  After editing .env:  sudo systemctl restart dw-monitor

IF IT STOPS WORKING
  After a failed check the script saves debug/last-failure.png (a screenshot of
  what the browser saw) and debug/last-failure.html. If DWService logged the VM
  out, stop the service, run --login again, and start it.

SECURITY
  The browser-profile folder can open your DWService account without a password
  (that's what "trusted device" means). Keep it private, and ideally log in with
  a separate DWService account that only has the shares it needs.
"""

import argparse
import csv
import html
import io
import json
import os
import re
import signal
import smtplib
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.message import EmailMessage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_env(path):
    """Read KEY=VALUE lines from a .env file into os.environ (real env vars win)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env(os.path.join(BASE_DIR, ".env"))


def env_list(name, default=""):
    raw = os.environ.get(name, default)
    return [part.strip() for part in raw.split(",") if part.strip()]


GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
ALERT_EMAILS = env_list("ALERT_EMAILS")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip() or GMAIL_USER
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT") or 465)
INCLUDE_KEYWORDS = [k.lower() for k in env_list("INCLUDE_KEYWORDS", "Barns")]
EXCLUDE_KEYWORDS = [k.lower() for k in env_list("EXCLUDE_KEYWORDS", "GMEET")]
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL_SECONDS") or 300)
CONFIRM_CHECKS = max(1, int(os.environ.get("CONFIRM_CHECKS") or 2))
# Email ALERT_EMAILS the moment a device goes offline / comes back online. Off: changes are
# only logged and shown in the scheduled reports (REPORT_TIMES).
CHANGE_ALERTS = os.environ.get("CHANGE_ALERTS", "off").strip().lower() in ("1", "on", "true", "yes")
HC_PING_URL = os.environ.get("HC_PING_URL", "")
# Dashboard backend that receives each check's devices (Device Mapping page); both or neither.
BACKEND_SYNC_URL = os.environ.get("BACKEND_SYNC_URL", "").strip()
BACKEND_SYNC_KEY = os.environ.get("BACKEND_SYNC_KEY", "").strip()
START_URL = os.environ.get("START_URL", "https://access.dwservice.net/login.dw")
SHARES_LABEL = os.environ.get("SHARES_LABEL", "Shares")
DWS_ACCOUNT = os.environ.get("DWS_ACCOUNT", "").strip()  # saved account to click; default: the first one
DEBUG_PORT = int(os.environ.get("DEBUG_PORT") or 9222)
PROFILE_DIR = os.environ.get("PROFILE_DIR") or os.path.join(BASE_DIR, "browser-profile")
STATE_FILE = os.path.join(BASE_DIR, "monitor-state.json")
DEBUG_DIR = os.path.join(BASE_DIR, "debug")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
REPORT_TITLE = (os.environ.get("REPORT_TITLE", "").strip()
                or (INCLUDE_KEYWORDS[0].title() if INCLUDE_KEYWORDS else "DWService") + " device status report")
REPORT_SLUG = re.sub(r"[^a-z0-9]+", "-", (INCLUDE_KEYWORDS[0] if INCLUDE_KEYWORDS else "dwservice").lower()).strip("-")
FAIL_ALERT_AFTER = 3          # failed checks in a row before warning ADMIN_EMAIL
FULL_RELOAD_EVERY = 6 * 3600  # reload the web app periodically to keep memory in check
REPORT_LATE_LIMIT = 3 * 3600  # a scheduled report this late (monitor down or failing) is skipped


def parse_report_times(raw):
    """'09:00, 21:00' -> [(9, 0), (21, 0)]. Empty turns the scheduled reports off."""
    times = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", part)
        if not m:
            sys.exit(f"REPORT_TIMES: {part!r} isn't a time like 09:00 (24-hour, comma-separated)")
        times.append((int(m.group(1)), int(m.group(2))))
    return sorted(set(times))


REPORT_TIMES = parse_report_times(os.environ.get("REPORT_TIMES", "09:00,21:00"))

TZ_NAME = os.environ.get("TIMEZONE") or "Asia/Kolkata"
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    TZ = ZoneInfo(TZ_NAME)
except Exception:
    from datetime import timedelta, timezone
    # Python 3.8 has no zoneinfo. India has no daylight saving, so a fixed offset is exact;
    # any other zone falls back to the VM's local time.
    TZ = timezone(timedelta(hours=5, minutes=30), "IST") if TZ_NAME == "Asia/Kolkata" else None


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


# ---------------------------------------------------------------- DWService protocol

FRAME_HEAD = re.compile(r"([^:]*):(\d+):")
EMAIL_TEXT = re.compile(r"^\s*[^@\s]+@[^@\s]+\.[A-Za-z]{2,}\s*$")


def parse_frames(text):
    """Split a DWService command response into {request_id: (status, payload)}.

    The format is "K:" followed by repeated "<id>:<length>:<status>:<payload>",
    where <length> covers "<status>:<payload>" measured in UTF-16 code units.
    A command's answer can arrive in the response to a later request.
    """
    if not text.startswith("K:"):
        raise ValueError(f"unexpected response: {text[:40]!r}")
    frames, pos, n = {}, 2, len(text)
    while pos < n:
        m = FRAME_HEAD.match(text, pos)
        if not m:
            raise ValueError(f"bad frame header at {pos}: {text[pos:pos + 40]!r}")
        frame_id, units = m.group(1), int(m.group(2))
        start = end = m.end()
        count = 0
        while count < units and end < n:
            count += 2 if ord(text[end]) > 0xFFFF else 1
            end += 1
        status, _, payload = text[start:end].partition(":")
        frames[frame_id] = (status, payload)
        pos = end
    return frames


def share_list_requests(post_data):
    """Return {request_id: list_name} for the share-list loads in a command request."""
    q = urllib.parse.parse_qs(post_data or "", keep_blank_values=True)

    def get(key):
        return q.get(key, [""])[0]

    try:
        count = int(get("count") or 0)
    except ValueError:
        return {}
    found = {}
    for i in range(count):
        if (get(f"module_{i}") == "share" and get(f"command_{i}") == "datasource"
                and get(f"parameter_{i}_operation") == "load"):
            found[get(f"id_{i}")] = get(f"parameter_{i}_name")
    return found


# ---------------------------------------------------------------- browser side

class ShareWatcher:
    """Drives the DWService web app and captures the agent list it loads."""

    def __init__(self, page):
        self.page = page
        self.pending = {}   # (session url, request id) -> list name
        self.queue = []     # finished requests waiting to be read
        self.latest = None  # (time captured, items)
        self.last_reload = 0.0
        self.trace = []     # recent steps, printed when something fails
        # "requestfinished" only fires once the full response has arrived, so reading
        # it can't hang on a request that was cut off by a page change.
        page.on("requestfinished", self._on_finished)
        page.on("framenavigated", self._on_navigate)

    def note(self, msg):
        self.trace.append(time.strftime("%H:%M:%S ") + msg)
        del self.trace[:-40]

    def _on_navigate(self, frame):
        if frame == self.page.main_frame:
            self.note("page: " + frame.url.split("?", 1)[0])

    def _on_finished(self, request):
        url = request.url
        if ("/ses/" in url and "request=command" in url) or "authentication.dw" in url:
            self.queue.append(request)

    def _drain(self):
        while self.queue:
            request = self.queue.pop(0)
            if "authentication.dw" in request.url:
                try:
                    self.note(f"login request: HTTP {request.response().status}")
                except Exception:
                    self.note("login request: no response")
                continue
            session = request.url.split("?", 1)[0]
            try:
                self.pending.update({(session, rid): name for rid, name in
                                     share_list_requests(request.post_data).items()})
                frames = parse_frames(request.response().text())
            except Exception:
                continue
            for rid, (status, payload) in frames.items():
                if self.pending.pop((session, rid), None) != "incoming" or status != "K":
                    continue
                try:
                    data = json.loads(payload)
                except ValueError:
                    continue
                if data.get("status") == "ok" and isinstance(data.get("items"), list):
                    self.latest = (time.time(), data["items"])
                    self.note(f"agent list received ({len(data['items'])} entries)")
        if len(self.pending) > 500:
            self.pending.clear()

    def wait_for_list(self, since, seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            self.page.wait_for_timeout(500)
            self._drain()
            if self.latest and self.latest[0] >= since:
                return self.latest[1]
        return None

    def _click_all(self, locator, what, limit=4, hidden_ok=False):
        clicked, found = 0, 0
        try:
            found = locator.count()
            for i in range(min(found, limit)):
                element = locator.nth(i)
                try:
                    if element.is_visible():
                        element.click(timeout=3000)
                        clicked += 1
                    elif hidden_ok:
                        # e.g. an item inside a collapsed side menu
                        element.dispatch_event("click")
                        clicked += 1
                except Exception:
                    pass
        except Exception:
            pass
        self.note(f"{what}: found {found}, clicked {clicked}")
        return clicked > 0

    def click_refresh(self):
        p = self.page
        return (self._click_all(p.locator('img[src*="md-refresh"]'), "refresh icon")
                or self._click_all(p.locator('[style*="md-refresh"]'), "refresh icon (css)"))

    def click_shares(self):
        p = self.page
        return (self._click_all(p.get_by_text(SHARES_LABEL, exact=True), f"'{SHARES_LABEL}' text", 3, True)
                or self._click_all(p.locator(f'[title="{SHARES_LABEL}"]'), f"'{SHARES_LABEL}' tooltip", 3, True))

    def pick_saved_account(self, wait=20):
        """On the login page, click the saved trusted-device account (no password needed).

        DWService lists trusted accounts under "Accounts" on its login page; clicking
        the email logs in. The menu button next to it is never touched.
        """
        deadline = time.time() + wait
        while time.time() < deadline and "login.dw" in self.page.url:
            target = (self.page.get_by_text(DWS_ACCOUNT, exact=True) if DWS_ACCOUNT
                      else self.page.get_by_text(EMAIL_TEXT))
            try:
                if target.count() and target.first.is_visible():
                    self.note("clicking saved account " + target.first.inner_text().strip())
                    target.first.click(timeout=5000)
                    self.page.wait_for_url(lambda url: "session.dw" in url, timeout=30000)
                    return True
            except Exception as exc:
                self.note(f"saved-account login problem: {str(exc).splitlines()[0]}")
            self.page.wait_for_timeout(1000)
        if "login.dw" in self.page.url:
            self.note("no saved account found on the login page")
        return "session.dw" in self.page.url

    def reload(self):
        self.last_reload = time.time()
        self.note("reloading " + START_URL)
        try:
            self.page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            log(f"Page load problem: {exc}")

    def fetch(self, force_reload=False):
        """Return (items, how) with the current shared-agent list, or (None, None)."""
        self._drain()
        since = time.time()
        stale = time.time() - self.last_reload > FULL_RELOAD_EVERY
        if not force_reload and not stale and "session.dw" in self.page.url:
            if self.click_refresh():
                items = self.wait_for_list(since, 20)
                if items is not None:
                    return items, "refresh button"
            if self.click_shares():
                items = self.wait_for_list(since, 20)
                if items is not None:
                    return items, "Shares menu"
        # Full reload, then log in through the saved trusted-device account.
        self.reload()
        self.pick_saved_account()
        items = self.wait_for_list(since, 15)
        if items is not None:
            return items, "page reload"
        for _ in range(4):
            self.pick_saved_account(wait=5)
            self.click_shares()
            items = self.wait_for_list(since, 10)
            if items is not None:
                return items, "page reload + Shares menu"
        return None, None

    def save_debug(self):
        try:
            os.makedirs(DEBUG_DIR, exist_ok=True)
            self.page.screenshot(path=os.path.join(DEBUG_DIR, "last-failure.png"), full_page=True)
            with open(os.path.join(DEBUG_DIR, "last-failure.html"), "w", encoding="utf-8") as f:
                f.write(self.page.content())
        except Exception as exc:
            log(f"Could not save debug files: {exc}")
        try:
            os.makedirs(DEBUG_DIR, exist_ok=True)
            with open(os.path.join(DEBUG_DIR, "last-failure-steps.txt"), "w", encoding="utf-8") as f:
                f.write(f"final page: {self.page.url.split('?', 1)[0]}\n" + "\n".join(self.trace) + "\n")
        except Exception:
            pass

    def report_failure(self):
        """Save debug files and print what the browser did."""
        self.save_debug()
        print("What the browser did:", flush=True)
        for line in self.trace[-25:]:
            print("  " + line, flush=True)
        print(f"Final page: {self.page.url.split('?', 1)[0]}", flush=True)
        print(f"Screenshot: {DEBUG_DIR}/last-failure.png  (steps: {DEBUG_DIR}/last-failure-steps.txt)", flush=True)


def launch_browser(playwright, debug_port=None):
    os.makedirs(PROFILE_DIR, exist_ok=True)
    os.chmod(PROFILE_DIR, 0o700)
    args = ["--disable-dev-shm-usage"]
    if debug_port:
        args.append(f"--remote-debugging-port={debug_port}")  # binds to 127.0.0.1 only
    options = dict(headless=True, args=args, viewport={"width": 1366, "height": 900}, locale="en-US")

    def start(**extra):
        try:
            # Playwright 1.49+: full Chromium in its newer headless mode
            return playwright.chromium.launch_persistent_context(PROFILE_DIR, channel="chromium", **options, **extra)
        except Exception:
            # Playwright 1.48 (the last version for Python 3.8) has no such channel
            return playwright.chromium.launch_persistent_context(PROFILE_DIR, **options, **extra)

    context = start()
    page = context.pages[0] if context.pages else context.new_page()
    # Present as regular Chrome: headless browsers announce themselves as "HeadlessChrome".
    agent = page.evaluate("navigator.userAgent")
    if "HeadlessChrome" in agent:
        context.close()
        context = start(user_agent=agent.replace("HeadlessChrome", "Chrome"))
        page = context.pages[0] if context.pages else context.new_page()
    return context, page


# ---------------------------------------------------------------- alert logic

STATUS_LABELS = {"N": "Online", "F": "Offline", "D": "Disabled", "W": "Waiting for install"}
HISTORY_KEEP = 7 * 86400   # fleet counts kept for trend charts
EVENTS_KEEP = 30 * 86400   # status changes kept for analytics
WINDOW = 7 * 86400         # availability / change-count window in reports


def status_label(code):
    return STATUS_LABELS.get(code, code or "Unknown")


def is_monitored(name, group):
    text = f"{name}\n{group}".lower()
    if INCLUDE_KEYWORDS and not any(k in text for k in INCLUDE_KEYWORDS):
        return False
    return not any(k in text for k in EXCLUDE_KEYWORDS)


def describe_access(permissions):
    if not isinstance(permissions, dict):
        return ""
    if permissions.get("fullAccess"):
        return "Full access"
    apps = permissions.get("applications") or []
    return f"Limited ({len(apps)} app{'' if len(apps) == 1 else 's'})"


def select_agents(items):
    """Dedupe the share list by agent id and keep only the monitored devices."""
    agents = {}
    for item in items:
        agent_id = item.get("idAgent")
        name = " ".join((item.get("name") or agent_id or "").split())
        group = item.get("group") or ""
        if not agent_id or not is_monitored(name, group):
            continue
        sharer, email = item.get("userDisplayName") or "", item.get("userEMail") or ""
        agents[agent_id] = {
            "name": name,
            "group": group,
            "state": item.get("state"),
            "hardware": item.get("agentHwName") or "",
            "access": describe_access(item.get("permissions")),
            "shared_by": f"{sharer} ({email})" if sharer and email else (sharer or email),
        }
    return agents


def update_state(state, agents, confirm=CONFIRM_CHECKS, now=None):
    """Apply one snapshot. Returns (went_down_ids, came_up_ids, online, total).

    Offline alerts need the device to have been seen online first, so devices that
    are already offline when monitoring starts don't trigger one. Any device that
    has been offline for at least `confirm` checks (including those) triggers an
    online alert when it comes back; a shorter blip triggers nothing.
    Every observed status change is also logged for the reports.
    """
    now = time.time() if now is None else now
    known = state.setdefault("agents", {})
    events = state.setdefault("events", [])
    state.setdefault("started", now)
    went_down, came_up = [], []
    for agent_id, agent in agents.items():
        new = agent["state"]
        rec = known.get(agent_id)
        if rec is None:
            rec = known[agent_id] = {"was_online": False, "off_count": 0, "alerted": False}
            if new == "F":
                # Already offline when first seen: treat it as confirmed offline.
                rec.update(off_count=confirm - 1, off_since=now)
        if "since" not in rec:  # new device, or a state file from an older version
            rec.update(first_seen=now, since=now, since_known=False)
        prev = rec.get("state")
        if prev is not None and prev != new:
            events.append([now, agent_id, agent["name"], agent["group"], prev, new])
            rec["since"], rec["since_known"] = now, True
        rec.update(agent)
        if new == "N":
            rec["last_online"] = now

        if new == "N":  # online
            if rec["alerted"] or rec["off_count"] >= confirm:
                rec["down_for"] = now - rec.get("off_since", now)
                # Never seen online before: the outage began before monitoring did.
                rec["down_known"] = rec["was_online"]
                came_up.append(agent_id)
            rec.update(was_online=True, off_count=0, alerted=False)
        elif new == "F":  # offline
            rec["off_count"] += 1
            if rec["off_count"] == 1 or "off_since" not in rec:
                rec["off_since"] = now
            if rec["was_online"] and not rec["alerted"] and rec["off_count"] >= confirm:
                rec["alerted"] = True
                went_down.append(agent_id)
        else:  # disabled, updating, waiting for install: not an outage
            rec["off_count"] = 0
    for agent_id in [a for a in known if a not in agents]:
        del known[agent_id]  # filtered out, share removed or agent deleted

    online = sum(1 for a in agents.values() if a["state"] == "N")
    history = state.setdefault("history", [])
    if not history or now - history[-1][0] >= 240:
        history.append([now, online, len(agents)])
    state["history"] = [h for h in history if h[0] >= now - HISTORY_KEEP]
    state["events"] = [e for e in events if e[0] >= now - EVENTS_KEEP][-10000:]
    state["last_check"] = now
    return went_down, came_up, online, len(agents)


# ---------------------------------------------------------------- formatting helpers

def fmt_time(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%d %b %Y, %H:%M")


def fmt_short(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%d %b, %H:%M")


def fmt_iso(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%Y-%m-%d %H:%M")


def tz_label(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%Z") or "local time"


def fmt_duration(seconds):
    minutes = max(1, int(seconds // 60))
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return f"{hours} h {minutes} min" if minutes else f"{hours} h"
    return f"{hours // 24} days"


def fmt_pct(fraction):
    return f"{fraction * 100:.1f}%"


# ---------------------------------------------------------------- scheduled reports

def describe_report_times():
    return " and ".join(f"{h:02d}:{m:02d}" for h, m in REPORT_TIMES)


def _report_slots(now):
    """The scheduled report times from yesterday to tomorrow, as timestamps, oldest first."""
    midnight = datetime.fromtimestamp(now, TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return sorted((midnight + timedelta(days=days)).replace(hour=h, minute=m).timestamp()
                  for days in (-1, 0, 1) for h, m in REPORT_TIMES)


def last_report_slot(now):
    """The most recent scheduled report time at or before `now`, or None."""
    past = [s for s in _report_slots(now) if s <= now] if REPORT_TIMES else []
    return past[-1] if past else None


def next_report_slot(now):
    """The next scheduled report time after `now`, or None."""
    future = [s for s in _report_slots(now) if s > now] if REPORT_TIMES else []
    return future[0] if future else None


def take_due_report(state, now):
    """The scheduled report time that has come round since the last one sent, or None.

    Call it only after a successful check, so the report has fresh data. The time is
    recorded in `state` either way; one missed by more than REPORT_LATE_LIMIT (the
    monitor was down, or couldn't read DWService) is skipped rather than sent late.
    """
    slot = last_report_slot(now)
    if slot is None or slot <= state.get("last_report_slot", 0):
        return None
    state["last_report_slot"] = slot
    if now - slot > REPORT_LATE_LIMIT:
        log(f"Skipped the {fmt_time(slot)} report: no successful check until {fmt_time(now)}")
        return None
    return slot


# ---------------------------------------------------------------- analytics

def device_analytics(state, now):
    """Per-device availability and status-change counts over the last WINDOW
    (or since the device was first seen, if that's more recent)."""
    by_id = {}
    for e in state.get("events", []):
        by_id.setdefault(e[1], []).append(e)
    window_start = max(now - WINDOW, state.get("started", now))
    out = {}
    for agent_id, rec in state.get("agents", {}).items():
        start = max(window_start, rec.get("first_seen", window_start))
        events = [e for e in by_id.get(agent_id, []) if start < e[0] <= now]
        status = events[0][4] if events else rec.get("state")
        t, online = start, 0.0
        for e in events:
            if status == "N":
                online += e[0] - t
            t, status = e[0], e[5]
        if status == "N":
            online += now - t
        span = now - start
        availability = online / span if span >= 60 else (1.0 if rec.get("state") == "N" else 0.0)
        changes = sum(1 for e in by_id.get(agent_id, []) if now - WINDOW <= e[0] <= now)
        out[agent_id] = {"availability": availability, "changes": changes}
    return out, window_start


def report_rows(state, changed, now):
    """Every monitored device with its status details, changed devices first."""
    analytics, window_start = device_analytics(state, now)
    rows = []
    for agent_id, rec in state.get("agents", {}).items():
        since = rec.get("since", now)
        known = rec.get("since_known", False)
        in_status = fmt_duration(now - since)
        rows.append({
            "id": agent_id,
            "name": rec.get("name", agent_id),
            "group": rec.get("group") or "No group",
            "state": rec.get("state"),
            "status": status_label(rec.get("state")),
            "change": changed.get(agent_id, ""),
            "since_ts": since,
            "since_known": known,
            "since": fmt_iso(since) if known else f"before {fmt_iso(since)}",
            "in_status": in_status if known else f"over {in_status}",
            "last_online": ("Now" if rec.get("state") == "N" else
                            fmt_iso(rec["last_online"]) if rec.get("last_online") else
                            "Not since monitoring began"),
            "since_short": fmt_short(since) if known else f"before {fmt_short(since)}",
            "last_online_short": ("Now" if rec.get("state") == "N" else
                                  fmt_short(rec["last_online"]) if rec.get("last_online") else "Not seen"),
            "changes_7d": analytics[agent_id]["changes"],
            "availability": analytics[agent_id]["availability"],
            "hardware": rec.get("hardware", ""),
            "access": rec.get("access", ""),
            "shared_by": rec.get("shared_by", ""),
        })
    order = {"F": 0, "D": 1, "W": 2, "N": 3}
    rows.sort(key=lambda r: (r["change"] == "", order.get(r["state"], 2), r["group"].lower(), r["name"].lower()))
    return rows, window_start


# ---------------------------------------------------------------- CSV

def build_csv(rows, now):
    tz = tz_label(now)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Device", "Group", "Status", "Changed in this alert", f"Status since ({tz})",
                     "Time in status", f"Last seen online ({tz})", "Status changes (7 days)",
                     "Availability (7 days)", "Hardware", "Access", "Shared by", "Agent ID"])
    for r in rows:
        writer.writerow([r["name"], r["group"], r["status"], r["change"], r["since"], r["in_status"],
                         r["last_online"], r["changes_7d"], fmt_pct(r["availability"]),
                         r["hardware"], r["access"], r["shared_by"], r["id"]])
    return buf.getvalue().encode("utf-8-sig")  # BOM so Excel reads names correctly


# ---------------------------------------------------------------- PDF report

REPORT_CSS = """
* { box-sizing: border-box; }
body { margin: 0; color: #14233C; font-size: 9.2pt; line-height: 1.45;
       font-family: "Noto Sans", "Segoe UI", "Liberation Sans", "DejaVu Sans", Arial, sans-serif;
       -webkit-print-color-adjust: exact; }
.num, .t, .figures b, svg text { font-variant-numeric: tabular-nums; }
.t, .nw { white-space: nowrap; }
h1 { font-size: 21pt; font-weight: 600; margin: 0; letter-spacing: -0.015em; line-height: 1.15; }
h2 { font-size: 11.5pt; font-weight: 600; margin: 20px 0 8px; padding-bottom: 4px;
     border-bottom: 1px solid #DDE3EA; break-after: avoid; }
p { margin: 0 0 6px; }
.meta { color: #5B6B82; margin-top: 5px; }
.lead { font-size: 12.5pt; margin: 16px 0 10px; max-width: 165mm; }
.figures { display: flex; border-top: 2px solid #14233C; border-bottom: 1px solid #DDE3EA; margin-bottom: 4px; }
.figures div { flex: 1; padding: 8px 10px 9px; border-left: 1px solid #DDE3EA; }
.figures div:first-child { border-left: 0; padding-left: 0; }
.figures b { display: block; font-size: 15pt; font-weight: 600; line-height: 1.2; }
.figures span { color: #5B6B82; font-size: 8.3pt; }
table { width: 100%; border-collapse: collapse; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { text-align: left; font-weight: 600; color: #5B6B82; font-size: 8.2pt; padding: 4px 6px;
     border-bottom: 1px solid #14233C; }
td { padding: 3.5px 6px; border-bottom: 1px solid #EDF0F4; vertical-align: top; }
.num { text-align: right; white-space: nowrap; }
.muted { color: #5B6B82; }
.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; vertical-align: 0.5px; }
.s-N { background: #1F8A70; } .s-F { background: #C8323C; } .s-other { background: #9AA5B4; }
.changed { color: #B7791F; font-weight: 600; }
.legend { color: #5B6B82; font-size: 8.3pt; margin-bottom: 6px; }
.legend span { margin-right: 14px; white-space: nowrap; }
.map-group { margin: 0 0 10px; break-inside: avoid; }
.map-label { display: flex; justify-content: space-between; font-size: 8.5pt; margin-bottom: 3px; }
.cells { display: flex; flex-wrap: wrap; gap: 2.5px; }
.cell { width: 9px; height: 9px; border-radius: 1.5px; }
.cell.ring { outline: 1.6px solid #B7791F; outline-offset: 1.2px; }
.bar { display: flex; height: 7px; width: 100%; min-width: 60px; margin-top: 4px; }
.bar i { display: block; height: 100%; }
.cols { display: flex; gap: 18px; break-inside: avoid; }
.keep { break-inside: avoid; }
.cols > div { flex: 1; min-width: 0; }
.note { color: #5B6B82; font-size: 8.2pt; margin-top: 14px; }
.empty { color: #5B6B82; padding: 6px 0; }
svg text { font-family: inherit; }
"""

PDF_FOOTER = ("<div style=\"font-family:Arial,Helvetica,sans-serif;font-size:7.5px;color:#5B6B82;width:100%;"
              "padding:0 14mm;display:flex;justify-content:space-between\">"
              "<span>{title}</span><span>Page <span class=\"pageNumber\"></span> of "
              "<span class=\"totalPages\"></span></span></div>")


def esc(value):
    return html.escape(str(value))


def status_dot(code):
    cls = f"s-{code}" if code in ("N", "F") else "s-other"
    return f"<span class='dot {cls}'></span>"


def trend_svg(history, now, width=680, height=150):
    """Online devices over the last 24 hours, with the monitored total for reference."""
    start = now - 86400
    points = [h for h in history if h[0] >= start]
    if len(points) < 2:
        return "<p class='empty'>The 24-hour trend appears once the monitor has a few checks of history.</p>"
    left, right, top, bottom = 34, 8, 8, 20
    plot_w, plot_h = width - left - right, height - top - bottom
    y_max = max(h[2] for h in points) or 1
    low = min(h[1] for h in points)
    pad = max(2, (y_max - low) * 0.25)
    y_min = max(0, int(low - pad))
    span = max(1, y_max - y_min)
    x = lambda t: left + (t - start) / 86400 * plot_w
    y = lambda v: top + plot_h - (v - y_min) / span * plot_h
    parts = [f"<svg width='{width}' height='{height}' viewBox='0 0 {width} {height}' xmlns='http://www.w3.org/2000/svg'>"]
    for v in (y_min, (y_min + y_max) / 2, y_max):
        parts.append(f"<line x1='{left}' x2='{width - right}' y1='{y(v):.1f}' y2='{y(v):.1f}' stroke='#EDF0F4'/>")
        parts.append(f"<text x='{left - 6}' y='{y(v) + 3:.1f}' font-size='8' fill='#5B6B82' text-anchor='end'>{int(round(v))}</text>")
    hour = datetime.fromtimestamp(start, TZ).replace(minute=0, second=0, microsecond=0)
    tick = hour.timestamp() + 3600
    while tick <= now:
        label_hour = datetime.fromtimestamp(tick, TZ).hour
        if label_hour % 6 == 0:
            parts.append(f"<line x1='{x(tick):.1f}' x2='{x(tick):.1f}' y1='{top}' y2='{top + plot_h}' stroke='#EDF0F4'/>")
            parts.append(f"<text x='{x(tick):.1f}' y='{height - 6}' font-size='8' fill='#5B6B82' text-anchor='middle'>{label_hour:02d}:00</text>")
        tick += 3600
    total_line = " ".join(f"{x(h[0]):.1f},{y(h[2]):.1f}" for h in points)
    online_line = " ".join(f"{x(h[0]):.1f},{y(h[1]):.1f}" for h in points)
    area = f"{x(points[0][0]):.1f},{y(y_min):.1f} {online_line} {x(points[-1][0]):.1f},{y(y_min):.1f}"
    parts.append(f"<polygon points='{area}' fill='#1F8A70' fill-opacity='0.10'/>")
    parts.append(f"<polyline points='{total_line}' fill='none' stroke='#9AA5B4' stroke-width='1' stroke-dasharray='3 3'/>")
    parts.append(f"<polyline points='{online_line}' fill='none' stroke='#1F8A70' stroke-width='1.6'/>")
    parts.append("</svg>")
    return "".join(parts)


def changes_svg(events, now, width=680, height=78):
    """Status changes per hour over the last 24 hours (offline in red, online in green)."""
    start = now - 86400
    buckets = [[0, 0] for _ in range(24)]
    for e in events:
        if start <= e[0] <= now:
            i = min(23, int((e[0] - start) // 3600))
            if e[5] == "F":
                buckets[i][0] += 1
            elif e[5] == "N":
                buckets[i][1] += 1
    peak = max((a + b for a, b in buckets), default=0)
    if peak == 0:
        return "<p class='empty'>No status changes in the last 24 hours.</p>"
    left, right, top, bottom = 34, 8, 6, 16
    plot_w, plot_h = width - left - right, height - top - bottom
    slot = plot_w / 24
    parts = [f"<svg width='{width}' height='{height}' viewBox='0 0 {width} {height}' xmlns='http://www.w3.org/2000/svg'>",
             f"<line x1='{left}' x2='{width - right}' y1='{top + plot_h}' y2='{top + plot_h}' stroke='#DDE3EA'/>",
             f"<text x='{left - 6}' y='{top + 8}' font-size='8' fill='#5B6B82' text-anchor='end'>{peak}</text>"]
    for i, (off, on) in enumerate(buckets):
        bx = left + i * slot + slot * 0.18
        bw = slot * 0.64
        h_off = off / peak * plot_h
        h_on = on / peak * plot_h
        if off:
            parts.append(f"<rect x='{bx:.1f}' y='{top + plot_h - h_off:.1f}' width='{bw:.1f}' height='{h_off:.1f}' fill='#C8323C'/>")
        if on:
            parts.append(f"<rect x='{bx:.1f}' y='{top + plot_h - h_off - h_on:.1f}' width='{bw:.1f}' height='{h_on:.1f}' fill='#1F8A70'/>")
    parts.append(f"<text x='{left}' y='{height - 3}' font-size='8' fill='#5B6B82'>24 h ago</text>")
    parts.append(f"<text x='{width - right}' y='{height - 3}' font-size='8' fill='#5B6B82' text-anchor='end'>Now</text>")
    parts.append("</svg>")
    return "".join(parts)


def build_report_html(state, rows, changed, now, window_start, title, reason=None):
    total = len(rows)
    online = sum(1 for r in rows if r["state"] == "N")
    offline_rows = sorted((r for r in rows if r["state"] == "F"), key=lambda r: -r["since_ts"])
    went_off = [r for r in rows if r["change"] == "Went offline"]
    came_on = [r for r in rows if r["change"] == "Came online"]
    events = state.get("events", [])
    day_events = [e for e in events if now - 86400 <= e[0] <= now]
    fleet_avail = sum(r["availability"] for r in rows) / total if total else 0
    tz = tz_label(now)

    if went_off or came_on:
        bits = []
        if went_off:
            bits.append(f"{len(went_off)} device{'' if len(went_off) == 1 else 's'} went offline")
        if came_on:
            bits.append(f"{len(came_on)} came back online")
        trigger = "Sent because " + " and ".join(bits) + "."
    else:
        trigger = reason or "Requested report. No status changes are highlighted."
    lead = f"{online} of {total} monitored devices are online ({fmt_pct(online / total if total else 0)})."
    if went_off or came_on:
        lead += " " + trigger.replace("Sent because ", "").capitalize()

    out = [f"<!doctype html><html><head><meta charset='utf-8'><title>{esc(title)}</title>"
           f"<style>{REPORT_CSS}</style></head><body>"]
    out.append(f"<h1>{esc(title)}</h1>")
    out.append(f"<p class='meta'>Status as of {esc(fmt_time(now))} {esc(tz)}. {esc(trigger)}</p>")
    out.append(f"<p class='lead'>{esc(lead)}</p>")
    out.append("<div class='figures'>"
               f"<div><b>{online}</b><span>Online</span></div>"
               f"<div><b>{total - online}</b><span>Not online</span></div>"
               f"<div><b>{len(went_off)} / {len(came_on)}</b><span>Offline / online now</span></div>"
               f"<div><b>{len(day_events)}</b><span>Changes in 24 h</span></div>"
               f"<div><b>{fmt_pct(fleet_avail)}</b><span>Average availability</span></div>"
               "</div>")

    # Changes in this report
    out.append("<h2>Changes in this report</h2>")
    if went_off or came_on:
        out.append("<table><thead><tr><th style='width:32%'>Device</th><th>Group</th><th>Change</th>"
                   "<th>Detail</th></tr></thead><tbody>")
        for r in went_off + came_on:
            rec = state["agents"].get(r["id"], {})
            if r["change"] == "Went offline":
                detail = f"Offline since {fmt_short(rec.get('off_since', now))}"
            elif rec.get("down_known", True):
                detail = f"Was offline for {fmt_duration(rec.get('down_for', 0))}"
            else:
                detail = f"Was offline for over {fmt_duration(rec.get('down_for', 0))}, since before monitoring began"
            out.append(f"<tr><td><b>{esc(r['name'])}</b></td><td class='nw'>{esc(r['group'])}</td>"
                       f"<td class='changed nw'>{status_dot(r['state'])}{esc(r['change'])}</td><td>{esc(detail)}</td></tr>")
        out.append("</tbody></table>")
    else:
        out.append("<p class='empty'>None. This report shows the current status of every monitored device.</p>")

    # Fleet map
    out.append("<h2>Fleet map</h2>")
    out.append("<div class='legend'><span><span class='dot s-N'></span>Online</span>"
               "<span><span class='dot s-F'></span>Offline</span>"
               "<span><span class='dot s-other'></span>Disabled or other</span>"
               "<span><span class='dot' style='background:#fff;outline:1.6px solid #B7791F'></span>Changed in this report</span></div>")
    groups = {}
    for r in sorted(rows, key=lambda r: (r["group"].lower(), r["name"].lower())):
        groups.setdefault(r["group"], []).append(r)
    for group, members in groups.items():
        g_on = sum(1 for r in members if r["state"] == "N")
        cells = "".join(
            f"<div class='cell {'s-' + r['state'] if r['state'] in ('N', 'F') else 's-other'}"
            f"{' ring' if r['change'] else ''}'></div>" for r in members)
        out.append(f"<div class='map-group'><div class='map-label'><span>{esc(group)}</span>"
                   f"<span class='muted'>{g_on} of {len(members)} online</span></div>"
                   f"<div class='cells'>{cells}</div></div>")

    # Trend
    out.append("<h2>Last 24 hours</h2>")
    out.append("<p class='muted'>Devices online (green line) against devices monitored (dashed). "
               "The scale starts near the lowest value so dips are visible.</p>")
    out.append(trend_svg(state.get("history", []), now))
    out.append("<p class='muted' style='margin-top:8px'>Status changes per hour: went offline (red), came online (green).</p>")
    out.append(changes_svg(events, now))

    # By group
    out.append("<div class='keep'><h2>By group</h2>")
    out.append("<table><thead><tr><th>Group</th><th class='num'>Devices</th><th class='num'>Online</th>"
               "<th class='num'>Offline</th><th class='num'>Online now</th><th class='num'>Availability</th>"
               "<th style='width:28%'></th></tr></thead><tbody>")
    for group, members in groups.items():
        n = len(members)
        g_on = sum(1 for r in members if r["state"] == "N")
        g_off = sum(1 for r in members if r["state"] == "F")
        g_avail = sum(r["availability"] for r in members) / n
        bar = (f"<div class='bar'><i style='width:{g_on / n * 100:.2f}%;background:#1F8A70'></i>"
               f"<i style='width:{g_off / n * 100:.2f}%;background:#C8323C'></i>"
               f"<i style='flex:1;background:#DDE3EA'></i></div>")
        out.append(f"<tr><td>{esc(group)}</td><td class='num'>{n}</td><td class='num'>{g_on}</td>"
                   f"<td class='num'>{g_off}</td><td class='num'>{fmt_pct(g_on / n)}</td>"
                   f"<td class='num'>{fmt_pct(g_avail)}</td><td>{bar}</td></tr>")
    out.append("</tbody></table></div>")

    # Currently offline
    out.append(f"<h2>Currently offline ({len(offline_rows)})</h2>")
    if offline_rows:
        out.append("<table><thead><tr><th>Device</th><th>Group</th><th>Offline since</th>"
                   "<th>Offline for</th><th>Last online</th></tr></thead><tbody>")
        for r in offline_rows:
            mark = " <span class='changed'>new</span>" if r["change"] else ""
            out.append(f"<tr><td>{esc(r['name'])}{mark}</td><td class='nw'>{esc(r['group'])}</td>"
                       f"<td class='t'>{esc(r['since_short'])}</td><td class='t'>{esc(r['in_status'])}</td>"
                       f"<td class='t'>{esc(r['last_online_short'])}</td></tr>")
        out.append("</tbody></table>")
        if any(r["last_online_short"] == "Not seen" for r in offline_rows):
            out.append("<p class='muted' style='margin-top:4px'>Not seen: hasn't been online since monitoring began.</p>")
    else:
        out.append("<p class='empty'>Every monitored device is online.</p>")

    # Needs attention
    dead = [r for r in rows if r["availability"] == 0 and r["changes_7d"] == 0]
    low = sorted((r for r in rows if r["availability"] < 0.9995 and r not in dead),
                 key=lambda r: (r["availability"], r["name"].lower()))[:12]
    flappy = sorted((r for r in rows if r["changes_7d"] > 0), key=lambda r: (-r["changes_7d"], r["name"].lower()))[:12]
    out.append("<div class='keep'><h2>Needs attention</h2><div class='cols'><div>")
    out.append("<p class='muted'>Lowest availability</p>")
    if low:
        out.append("<table><thead><tr><th>Device</th><th class='num'>Availability</th></tr></thead><tbody>")
        out += [f"<tr><td>{status_dot(r['state'])}{esc(r['name'])}</td><td class='num'>{fmt_pct(r['availability'])}</td></tr>" for r in low]
        out.append("</tbody></table>")
    else:
        out.append("<p class='empty'>No device had partial downtime in the period.</p>")
    if dead:
        out.append(f"<p class='muted' style='margin-top:4px'>{len(dead)} device{'' if len(dead) == 1 else 's'} "
                   "stayed offline for the whole period and are listed under Currently offline.</p>")
    out.append("</div><div><p class='muted'>Most status changes</p>")
    if flappy:
        out.append("<table><thead><tr><th>Device</th><th class='num'>Changes</th></tr></thead><tbody>")
        out += [f"<tr><td>{status_dot(r['state'])}{esc(r['name'])}</td><td class='num'>{r['changes_7d']}</td></tr>" for r in flappy]
        out.append("</tbody></table>")
    else:
        out.append("<p class='empty'>No status changes in the period.</p>")
    out.append("</div></div></div>")

    # Recent changes
    recent = sorted(day_events, key=lambda e: -e[0])[:40]
    out.append("<h2>Recent status changes (last 24 hours)</h2>")
    if recent:
        out.append("<table><thead><tr><th>Time</th><th>Device</th><th>Group</th><th>Change</th></tr></thead><tbody>")
        for e in recent:
            out.append(f"<tr><td class='muted t'>{esc(fmt_short(e[0]))}</td><td>{esc(e[2])}</td><td class='nw'>{esc(e[3] or 'No group')}</td>"
                       f"<td>{status_dot(e[4])}{esc(status_label(e[4]))} to {status_dot(e[5])}{esc(status_label(e[5]))}</td></tr>")
        out.append("</tbody></table>")
        if len(day_events) > len(recent):
            out.append(f"<p class='muted'>Showing the latest {len(recent)} of {len(day_events)} changes.</p>")
    else:
        out.append("<p class='empty'>No status changes in the last 24 hours.</p>")

    period = "the last 7 days" if now - window_start >= WINDOW - 60 else f"the period since monitoring began on {fmt_time(window_start)}"
    out.append(f"<p class='note'>Availability is the share of time each device was online over {esc(period)}, "
               f"measured at each check (every {fmt_duration(CHECK_INTERVAL)}); brief drops between checks aren't seen. "
               f"Devices monitored: {esc(describe_filters())}. Times are {esc(tz)}. "
               "The full device list with every detail is in the attached CSV.</p>")
    out.append("</body></html>")
    return "".join(out)


def render_pdf(page_source, html_text, title):
    """Render HTML to PDF bytes with Chromium (page_source: a browser or browser context)."""
    page = page_source.new_page()
    try:
        page.set_content(html_text, wait_until="load")
        return page.pdf(format="A4", print_background=True, display_header_footer=True,
                        header_template="<span></span>", footer_template=PDF_FOOTER.format(title=esc(title)),
                        margin={"top": "14mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
    finally:
        page.close()


def build_report_files(state, changed, now, page_source, reason=None):
    """Return email attachments [(filename, bytes, maintype, subtype)] and keep copies in REPORTS_DIR.

    reason: the PDF's "why this report" line when nothing changed (default: requested).
    """
    rows, window_start = report_rows(state, changed, now)
    stamp = datetime.fromtimestamp(now, TZ).strftime("%Y-%m-%d_%H%M")
    files = [(f"{REPORT_SLUG}-devices-{stamp}.csv", build_csv(rows, now), "text", "csv")]
    try:
        report_html = build_report_html(state, rows, changed, now, window_start, REPORT_TITLE, reason)
        pdf = render_pdf(page_source, report_html, REPORT_TITLE)
        files.append((f"{REPORT_SLUG}-status-report-{stamp}.pdf", pdf, "application", "pdf"))
    except Exception as exc:
        log(f"PDF report failed, sending the CSV only: {exc}")
    try:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        for name, data, _, _ in files:
            with open(os.path.join(REPORTS_DIR, name), "wb") as f:
                f.write(data)
        # Oldest first by time: sorting by name put every "-devices-" CSV before the
        # PDFs, so once there were 200 files the newest CSVs were the ones deleted.
        saved = sorted(os.listdir(REPORTS_DIR), key=lambda n: os.path.getmtime(os.path.join(REPORTS_DIR, n)))
        for old in saved[:-200]:  # keep the latest 200 files
            os.remove(os.path.join(REPORTS_DIR, old))
    except OSError as exc:
        log(f"Could not save report copies: {exc}")
    return files


# ---------------------------------------------------------------- emails

def change_lines(kind, ids, known, now):
    recs = sorted((known[a] for a in ids), key=lambda r: (r["group"].lower(), r["name"].lower()))
    rows = []
    for r in recs:
        if kind == "down":
            detail = f"offline since {fmt_time(r.get('off_since', now))}"
        elif r.get("down_known", True):
            detail = f"was offline for {fmt_duration(r.get('down_for', 0))}"
        else:
            detail = f"was offline for over {fmt_duration(r.get('down_for', 0))}, since before monitoring began"
        rows.append((r["group"] or "No group", r["name"], detail))
    return rows


def build_change_email(down, up, known, online, total, now=None):
    """One email for all changes found in a check (attachments are added by the caller)."""
    now = time.time() if now is None else now
    down_rows = change_lines("down", down, known, now)
    up_rows = change_lines("up", up, known, now)
    names = [r[1] for r in down_rows + up_rows]
    preview = ", ".join(names[:3]) + (f" +{len(names) - 3} more" if len(names) > 3 else "")
    if down and up:
        subject = f"🔴 {len(down)} offline, 🟢 {len(up)} back online: {preview}"
    elif down:
        subject = f"🔴 {len(down)} device{'s' if len(down) > 1 else ''} went offline: {preview}"
    else:
        subject = f"🟢 {len(up)} device{'s' if len(up) > 1 else ''} back online: {preview}"
    if len(subject) > 150:
        subject = subject[:147] + "..."
    footer = f"Online now: {online}/{total} monitored devices. Checked {fmt_time(now)}."
    attached = "Attached: the full device list (CSV) and a status report (PDF)."

    text, blocks = [], []
    for icon, title, rows in (("🔴", "went offline", down_rows), ("🟢", "back online", up_rows)):
        if not rows:
            continue
        heading = f"{icon} {len(rows)} device{'s' if len(rows) > 1 else ''} {title}"
        text += [heading, ""]
        text += [f"  • {name} ({group}): {detail}" for group, name, detail in rows]
        text.append("")
        cells = "".join(
            "<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>{esc(group)}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee'><b>{esc(name)}</b></td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>{esc(detail[0].upper() + detail[1:])}</td>"
            "</tr>" for group, name, detail in rows)
        blocks.append(
            f"<p style='font-size:16px;margin:16px 0 8px'><b>{esc(heading)}</b></p>"
            "<table style='border-collapse:collapse'><tr style='background:#f4f4f4;text-align:left'>"
            "<th style='padding:6px 10px'>Group</th><th style='padding:6px 10px'>Device</th>"
            f"<th style='padding:6px 10px'>Detail</th></tr>{cells}</table>")
    text += [footer, attached]
    body_html = ("<div style='font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222'>"
                 + "".join(blocks)
                 + f"<p style='color:#666;margin-top:14px'>{esc(footer)}<br>{esc(attached)}</p></div>")
    return {"subject": subject, "text": "\n".join(text), "html": body_html, "to": ALERT_EMAILS}


def build_status_email(state, now, note=""):
    """The status report email (attachments are added by the caller). note: an extra line, e.g. the schedule."""
    agents = state.get("agents", {})
    online = sum(1 for r in agents.values() if r.get("state") == "N")
    subject = f"📊 {REPORT_TITLE}: {online}/{len(agents)} online"
    attached = "Attached: the full device list (CSV) and a status report (PDF)."
    text = (f"{REPORT_TITLE}\n\n{online} of {len(agents)} monitored devices online, as of {fmt_time(now)}.\n\n"
            + attached + (f"\n{note}" if note else ""))
    body_html = ("<div style='font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222'>"
                 f"<p style='font-size:16px'><b>{esc(REPORT_TITLE)}</b></p>"
                 f"<p>{online} of {len(agents)} monitored devices online, as of {esc(fmt_time(now))}.</p>"
                 f"<p style='color:#666'>{esc(attached)}{'<br>' + esc(note) if note else ''}</p></div>")
    return {"subject": subject, "text": text, "html": body_html, "to": ALERT_EMAILS}


def admin_notice(subject, text):
    return {"subject": subject, "text": text, "html": None, "to": [ADMIN_EMAIL]}


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, STATE_FILE)


# ---------------------------------------------------------------- notifications

def send_email(mail):
    msg = EmailMessage()
    msg["Subject"] = mail["subject"]
    msg["From"] = f"DWService Monitor <{GMAIL_USER}>"
    msg["To"] = ", ".join(mail["to"])
    msg.set_content(mail["text"])
    if mail.get("html"):
        msg.add_alternative(mail["html"], subtype="html")
    for filename, data, maintype, subtype in mail.get("attachments", []):
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    try:
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
            server.ehlo()
            if server.has_extn("starttls"):
                server.starttls()
        with server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        return True
    except smtplib.SMTPAuthenticationError:
        log("Gmail rejected the login: check GMAIL_USER and GMAIL_APP_PASSWORD (will retry)")
    except Exception as exc:
        log(f"Email send failed (will retry): {exc}")
    return False


def ping_healthcheck():
    if not HC_PING_URL:
        return
    try:
        with urllib.request.urlopen(HC_PING_URL, timeout=10) as resp:
            resp.read()
    except Exception as exc:
        log(f"Healthcheck ping failed: {exc}")


MAX_PENDING_CHANGES = 500  # status changes kept for resending while the backend is unreachable


def change_events(down, up, known, now):
    """The devices update_state() confirmed went offline / came back online in this
    check, as the dashboard backend takes them (times are Unix seconds)."""
    events = [{"agent_id": a, "change": "offline", "at": int(now),
               "offline_since": int(known[a].get("off_since", now))} for a in down]
    events += [{"agent_id": a, "change": "online", "at": int(now),
                "down_seconds": int(known[a].get("down_for", 0)),
                "down_known": bool(known[a].get("down_known", True))} for a in up]
    return events


def push_devices(agents, changes=()):
    """Send this check's monitored devices, and the status changes not yet delivered,
    to the dashboard backend (Device Mapping page; the changes notify the support
    accounts).

    Returns the backend's reply ({"received", "new_devices", "unmapped", "unmapped_names",
    "changes_received", "changes_new", "changes_stored"}) or None when sync is off or the
    request failed. Never raises: a backend problem must not stop the checks or emails.
    """
    if not BACKEND_SYNC_URL or not BACKEND_SYNC_KEY or not agents:
        return None
    payload = {
        "devices": [
            {"agent_id": agent_id, "name": a["name"], "group": a["group"], "state": a["state"],
             "hardware": a["hardware"]}
            for agent_id, a in agents.items()],
        "changes": list(changes),
    }
    request = urllib.request.Request(
        BACKEND_SYNC_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-api-key": BACKEND_SYNC_KEY,
                 "User-Agent": "dw-dashboard-monitor"})
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("message") or exc.reason
        except Exception:
            detail = exc.reason
        log(f"Backend sync failed: HTTP {exc.code} {detail}")
    except Exception as exc:
        log(f"Backend sync failed: {exc}")
    return None


def sync_summary(reply):
    """One line describing a backend sync reply."""
    text = f"Backend sync OK: {reply.get('received', 0)} devices"
    if reply.get("new_devices"):
        text += f", {reply['new_devices']} new"
    unmapped = reply.get("unmapped", 0)
    if unmapped:
        names = reply.get("unmapped_names") or []
        more = ", ..." if unmapped > len(names) else ""
        text += f", {unmapped} not mapped to a store ({', '.join(names)}{more})"
    if reply.get("changes_stored") is False:
        text += "; status changes not stored (apply sql/dw-device-events-schema.sql on the backend)"
    return text


# ---------------------------------------------------------------- modes

def require_email():
    missing = [k for k, v in {"GMAIL_USER": GMAIL_USER, "GMAIL_APP_PASSWORD": GMAIL_APP_PASSWORD,
                              "ALERT_EMAILS": ALERT_EMAILS}.items() if not v]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}")


def describe_filters():
    inc = ", ".join(INCLUDE_KEYWORDS) or "everything"
    exc = ", ".join(EXCLUDE_KEYWORDS) or "nothing"
    return f"including: {inc}; excluding: {exc}"


def run_login():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        context, page = launch_browser(p, DEBUG_PORT)
        watcher = ShareWatcher(page)
        watcher.reload()
        print(
            "\nBrowser is open on the VM. To log in from your PC:\n"
            f"  1. Run:  ssh -L {DEBUG_PORT}:127.0.0.1:{DEBUG_PORT} <user>@<vm-ip>\n"
            f"  2. In Chrome open chrome://inspect/#devices, Configure... add localhost:{DEBUG_PORT}\n"
            "  3. Click 'inspect' under the DWService page\n"
            "  4. Log in, TICK 'trusted device', then open Shares\n"
            "Waiting up to 30 minutes...\n", flush=True)
        items = watcher.wait_for_list(0, 30 * 60)
        if items is None:
            context.close()
            sys.exit("Timed out without seeing your agent list. Run --login again.")
        print(f"Logged in: {len({i.get('idAgent') for i in items})} agents visible.", flush=True)
        print("Checking that the VM can log itself back in...", flush=True)
        watcher.trace.clear()
        items, how = watcher.fetch(force_reload=True)
        if items is None:
            print("The re-login check couldn't load the agent list.", flush=True)
            watcher.report_failure()
            context.close()
            sys.exit("Send me the screenshot and the steps above so I can see where it got stuck.")
        context.close()
        print(f"Automatic re-login works (via {how}). Next: run --check, then start the service.")


def run_check():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        context, page = launch_browser(p)
        watcher = ShareWatcher(page)
        items, how = watcher.fetch(force_reload=True)
        if items is None:
            print("Could not read the agent list.", flush=True)
            watcher.report_failure()
            context.close()
            sys.exit(1)
        agents = select_agents(items)
        online = sum(1 for a in agents.values() if a["state"] == "N")
        total_seen = len({i.get("idAgent") for i in items})
        print(f"Read {total_seen} agents via {how}.")
        print(f"Monitoring {len(agents)} of them ({describe_filters()}): "
              f"{online} online, {len(agents) - online} offline.")
        groups = {}
        for a in agents.values():
            g = groups.setdefault(a["group"] or "No group", [0, 0])
            g[0 if a["state"] == "N" else 1] += 1
        for name, (on, off) in sorted(groups.items()):
            print(f"  {name}: {on} online, {off} offline")
        if BACKEND_SYNC_URL and BACKEND_SYNC_KEY:
            reply = push_devices(agents)
            print(sync_summary(reply) if reply is not None else "Backend sync failed, see the error above.")
        else:
            print("Backend sync is off (set BACKEND_SYNC_URL and BACKEND_SYNC_KEY in .env to turn it on).")
        items, how = watcher.fetch()
        print(f"Repeat refresh worked via {how}." if items is not None
              else "Repeat refresh failed; the service will fall back to page reloads.")
        context.close()


def launch_plain_browser(playwright):
    """A throwaway browser for rendering PDFs; doesn't touch the DWService profile."""
    try:
        return playwright.chromium.launch(headless=True, channel="chromium")
    except Exception:
        return playwright.chromium.launch(headless=True)


def run_report(send):
    from playwright.sync_api import sync_playwright
    state = load_state()
    if not state.get("agents"):
        sys.exit("No device data yet. Start the service and wait for its first check, then try again.")
    if send:
        require_email()
    now = state.get("last_check", time.time())
    with sync_playwright() as p:
        browser = launch_plain_browser(p)
        files = build_report_files(state, {}, now, browser)
        browser.close()
    for name, data, _, _ in files:
        print(f"Saved {os.path.join(REPORTS_DIR, name)} ({len(data) // 1024} KB)")
    if send:
        mail = build_status_email(state, now)
        mail["attachments"] = files
        ok = send_email(mail)
        print(f"Emailed to {', '.join(ALERT_EMAILS)}." if ok else "Email failed, see the error above.")
        sys.exit(0 if ok else 1)


def run_monitor():
    from playwright.sync_api import sync_playwright
    require_email()
    state = load_state()
    outbox, failures, fail_alerted, last_how = [], 0, False, None
    last_sync = None  # last backend sync summary logged, so an unchanged one isn't repeated
    # Status changes not yet delivered to the dashboard backend, sent with every report
    # until one gets through (the backend ignores ones it already has).
    pending_changes = []
    sync_on = bool(BACKEND_SYNC_URL and BACKEND_SYNC_KEY)
    progress = {"t": time.time()}
    stall_limit = max(900, 3 * CHECK_INTERVAL)

    def watchdog():
        # If the browser ever hangs, exit so systemd (Restart=always) starts a fresh one.
        while True:
            time.sleep(30)
            if time.time() - progress["t"] > stall_limit:
                log(f"Watchdog: no progress for {stall_limit}s, restarting")
                os._exit(1)

    threading.Thread(target=watchdog, daemon=True).start()
    with sync_playwright() as p:
        context, page = launch_browser(p)
        watcher = ShareWatcher(page)
        log(f"Monitor started: checking every {CHECK_INTERVAL}s; {describe_filters()}; "
            f"emailing {', '.join(ALERT_EMAILS)}")
        if CHANGE_ALERTS:
            log(f"Status-change alerts are on: emailing when a device goes offline "
                f"({CONFIRM_CHECKS} offline check(s) in a row) or comes back online")
        else:
            log("Status-change alerts are off (CHANGE_ALERTS): changes are logged and shown in the scheduled reports")
            if not REPORT_TIMES:
                log("Warning: REPORT_TIMES is empty too, so no device emails will be sent at all")
        if BACKEND_SYNC_URL and BACKEND_SYNC_KEY:
            log(f"Sending each check's devices to {BACKEND_SYNC_URL}")
        elif BACKEND_SYNC_URL or BACKEND_SYNC_KEY:
            log("Backend sync is off: set both BACKEND_SYNC_URL and BACKEND_SYNC_KEY in .env")
        if REPORT_TIMES:
            log(f"Emailing the status report daily at {describe_report_times()} ({tz_label(time.time())})")
            if not state.get("last_report_slot"):
                # First run with scheduled reports: start with the next one, not one already past.
                state["last_report_slot"] = last_report_slot(time.time()) or 0
        while True:
            started = progress["t"] = time.time()
            try:
                items, how = watcher.fetch()
            except Exception as exc:
                log(f"Check failed: {exc}")
                items, how = None, None

            if items is None:
                failures += 1
                log(f"Could not read the agent list ({failures} in a row)")
                watcher.save_debug()
                if failures >= FAIL_ALERT_AFTER and not fail_alerted:
                    fail_alerted = True
                    outbox.append(admin_notice(
                        "⚠️ DWService monitor can't read the device list",
                        f"The monitor failed {failures} checks in a row, so device statuses aren't being updated "
                        "and scheduled reports are held until it recovers (skipped if over 3 hours late).\n"
                        "If DWService logged it out: stop the service, run --login again, and restart it.\n"
                        f"A screenshot of what the browser saw is in {DEBUG_DIR}/last-failure.png on the VM."))
            else:
                if how != last_how:
                    log(f"Reading the list via {how}")
                    last_how = how
                if fail_alerted:
                    outbox.append(admin_notice("✅ DWService monitor is working again",
                                               "The monitor is reading the device list again."))
                failures, fail_alerted = 0, False
                now = time.time()
                agents = select_agents(items)
                down, up, online, total = update_state(state, agents, now=now)
                report_slot = take_due_report(state, now)
                save_state(state)
                known = state["agents"]
                log(f"Check OK: {online}/{total} monitored devices online")
                if down:
                    log("Offline: " + ", ".join(known[a]["name"] for a in down))
                if up:
                    log("Back online: " + ", ".join(known[a]["name"] for a in up))
                if sync_on and (down or up):
                    pending_changes = (pending_changes + change_events(down, up, known, now))[-MAX_PENDING_CHANGES:]
                if (down or up) and CHANGE_ALERTS:
                    changed = {a: "Went offline" for a in down}
                    changed.update({a: "Came online" for a in up})
                    mail = build_change_email(down, up, known, online, total, now)
                    mail["attachments"] = build_report_files(state, changed, now, context)
                    outbox.append(mail)
                reply = push_devices(agents, pending_changes)
                if reply is not None:
                    summary = sync_summary(reply)
                    if summary != last_sync:
                        log(summary)
                        last_sync = summary
                    if pending_changes:
                        log(f"Sent {len(pending_changes)} status change(s) to the dashboard")
                    pending_changes = []
                else:
                    last_sync = None  # failures are logged by push_devices; log the next success
                    if pending_changes:
                        log(f"{len(pending_changes)} status change(s) kept to send with the next report")
                if report_slot is not None:
                    schedule = f"Sent daily at {describe_report_times()} ({tz_label(now)})."
                    mail = build_status_email(state, now, note=schedule)
                    mail["attachments"] = build_report_files(
                        state, {}, now, context, reason=f"Scheduled report. {schedule}")
                    outbox.append(mail)
                    log(f"Scheduled report for {fmt_time(report_slot)} queued")
                ping_healthcheck()

            del outbox[:-20]
            while outbox and send_email(outbox[0]):
                log(f"Emailed: {outbox[0]['subject']}")
                outbox.pop(0)

            if page.is_closed():
                page = context.new_page()
                watcher = ShareWatcher(page)
            progress["t"] = time.time()
            wait = CHECK_INTERVAL - (time.time() - started)
            upcoming = next_report_slot(time.time())
            if upcoming is not None:
                # Wake for a scheduled report so it goes out on time, with a fresh check.
                wait = min(wait, upcoming - time.time() + 5)
            page.wait_for_timeout(max(10.0, wait) * 1000)


def main():
    parser = argparse.ArgumentParser(description="Twice-daily email status reports for DWService devices.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--login", action="store_true", help="one-time login through Chrome's remote inspector")
    mode.add_argument("--check", action="store_true", help="read the agent list once and print a summary")
    mode.add_argument("--test-email", action="store_true", help="send a test email to ALERT_EMAILS")
    mode.add_argument("--report", action="store_true", help="save a CSV + PDF report from the latest data")
    mode.add_argument("--send-report", action="store_true", help="email a CSV + PDF report now")
    args = parser.parse_args()

    if args.report or args.send_report:
        run_report(send=args.send_report)
        return

    if args.test_email:
        require_email()
        plan = []
        if REPORT_TIMES:
            plan.append(f"a status report daily at {describe_report_times()} ({tz_label(time.time())})")
        if CHANGE_ALERTS:
            plan.append("a message when a monitored device goes offline or comes back online")
        ok = send_email({
            "subject": "✅ DWService monitor test email",
            "text": "Email is working. You'll get "
                    + (" and ".join(plan) if plan else "no device emails (REPORT_TIMES is empty and CHANGE_ALERTS is off)")
                    + f" here. Devices monitored: {describe_filters()}.",
            "html": None,
            "to": ALERT_EMAILS,
        })
        print(f"Sent to {', '.join(ALERT_EMAILS)}." if ok else "Failed, see the error above.")
        sys.exit(0 if ok else 1)
    if args.login:
        run_login()
    elif args.check:
        run_check()
    else:
        def stop(signum, frame):
            raise KeyboardInterrupt  # unwinds through Playwright so the browser closes cleanly

        signal.signal(signal.SIGTERM, stop)  # systemd stops services with SIGTERM
        try:
            run_monitor()
        except KeyboardInterrupt:
            log("Stopped.")


if __name__ == "__main__":
    main()
