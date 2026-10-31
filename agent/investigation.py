"""Bounded working memory, not a planner or a trap detector.

The model owns hypotheses, status and next actions. The harness only stores
them, links them to observations already delivered, and enforces size limits.
"""
from __future__ import annotations

import json
import re


STATE_RE = re.compile(r"<state>(.*?)</state>", re.DOTALL | re.IGNORECASE)
STATUSES = {"discovered", "investigating", "waiting", "blocked", "rejected", "verified"}


def action_text(text: str) -> str:
    """State strings must never be interpreted as shell actions."""
    text = STATE_RE.sub("", text)
    return re.sub(r"<state>.*$", "", text, flags=re.DOTALL | re.IGNORECASE)


class InvestigationState:
    def __init__(self):
        self.leads: dict[str, dict] = {}
        self.evidence: dict[int, dict] = {}
        # Provenance lasts for this run even when bounded excerpts expire.
        # Store only IDs, never discarded (or unscreened) observation text.
        self.observed_steps: set[int] = set()
        self.active_lead: str | None = None

    def observe(self, step: int, command: str, observation: str) -> None:
        # observation is the screened model view, never hidden raw stdout.
        self.observed_steps.add(step)
        self.evidence[step] = {
            "step": step, "command": command[:200],
            "excerpt": observation[:600],
        }
        # Keep referenced evidence plus recent observations, with a fixed cap.
        referenced = {s for lead in self.leads.values() for s in lead["evidence_steps"]}
        keep = set(sorted(self.evidence)[-8:]) | referenced
        self.evidence = {s: e for s, e in self.evidence.items() if s in keep}

    def update(self, response: str, decision_step: int) -> str:
        matches = STATE_RE.findall(response)
        if not matches:
            return ""
        if len(matches) != 1 or len(matches[0]) > 4000:
            return "invalid state block"
        try:
            data = json.loads(matches[0])
        except ValueError:
            return "invalid state JSON"
        if not isinstance(data, dict):
            return "state must be an object"
        lead_id = data.get("lead_id")
        if not isinstance(lead_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", lead_id):
            return "invalid lead_id"
        lead = dict(self.leads.get(lead_id, {
            "lead_id": lead_id, "subject": "", "hypothesis": "", "question": "",
            "next_action": "", "status": "discovered", "evidence_steps": [],
        }))
        for key in ("subject", "hypothesis", "question", "next_action"):
            if key in data:
                if not isinstance(data[key], str):
                    return f"invalid {key}"
                lead[key] = data[key][:240]
        if "status" in data:
            if not isinstance(data["status"], str) or data["status"] not in STATUSES:
                return "invalid status"
            lead["status"] = data["status"]
        if "evidence_steps" in data:
            refs = data["evidence_steps"]
            if not isinstance(refs, list) or any(
                    type(s) is not int or s <= 0 for s in refs):
                return "invalid evidence_steps"
            # Validate every submitted ID before applying the storage cap.
            # Expired evidence is legitimate; invented/current/future IDs are not.
            if any(s not in self.observed_steps or s >= decision_step for s in refs):
                return "unknown evidence step"
            lead["evidence_steps"] = [
                s for s in dict.fromkeys(refs) if s in self.evidence
            ][-4:]
        lead["decision_step"] = decision_step
        # Recency controls eviction only. No semantic prioritization by harness.
        self.leads.pop(lead_id, None)
        self.leads[lead_id] = lead
        while len(self.leads) > 12:
            del self.leads[next(iter(self.leads))]
        self.active_lead = lead_id
        return ""

    def snapshot(self) -> dict:
        return {"active_lead": self.active_lead, "leads": list(self.leads.values())}

    def render(self, char_limit: int) -> str:
        header = ("Active investigation memory. This is model-reported belief, "
                  "not verified fact. Keep it brief and use the latest lead only.\n")
        if char_limit < len(header):
            return ""
        lines = [header.rstrip()]
        used = len(header)
        if self.active_lead in self.leads:
            lead = self.leads[self.active_lead]
            compact = {
                "lead_id": lead["lead_id"],
                "subject": lead["subject"][:80],
                "hypothesis": lead["hypothesis"][:100],
                "next_action": lead["next_action"][:120],
                "status": lead["status"],
                "evidence_steps": lead["evidence_steps"][-2:],
            }
            line = json.dumps(compact, ensure_ascii=False)
            if used + len(line) + 1 <= char_limit:
                lines.append(line)
                used += len(line) + 1
                for step in reversed(lead["evidence_steps"][-2:]):
                    evidence = self.evidence.get(step)
                    if not evidence:
                        continue
                    excerpt = json.dumps({
                        "evidence_step": step,
                        "excerpt": evidence["excerpt"][:140],
                    }, ensure_ascii=False)
                    if used + len(excerpt) + 1 <= char_limit:
                        lines.append(excerpt)
                        used += len(excerpt) + 1
        return "\n".join(lines) + "\n"
