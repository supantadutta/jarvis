"""Defensive SOC / cybersecurity helpers (Phase 3).

DEFENSIVE, educational, lab-authorized output only — detection engineering and
analysis. No exploitation, malware, evasion, persistence, or offensive tooling.
Everything here is pure string/data construction (deterministic, unit-tested);
no commands are executed and nothing reaches a network.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --- Windows Event ID reference (common security-relevant events) ---
WINDOWS_EVENT_IDS: dict[int, dict] = {
    4624: {"name": "Successful logon", "category": "Logon",
           "notes": "Check LogonType (2=interactive, 3=network, 10=RDP)."},
    4625: {"name": "Failed logon", "category": "Logon",
           "notes": "Bursts may indicate password spraying/brute force."},
    4634: {"name": "Logoff", "category": "Logon", "notes": "Session ended."},
    4648: {"name": "Logon with explicit credentials", "category": "Logon",
           "notes": "Possible lateral movement / runas."},
    4672: {"name": "Special privileges assigned to new logon", "category": "Privilege",
           "notes": "Admin-equivalent logon; baseline expected accounts."},
    4688: {"name": "A new process has been created", "category": "Process",
           "notes": "Enable command-line auditing for full visibility."},
    4720: {"name": "User account created", "category": "Account Management",
           "notes": "Unexpected creation may indicate persistence."},
    4724: {"name": "Password reset attempt", "category": "Account Management",
           "notes": "Correlate with the actor account."},
    4732: {"name": "Member added to a security-enabled local group", "category": "Account Management",
           "notes": "Watch additions to Administrators."},
    4768: {"name": "Kerberos TGT requested", "category": "Kerberos",
           "notes": "AS-REQ; baseline normal volume."},
    4769: {"name": "Kerberos service ticket requested", "category": "Kerberos",
           "notes": "Anomalous encryption types can indicate Kerberoasting."},
    7045: {"name": "A new service was installed", "category": "Service",
           "notes": "New services are a common persistence mechanism."},
    4740: {"name": "User account locked out", "category": "Account Management",
           "notes": "Correlate with 4625 bursts (brute force / spray)."},
    4698: {"name": "Scheduled task created", "category": "Persistence",
           "notes": "Scheduled tasks are a common persistence mechanism."},
    1102: {"name": "The audit log was cleared", "category": "Log Management",
           "notes": "Anti-forensics indicator; alert on any occurrence."},
}


def explain_event_id(event_id: int) -> dict:
    info = WINDOWS_EVENT_IDS.get(event_id)
    if not info:
        return {"event_id": event_id, "known": False,
                "message": "Not in the built-in reference; consult Microsoft docs."}
    return {"event_id": event_id, "known": True, **info}


# --- MITRE ATT&CK mapping (small built-in lookup) ---
ATTACK_TECHNIQUES: dict[str, dict] = {
    "T1110": {"name": "Brute Force", "tactic": "Credential Access",
              "detections": ["Spike in 4625 failed logons", "Lockout events 4740"]},
    "T1059": {"name": "Command and Scripting Interpreter", "tactic": "Execution",
              "detections": ["4688 with powershell/cmd", "Script-block logging 4104"]},
    "T1078": {"name": "Valid Accounts", "tactic": "Defense Evasion / Persistence",
              "detections": ["Off-hours 4624", "Impossible travel in sign-in logs"]},
    "T1543": {"name": "Create or Modify System Process", "tactic": "Persistence",
              "detections": ["7045 new service", "Registry run-key changes"]},
    "T1021": {"name": "Remote Services", "tactic": "Lateral Movement",
              "detections": ["4624 LogonType 10 (RDP)", "4648 explicit creds"]},
    "T1003": {"name": "OS Credential Dumping", "tactic": "Credential Access",
              "detections": ["LSASS access", "4769 anomalous (Kerberoasting)"]},
    "T1053": {"name": "Scheduled Task/Job", "tactic": "Persistence / Execution",
              "detections": ["4698 task created", "schtasks in 4688 command line"]},
    "T1070": {"name": "Indicator Removal", "tactic": "Defense Evasion",
              "detections": ["1102 audit log cleared", "wevtutil/Clear-EventLog usage"]},
}

# Keyword → technique hints, for mapping a free-text behavior description.
_BEHAVIOR_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("brute", "spray", "failed logon", "password guess"), "T1110"),
    (("powershell", "cmd", "script", "encoded command"), "T1059"),
    (("rdp", "lateral", "remote desktop", "psexec"), "T1021"),
    (("new service", "service install", "persistence"), "T1543"),
    (("lsass", "mimikatz", "credential dump", "kerberoast"), "T1003"),
    (("scheduled task", "schtasks", "cron job"), "T1053"),
    (("cleared the log", "audit log cleared", "wevtutil", "clear-eventlog"), "T1070"),
    (("off-hours", "valid account", "stolen credential", "impossible travel"), "T1078"),
]


def map_to_attack(behavior: str) -> list[dict]:
    """Map a free-text behavior description to candidate ATT&CK techniques."""
    low = behavior.lower()
    out: list[dict] = []
    seen: set[str] = set()
    for cues, tid in _BEHAVIOR_HINTS:
        if any(c in low for c in cues) and tid not in seen:
            seen.add(tid)
            out.append({"technique_id": tid, **ATTACK_TECHNIQUES[tid]})
    return out


# --- detection query builders (defensive) ---
@dataclass
class DetectionSpec:
    index: str = "*"
    event_id: int | None = None
    field_filters: dict = field(default_factory=dict)
    threshold: int | None = None
    by_fields: list[str] = field(default_factory=list)
    timespan: str = "1h"


def build_splunk_spl(spec: DetectionSpec) -> str:
    """Build a defensive Splunk SPL search from a typed spec."""
    parts = [f"index={spec.index}"]
    if spec.event_id is not None:
        parts.append(f"EventCode={spec.event_id}")
    for k, v in spec.field_filters.items():
        parts.append(f'{k}="{v}"')
    spl = " ".join(parts)
    if spec.by_fields:
        by = ", ".join(spec.by_fields)
        spl += f" | stats count by {by}"
        if spec.threshold is not None:
            spl += f" | where count >= {spec.threshold}"
    return spl


def build_logscale_query(spec: DetectionSpec) -> str:
    """Build a CrowdStrike LogScale (Humio) query from a typed spec."""
    parts = []
    if spec.event_id is not None:
        parts.append(f"EventID={spec.event_id}")
    for k, v in spec.field_filters.items():
        parts.append(f'{k}="{v}"')
    query = " AND ".join(parts) if parts else "*"
    if spec.by_fields:
        groupby = ", ".join(spec.by_fields)
        query += f" | groupBy([{groupby}], function=count(as=count))"
        if spec.threshold is not None:
            query += f" | count >= {spec.threshold}"
    return query


def build_sigma_rule(*, title: str, event_id: int, product: str = "windows",
                     service: str = "security", level: str = "medium") -> dict:
    """Build a minimal Sigma detection rule skeleton (defensive)."""
    return {
        "title": title,
        "status": "experimental",
        "description": f"Defensive detection for {title} (lab-authorized).",
        "logsource": {"product": product, "service": service},
        "detection": {
            "selection": {"EventID": event_id},
            "condition": "selection",
        },
        "level": level,
        "tags": [],
    }


def incident_report_template(*, title: str, severity: str = "medium") -> dict:
    """Structured incident-report skeleton for analyst drafting."""
    return {
        "title": title,
        "severity": severity,
        "sections": [
            "Summary", "Timeline (UTC)", "Affected assets / accounts",
            "Indicators of Compromise (observed, lab)", "MITRE ATT&CK mapping",
            "Containment actions", "Eradication & recovery",
            "Root cause", "Lessons learned / detections to add",
        ],
    }


def build_suricata_rule(*, msg: str, dest_port: int | None = None,
                        content: str | None = None, sid: int = 1000001,
                        proto: str = "tcp") -> str:
    """Build a defensive Suricata IDS rule (alert-only)."""
    options = [f'msg:"{msg}"']
    if content:
        options.append(f'content:"{content}"')
    options.append("classtype:policy-violation")
    options.append(f"sid:{sid}")
    options.append("rev:1")
    port = dest_port if dest_port is not None else "any"
    opts = "; ".join(options)
    return f"alert {proto} any any -> any {port} ({opts};)"


def build_wazuh_rule(*, rule_id: int, level: int, description: str,
                     if_sid: int | None = None, field_match: dict | None = None) -> str:
    """Build a Wazuh local rule XML snippet (detection only)."""
    lines = [f'<rule id="{rule_id}" level="{level}">']
    if if_sid is not None:
        lines.append(f"  <if_sid>{if_sid}</if_sid>")
    for k, v in (field_match or {}).items():
        lines.append(f'  <field name="{k}">{v}</field>')
    lines.append(f"  <description>{description}</description>")
    lines.append("</rule>")
    return "\n".join(lines)
