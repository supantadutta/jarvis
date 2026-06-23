"""SOC Brain upgrade + benchmark harness."""
from __future__ import annotations

from app.brain.benchmarks import run_all
from app.soc.brain import (
    analyze_false_positive,
    analyze_web_attack,
    brute_force_logic,
    build_yara_rule,
    dns_tunneling_logic,
    incident_summary,
    password_spraying_logic,
    triage_alert,
)


# --- SOC brain ---
def test_triage_high_severity_for_brute_force():
    res = triage_alert({"event_id": 4625, "failed_count": 80, "off_hours": True,
                        "is_internal": False, "description": "many failed logons"})
    assert res["severity"] in ("high", "critical")
    assert res["score"] >= 4
    assert any("Isolate" in a for a in res["recommended_actions"])


def test_triage_log_tampering_flagged():
    res = triage_alert({"event_id": 1102, "description": "audit log cleared"})
    assert res["score"] >= 3


def test_false_positive_known_admin():
    res = analyze_false_positive(signature="suspicious logon",
                                 context={"known_admin": True})
    assert res["likely_false_positive"] is True


def test_yara_rule_skeleton():
    rule = build_yara_rule(name="Evil Macro", strings=["AutoOpen", "Shell"],
                           description="detect macro")
    assert rule.startswith("rule Evil_Macro")
    assert '$s0 = "AutoOpen"' in rule and "condition:" in rule


def test_brute_force_and_spray_logic():
    bf = brute_force_logic(threshold=25)
    assert "EventCode=4625" in bf["spl"] and "count >= 25" in bf["spl"]
    spray = password_spraying_logic(min_users=15)
    assert "dc(user)" in spray["spl"] and "users >= 15" in spray["spl"]
    assert spray["attack"].startswith("T1110")


def test_dns_tunneling_logic():
    dns = dns_tunneling_logic()
    assert "TXT" in " ".join(dns["indicators"]) or "entropy" in " ".join(dns["indicators"])
    assert dns["attack"] == "T1071.004"


def test_web_attack_detection():
    assert analyze_web_attack("GET /?id=1' OR '1'='1")["malicious"] is True
    assert "SQL injection" in str(analyze_web_attack("union select * from users"))
    assert analyze_web_attack("<script>alert(1)</script>")["findings"][0]["type"] == "XSS"
    assert analyze_web_attack("GET /home")["malicious"] is False


def test_incident_summary_builds_timeline_and_mitre():
    events = [
        {"ts": "2026-06-16T09:00", "description": "failed logon brute force"},
        {"ts": "2026-06-16T09:05", "description": "rdp lateral movement"},
    ]
    summ = incident_summary(title="IR-1", events=events, severity="high")
    assert summ["event_count"] == 2
    assert "T1110" in summ["mitre_techniques"] or "T1021" in summ["mitre_techniques"]
    assert summ["timeline"][0].startswith("2026-06-16T09:00")


# --- benchmark harness ---
def test_benchmarks_all_pass():
    report = run_all()
    assert report["passed"] is True
    assert report["overall_score"] >= 0.8
    names = {s["name"] for s in report["suites"]}
    assert {"routing_accuracy", "permission_guard_enforcement",
            "prompt_injection_resistance"} <= names


def test_benchmark_guard_enforcement_perfect():
    report = run_all()
    guard = next(s for s in report["suites"] if s["name"] == "permission_guard_enforcement")
    assert guard["score"] == 1.0  # security enforcement must be perfect
