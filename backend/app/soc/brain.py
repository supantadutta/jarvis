"""SOC Brain upgrade (Cognitive Processing Engine v2) — stronger DEFENSIVE
detection-engineering and triage reasoning.

DEFENSIVE / educational / lab-authorized only. No exploitation, malware, evasion,
or offensive tooling. Pure, deterministic data construction (unit-tested); nothing
is executed and nothing reaches a network. Builds on app/soc/defensive.py.
"""
from __future__ import annotations

import re

from app.soc.defensive import build_splunk_spl, DetectionSpec, map_to_attack

_SEVERITY = ["info", "low", "medium", "high", "critical"]


def triage_alert(alert: dict) -> dict:
    """Score and triage a security alert (defensive). `alert` may include:
    event_id, count, failed_count, src_ip, user, is_internal, off_hours."""
    score = 0
    reasons: list[str] = []

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(reason)

    failed = int(alert.get("failed_count", 0))
    if failed >= 50:
        add(3, f"{failed} failed logons (possible brute force/spray)")
    elif failed >= 10:
        add(2, f"{failed} failed logons")
    if alert.get("event_id") in (1102, 4719):
        add(3, "audit/log tampering indicator")
    if alert.get("event_id") == 4672:
        add(1, "special-privilege logon")
    if alert.get("off_hours"):
        add(1, "activity outside business hours")
    if alert.get("is_internal") is False:
        add(1, "external source")
    if int(alert.get("distinct_users", 0)) >= 10:
        add(2, "many distinct target users (spray pattern)")

    sev = _SEVERITY[min(len(_SEVERITY) - 1, score)]
    behavior = " ".join(str(alert.get(k, "")) for k in ("description", "signature")) \
        + (" failed logon brute" if failed >= 10 else "")
    return {
        "severity": sev, "score": score, "reasons": reasons,
        "attack_mapping": map_to_attack(behavior),
        "recommended_actions": _actions_for(sev),
    }


def _actions_for(severity: str) -> list[str]:
    base = ["Confirm scope in SIEM", "Check source reputation", "Correlate with auth logs"]
    if severity in ("high", "critical"):
        base += ["Isolate affected host (with approval)", "Reset impacted credentials",
                 "Open incident ticket", "Preserve evidence (logs, memory)"]
    return base


def analyze_false_positive(*, signature: str, context: dict) -> dict:
    """Heuristic FP analysis: is this alert likely benign given context?"""
    rationale: list[str] = []
    if context.get("known_admin") and "logon" in signature.lower():
        rationale.append("source is a known admin account")
    if context.get("maintenance_window"):
        rationale.append("occurred during a maintenance window")
    if context.get("allowlisted_ip"):
        rationale.append("source IP is allowlisted")
    likely_fp = bool(rationale)
    return {"likely_false_positive": likely_fp, "rationale": rationale,
            "recommendation": "tune rule / add exception" if likely_fp else "investigate"}


def build_yara_rule(*, name: str, strings: list[str], description: str = "",
                    condition: str = "any of them") -> str:
    """Build a defensive YARA rule skeleton (detection only)."""
    safe = re.sub(r"\W", "_", name) or "rule"
    str_lines = "\n".join(f'        $s{i} = "{s}"' for i, s in enumerate(strings))
    return (
        f"rule {safe} {{\n"
        f"    meta:\n        description = \"{description or name} (defensive, lab)\"\n"
        f"    strings:\n{str_lines}\n"
        f"    condition:\n        {condition}\n}}"
    )


def brute_force_logic(*, index: str = "wineventlog", threshold: int = 20) -> dict:
    spec = DetectionSpec(index=index, event_id=4625, by_fields=["src_ip", "user"],
                         threshold=threshold)
    return {
        "name": "Brute force (failed logons per source)",
        "indicators": [f">={threshold} EventID 4625 from one src_ip in a short window",
                       "few distinct users, many attempts"],
        "spl": build_splunk_spl(spec), "attack": "T1110",
    }


def password_spraying_logic(*, index: str = "wineventlog", min_users: int = 10) -> dict:
    return {
        "name": "Password spraying (few attempts across many users)",
        "indicators": [f"one src_ip targeting >= {min_users} distinct users",
                       "1-2 failed attempts per user (under lockout threshold)"],
        "spl": (f"index={index} EventCode=4625 | stats dc(user) as users count by src_ip "
                f"| where users >= {min_users}"),
        "attack": "T1110.003",
    }


def dns_tunneling_logic(*, index: str = "dns") -> dict:
    return {
        "name": "DNS tunneling (exfil/C2 over DNS)",
        "indicators": ["abnormally long subdomains/labels", "high volume of TXT/NULL queries",
                       "high entropy hostnames", "many unique subdomains for one domain"],
        "spl": (f"index={index} | eval qlen=len(query) "
                "| stats avg(qlen) as avg_len count dc(query) as uniq by domain "
                "| where avg_len > 50 OR uniq > 200"),
        "attack": "T1071.004",
    }


_WEB_ATTACK_PATTERNS = [
    ("SQL injection", re.compile(r"(union\s+select|' or '1'='1|--|;\s*drop\s+table|sleep\()", re.I), "T1190"),
    ("XSS", re.compile(r"(<script|onerror=|javascript:|<img[^>]+onerror)", re.I), "T1059.007"),
    ("Path traversal", re.compile(r"(\.\./|\.\.\\|/etc/passwd|c:\\windows)", re.I), "T1083"),
    ("Command injection", re.compile(r"(;\s*cat\s|`.*`|\$\(|\|\s*nc\s)", re.I), "T1059"),
]


def analyze_web_attack(log_line: str) -> dict:
    """Detect (defensively) classes of web attack patterns in a request/log line."""
    findings = []
    for name, pat, attack in _WEB_ATTACK_PATTERNS:
        if pat.search(log_line or ""):
            findings.append({"type": name, "attack": attack})
    return {
        "findings": findings,
        "malicious": bool(findings),
        "recommendation": "block + WAF rule + investigate source" if findings
        else "no known web-attack pattern detected",
    }


def incident_summary(*, title: str, events: list[dict], severity: str = "medium") -> dict:
    """Assemble an evidence-based incident summary from triaged events."""
    timeline = sorted(events, key=lambda e: e.get("ts", ""))
    techniques = sorted({t["technique_id"] for e in events
                         for t in map_to_attack(e.get("description", ""))})
    return {
        "title": title, "severity": severity, "event_count": len(events),
        "timeline": [f"{e.get('ts', '?')} — {e.get('description', '')}" for e in timeline],
        "mitre_techniques": techniques,
        "sections": ["Summary", "Timeline (UTC)", "Affected assets", "Evidence",
                     "MITRE ATT&CK", "Containment", "Eradication", "Lessons learned"],
    }
