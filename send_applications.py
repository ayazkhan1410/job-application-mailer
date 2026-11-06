"""Send job application emails with your resume attached, one at a time.

Usage:
    python send_applications.py            # dry run: shows what would be sent
    python send_applications.py --send     # actually sends
    python send_applications.py --send --limit 5
"""

import argparse
import csv
import mimetypes
import os
import random
import re
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

BASE = Path(__file__).resolve().parent
RECIPIENTS = BASE / "recipients.csv"
MESSAGE = BASE / "message.txt"
LOG = BASE / "sent_log.csv"
ENV = BASE / ".env"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_TIMEOUT = 30
MAX_ATTACHMENT_MB = 5
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def load_env():
    """Read KEY=VALUE pairs from .env without overriding real env vars."""
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require(name):
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Missing {name}. Add it to .env (see .env.example).")
    return value


def load_recipients():
    if not RECIPIENTS.exists():
        sys.exit(f"Not found: {RECIPIENTS}")
    seen, rows = set(), []
    with RECIPIENTS.open(newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            email = (row.get("email") or "").strip().lower()
            company = (row.get("company") or "").strip()
            role = (row.get("role") or "").strip()
            subject = (row.get("subject") or "").strip()
            if not EMAIL_RE.match(email):
                print(f"  skip line {i}: invalid email '{email}'")
                continue
            if email in seen:
                print(f"  skip line {i}: duplicate {email}")
                continue
            seen.add(email)
            rows.append({"email": email, "company": company, "role": role, "subject": subject})
    return rows


def already_handled():
    """Emails already sent, or whose result is uncertain, are never sent again automatically."""
    if not LOG.exists():
        return set()
    with LOG.open(newline="", encoding="utf-8") as f:
        return {r["email"] for r in csv.DictReader(f) if r["status"] in ("sent", "uncertain")}


def log(email, status, detail=""):
    new = not LOG.exists()
    with LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp_utc", "email", "status", "detail"])
        w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), email, status, detail[:200]])


def load_template():
    text = MESSAGE.read_text(encoding="utf-8")
    subject_line, _, body = text.partition("\n")
    if not subject_line.lower().startswith("subject:"):
        sys.exit("message.txt must start with a 'Subject: ...' line.")
    return subject_line.split(":", 1)[1].strip(), body.strip() + "\n"


def build_message(sender, name, r, subject, body, resume):
    """r is a recipient row; a non-empty 'subject' column overrides the template subject."""
    company = r["company"] or "your team"
    role = r["role"] or "Python/Django Backend Developer"
    msg = EmailMessage()
    msg["From"] = f"{name} <{sender}>"
    msg["To"] = r["email"]
    msg["Subject"] = (r["subject"] or subject).format(company=company, role=role)
    msg.set_content(body.format(company=company, role=role, name=name))
    ctype = mimetypes.guess_type(resume.name)[0] or "application/pdf"
    maintype, subtype = ctype.split("/", 1)
    msg.add_attachment(resume.read_bytes(), maintype=maintype, subtype=subtype, filename=resume.name)
    return msg


def connect(sender, password, attempts=3):
    """Connecting and logging in are safe to retry; nothing has been sent yet."""
    for n in range(1, attempts + 1):
        try:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT)
            server.login(sender, password)
            return server
        except smtplib.SMTPAuthenticationError:
            sys.exit("Gmail login failed. Use a Gmail App Password, not your normal password.")
        except (OSError, smtplib.SMTPException) as e:
            if n == attempts:
                sys.exit(f"Could not connect to Gmail: {e}")
            wait = 2 ** n + random.uniform(0, 1)
            print(f"  connection failed ({e}), retrying in {wait:.0f}s")
            time.sleep(wait)


def main():
    parser = argparse.ArgumentParser(description="Send job applications with your resume.")
    parser.add_argument("--send", action="store_true", help="actually send (default is dry run)")
    parser.add_argument("--limit", type=int, default=20, help="max emails this run (default 20)")
    parser.add_argument("--min-delay", type=int, default=60, help="min seconds between emails")
    parser.add_argument("--max-delay", type=int, default=120, help="max seconds between emails")
    parser.add_argument("--recipients", default="recipients.csv", help="CSV with email,company[,role,subject]")
    parser.add_argument("--message", default="message.txt", help="template file starting with 'Subject:'")
    args = parser.parse_args()
    global RECIPIENTS, MESSAGE
    RECIPIENTS, MESSAGE = BASE / args.recipients, BASE / args.message
    if not 1 <= args.limit <= 50:
        sys.exit("--limit must be between 1 and 50.")
    if not 10 <= args.min_delay <= args.max_delay:
        sys.exit("Delays must satisfy 10 <= --min-delay <= --max-delay.")

    load_env()
    sender = require("GMAIL_ADDRESS")
    name = require("SENDER_NAME")
    resume = (BASE / require("RESUME_PATH")).resolve()
    if not resume.is_file():
        sys.exit(f"Resume not found: {resume}")
    if resume.stat().st_size > MAX_ATTACHMENT_MB * 1024 * 1024:
        sys.exit(f"Resume is larger than {MAX_ATTACHMENT_MB} MB.")

    subject, body = load_template()
    done = already_handled()
    pending = [r for r in load_recipients() if r["email"] not in done][: args.limit]
    if not pending:
        print("Nothing to send. Everyone in recipients.csv is already in sent_log.csv.")
        return

    print(f"{len(pending)} email(s) to {'SEND' if args.send else 'preview (dry run)'}.\n")
    if not args.send:
        for r in pending:
            m = build_message(sender, name, r, subject, body, resume)
            print(f"To: {m['To']}\nSubject: {m['Subject']}\n")
        print("-" * 60)
        print(build_message(sender, name, pending[0], subject, body, resume)
              .get_body(("plain",)).get_content())
        print("Dry run only. Add --send to send.")
        return

    password = require("GMAIL_APP_PASSWORD")
    server = connect(sender, password)
    sent = 0
    try:
        for i, r in enumerate(pending, start=1):
            msg = build_message(sender, name, r, subject, body, resume)
            try:
                server.noop()
            except (OSError, smtplib.SMTPException):
                server = connect(sender, password)
            try:
                refused = server.send_message(msg)
                if refused:
                    log(r["email"], "failed", str(refused))
                    print(f"[{i}/{len(pending)}] REFUSED {r['email']}")
                else:
                    log(r["email"], "sent")
                    sent += 1
                    print(f"[{i}/{len(pending)}] sent    {r['email']}")
            except smtplib.SMTPRecipientsRefused as e:
                log(r["email"], "failed", str(e.recipients))
                print(f"[{i}/{len(pending)}] REFUSED {r['email']}")
            except (OSError, smtplib.SMTPException) as e:
                # The connection broke mid-send, so Gmail may or may not have sent it.
                # Marked uncertain and not retried; check your Sent folder.
                log(r["email"], "uncertain", str(e))
                print(f"[{i}/{len(pending)}] UNCERTAIN {r['email']} ({e}) - check Gmail Sent folder")
                server = connect(sender, password)
            if i < len(pending):
                time.sleep(random.uniform(args.min_delay, args.max_delay))
    except KeyboardInterrupt:
        print("\nStopped. Progress is saved in sent_log.csv.")
    finally:
        try:
            server.quit()
        except (OSError, smtplib.SMTPException):
            pass
    print(f"\nDone. Sent {sent}. See sent_log.csv for details.")


if __name__ == "__main__":
    main()
