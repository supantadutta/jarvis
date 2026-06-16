# SOC / Cybersecurity Modules (Phase 3)

**Defensive, educational, lab-authorized only.** These modules help with
detection engineering and analysis. They contain **no** offensive tooling — no
exploitation, malware, evasion, persistence, credential theft, or stealth. All
helpers are pure data/string construction: nothing is executed and nothing
reaches a network. See `threat_model.md` for the boundary.

## Capabilities (`app/soc/defensive.py`)

| Helper | Purpose |
|--------|---------|
| `explain_event_id(id)` | Explain common security Windows Event IDs (4624/4625/4688/4720/7045/4769…). |
| `map_to_attack(text)` | Map a free-text behavior description to candidate MITRE ATT&CK techniques. |
| `build_splunk_spl(spec)` | Build a defensive Splunk SPL search from a typed `DetectionSpec`. |
| `build_logscale_query(spec)` | Build a CrowdStrike LogScale (Humio) query. |
| `build_sigma_rule(...)` | Build a minimal Sigma detection-rule skeleton. |
| `incident_report_template(...)` | Structured IR report skeleton for analyst drafting. |

## API

```
GET  /api/soc/event/{event_id}     -> explanation
POST /api/soc/attack-map           {"behavior": "..."}            -> techniques
POST /api/soc/splunk               {"index","event_id",          -> {spl, logscale}
                                    "by_fields","threshold"}
```

## Example

```bash
curl -s localhost:8000/api/soc/splunk -H 'content-type: application/json' \
  -d '{"index":"wineventlog","event_id":4625,"by_fields":["src_ip"],"threshold":10}'
# {"spl":"index=wineventlog EventCode=4625 | stats count by src_ip | where count >= 10",
#  "logscale":"EventID=4625 | groupBy([src_ip], function=count(as=count)) | count >= 10"}
```

The **SOC agent** (`app/agents/specialists.py::SOCAgent`) uses these with a
defensive-only system prompt and declines anything offensive, explaining the
defensive alternative instead.
