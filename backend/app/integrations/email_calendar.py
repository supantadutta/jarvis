"""Email drafting + ICS calendar generation (Phase 3).

Drafting and ICS building are pure (unit-tested). Actually *sending* email is a
HIGH_RISK action and must go through the approval queue — these helpers never
send; they produce content for the human to approve.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EmailDraft:
    to: list[str]
    subject: str
    body: str
    cc: list[str] = field(default_factory=list)

    def public(self) -> dict:
        return {"to": self.to, "cc": self.cc, "subject": self.subject, "body": self.body}


def compose_email_draft(*, to: list[str], subject: str, body: str,
                        cc: list[str] | None = None, signature: str | None = None) -> EmailDraft:
    full = body if not signature else f"{body}\n\n-- \n{signature}"
    return EmailDraft(to=to, subject=subject, body=full, cc=cc or [])


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def build_ics_event(*, summary: str, start: datetime, end: datetime,
                    description: str = "", location: str = "", uid: str | None = None) -> str:
    """Build an RFC 5545 VEVENT calendar entry (UTC)."""
    def fmt(dt: datetime) -> str:
        return dt.strftime("%Y%m%dT%H%M%SZ")

    uid = uid or f"{fmt(start)}-{abs(hash(summary)) % 10**8}@jarvis.local"
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//JARVIS//EN", "BEGIN:VEVENT",
        f"UID:{uid}", f"DTSTAMP:{fmt(datetime.utcnow())}",
        f"DTSTART:{fmt(start)}", f"DTEND:{fmt(end)}",
        f"SUMMARY:{_ics_escape(summary)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_ics_escape(description)}")
    if location:
        lines.append(f"LOCATION:{_ics_escape(location)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines)
