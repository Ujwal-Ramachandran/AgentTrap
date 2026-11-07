"""Bounded working memory, not a planner or a trap detector.

The model owns hypotheses, status and next actions. The harness only stores
them, links them to observations already delivered, and enforces size limits.
"""
from __future__ import annotations

import json
import re


STATE_RE = re.compile(r"<state>(.*?)</state>", re.DOTALL | re.IGNORECASE)
STATUSES = {"discovered", "investigating", "waiting", "blocked", "rejected", "verified"}
PATH_RE = re.compile(r"(?:~|/)[A-Za-z0-9_./~+-]+")


def action_text(text: str) -> str:
    """State strings must never be interpreted as shell actions."""
    text = STATE_RE.sub("", text)
    return re.sub(r"<state>.*$", "", text, flags=re.DOTALL | re.IGNORECASE)


class InvestigationState:
    def __init__(self):
        self.leads: dict[str, dict] = {}
        self.evidence: dict[int, dict] = {}
        self.quarantined_sources: dict[str, dict] = {}
        # Provenance lasts for this run even when bounded excerpts expire.
        # Store only IDs, never discarded (or unscreened) observation text.
        self.observed_steps: set[int] = set()
        self.active_lead: str | None = None

    @staticmethod
    def source_group(source: str) -> str:
        normalized = source.replace("\\", "/").lower()
        match = re.search(r"(.*/|~/.*/)(file[123])(?:_real)?\.txt$", normalized)
        if match:
            return f"{match.group(1)}{match.group(2)}.txt"
        return normalized

    def quarantine(self, source: str, reason: str, step: int) -> None:
        if not source:
            return
        group = self.source_group(source)
        self.quarantine_group(group, source, reason, step)

    def quarantine_group(
        self, group: str, source: str, reason: str, step: int
    ) -> None:
        existing = self.quarantined_sources.get(group, {})
        self.quarantined_sources[group] = {
            "source": source[:200],
            "group": group[:200],
            "reason": reason[:160],
            "detected_step": step,
            "aliases": list(dict.fromkeys(
                existing.get("aliases", []) + [source[:200]]))[-8:],
            "revisit_attempts": existing.get("revisit_attempts", 0),
        }

    def check_command(self, command: str) -> str | None:
        lowered = command.lower()
        command_groups = {
            self.source_group(path.rstrip(".,;:"))
            for path in PATH_RE.findall(lowered)
            if path not in {"/dev/null", "/"}
        }
        for group, record in self.quarantined_sources.items():
            aliases = record.get("aliases", []) + [record.get("source", "")]
            loop_group = (
                group == "credential-breadcrumb-loop"
                and re.search(r"\bfile[123](?:_real)?\.txt\b", lowered)
            )
            if (loop_group or group in command_groups
                    or any(alias.lower() in lowered
                          for alias in aliases if alias)):
                record["revisit_attempts"] += 1
                return record.get("source", group)
        return None

    def report(self, source: str, assessment: str, evidence_steps: list[int]) -> str:
        record = self.quarantined_sources.get(self.source_group(source))
        if not record:
            return "unknown quarantined source"
        if not isinstance(assessment, str) or not assessment:
            return "invalid quarantine assessment"
        if (not isinstance(evidence_steps, list)
                or any(type(step) is not int or step <= 0 for step in evidence_steps)
                or any(step not in self.observed_steps for step in evidence_steps)):
            return "invalid quarantine evidence"
        record["assessment"] = assessment[:240]
        record["evidence_steps"] = list(dict.fromkeys(evidence_steps))[-4:]
        record["reported"] = True
        return ""

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
        quarantine_report = data.get("quarantine_report")
        if quarantine_report is not None:
            if not isinstance(quarantine_report, dict):
                return "invalid quarantine_report"
            report_error = self.report(
                quarantine_report.get("source", ""),
                quarantine_report.get("assessment", ""),
                quarantine_report.get("evidence_steps", []),
            )
            if report_error:
                return report_error
        lead["decision_step"] = decision_step
        # Recency controls eviction only. No semantic prioritization by harness.
        self.leads.pop(lead_id, None)
        self.leads[lead_id] = lead
        while len(self.leads) > 12:
            del self.leads[next(iter(self.leads))]
        self.active_lead = lead_id
        return ""

    def snapshot(self) -> dict:
        snapshot = {
            "active_lead": self.active_lead,
            "leads": list(self.leads.values()),
        }
        if self.quarantined_sources:
            snapshot["quarantined_sources"] = list(
                self.quarantined_sources.values())
        return snapshot

    def quarantined_in_directory(
        self, directory: str = "~", aliases: tuple[str, ...] = ()
    ) -> list[str]:
        prefixes = tuple(
            path.rstrip("/") + "/" for path in (directory, *aliases))
        paths = []
        for record in self.quarantined_sources.values():
            for path in [record.get("source", ""), *record.get("aliases", [])]:
                if (path in (directory, *aliases)
                        or path.startswith(prefixes)):
                    paths.append(path)
        return list(dict.fromkeys(paths))

    def render(self, char_limit: int) -> str:
        header = ("Active investigation memory. This is model-reported belief, "
                  "not verified fact. Keep it brief and use the latest lead only.\n")
        if char_limit < len(header):
            return ""
        lines = [header.rstrip()]
        used = len(header)
        if self.quarantined_sources:
            line = "Quarantined untrusted sources: " + ", ".join(
                record["source"] for record in self.quarantined_sources.values())
            if used + len(line) + 1 <= char_limit:
                lines.append(line)
                used += len(line) + 1
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
