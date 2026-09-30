"""Persistent company/role history for avoiding repeat job applications."""

import csv
import io
import logging
import os
from datetime import date, datetime, timedelta


HISTORY_CSV = "applied_jobs.csv"
HISTORY_FIELDS = ["company", "role", "applied_at", "applied_date", "job_url"]
LEGACY_FIELDS = ["company", "role", "applied_at", "job_url"]


def normalize_job(company, role):
    """Return a case-insensitive key for a company and role pair."""
    return (" ".join(company.split()).casefold(), " ".join(role.split()).casefold())


def load_applied_jobs():
    """Clean expired entries, then load existing company/role pairs."""
    clean_expired_jobs()

    with open(HISTORY_CSV, "r", encoding="utf-8-sig", newline="") as history_file:
        return {
            normalize_job(row.get("company", ""), row.get("role", ""))
            for row in csv.DictReader(history_file)
            if row.get("company", "").strip() and row.get("role", "").strip()
        }


def clean_expired_jobs(retention_days=None):
    """Remove expired history entries and migrate legacy CSV rows while preserving valid records."""
    if retention_days is None:
        retention_days = int(os.getenv("APPLICATION_HISTORY_RETENTION_DAYS", "5"))
    if retention_days < 0:
        raise ValueError("APPLICATION_HISTORY_RETENTION_DAYS cannot be negative")

    if not os.path.exists(HISTORY_CSV):
        contents = ""
    else:
        with open(HISTORY_CSV, "r", encoding="utf-8-sig", newline="") as history_file:
            contents = history_file.read()

    legacy_header = ",".join(LEGACY_FIELDS)
    if contents.startswith(legacy_header) and len(contents) > len(legacy_header):
        if contents[len(legacy_header)] not in "\r\n":
            contents = legacy_header + "\n" + contents[len(legacy_header):]

    rows = list(csv.DictReader(io.StringIO(contents, newline=""))) if contents.strip() else []
    cutoff_date = date.today() - timedelta(days=retention_days)
    retained_rows = []
    removed = 0
    for row in rows:
        stored_date = (row.get("applied_date") or "").strip()
        if not stored_date:
            stored_date = (row.get("applied_at") or "").strip()[:10]
        try:
            applied_date = date.fromisoformat(stored_date)
        except ValueError:
            applied_date = None

        if applied_date is not None and applied_date < cutoff_date:
            removed += 1
            continue

        row["applied_date"] = applied_date.isoformat() if applied_date else stored_date
        retained_rows.append({field: row.get(field, "") for field in HISTORY_FIELDS})

    with open(HISTORY_CSV, "w", encoding="utf-8", newline="") as history_file:
        writer = csv.DictWriter(history_file, fieldnames=HISTORY_FIELDS)
        writer.writeheader()
        writer.writerows(retained_rows)

    if removed:
        logging.getLogger(__name__).info(
            "Removed %s application history entries older than %s days.", removed, retention_days
        )


def record_applied_job(company, role, job_url=""):
    """Append one applied company/role pair to the persistent CSV."""
    clean_expired_jobs()
    with open(HISTORY_CSV, "a", encoding="utf-8", newline="") as history_file:
        writer = csv.DictWriter(history_file, fieldnames=HISTORY_FIELDS)
        writer.writerow({
            "company": company.strip(),
            "role": role.strip(),
            "applied_at": datetime.now().isoformat(timespec="seconds"),
            "applied_date": date.today().isoformat(),
            "job_url": job_url,
        })