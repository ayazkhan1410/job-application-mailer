# Job Application Mailer

Sends your resume to each address in `recipients.csv`, one email at a time, with a personalized subject and greeting.

## Setup

1. Copy the example files and add your resume:
   ```bash
   cp .env.example .env
   cp recipients.example.csv recipients.csv
   cp message.example.txt message.txt
   ```
2. Put your resume PDF in this folder and set `RESUME_PATH` in `.env`.
3. Turn on 2-Step Verification in your Google account, then create an **App Password**
   (Google Account > Security > App passwords) and put it in `.env`.

No extra packages are needed (Python 3.9+). Personal files (`.env`, resume, `recipients.csv`, `message.txt`, `sent_log.csv`) are gitignored.

## Run

```bash
python send_applications.py              # dry run: preview, sends nothing
python send_applications.py --send       # send for real
python send_applications.py --send --limit 5
```

- Waits 60–120 seconds between emails to avoid Gmail spam limits.
- Every result is saved in `sent_log.csv`. Anyone marked `sent` or `uncertain` is never emailed again, so you can stop and rerun safely.
- `uncertain` means the connection dropped mid-send. Check your Gmail Sent folder before resending manually.
- To add companies, add rows to `recipients.csv` (`email,company`).
- Edit `message.txt` to change the email. `{company}` and `{name}` are filled in automatically.

## Other lists

Use `--recipients` and `--message` to send a different list, for example the worldwide remote list:

```bash
python send_applications.py --recipients recipients_global.csv --message message_global.txt
python send_applications.py --recipients recipients_global.csv --message message_global.txt --send
```

The CSV can also have `role` and `subject` columns. `{role}` is filled into the message, and a non-empty `subject` replaces the template subject for that one email.
