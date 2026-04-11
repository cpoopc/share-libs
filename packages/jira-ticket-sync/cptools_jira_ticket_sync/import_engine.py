from __future__ import annotations

from collections import defaultdict
from typing import Any


NOISE_NAME_TOKENS = (
    "infobox",
    "notice",
    "notification",
    "hint",
    "deprecated",
)
SYSTEM_FIELD_NAMES = {
    "development",
    "rank",
    "epic_colour",
    "epic_color",
}
TYPE_SPECIFIC_KEYWORDS = {
    "Bug": ("reproduce", "problem", "workaround", "customer", "severity", "production"),
    "Epic": ("epic", "target_", "parent_link", "roadmap", "initiative"),
    "Task": ("epic", "start_date", "resolved", "resolution", "severity"),
    "User Story": ("epic", "start_date", "story", "acceptance", "severity"),
    "Story": ("epic", "start_date", "story", "acceptance", "severity"),
}


def extract_aliases_from_field_schema(field_schema: list[dict[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for field in field_schema:
        if not field.get("custom"):
            continue
        name = str(field.get("name", "")).strip().lower().replace(" ", "_")
        if not name:
            continue
        aliases[name] = field["id"]
    return aliases


def build_import_template(
    issues: list[dict[str, Any]],
    field_schema: dict[str, str],
    *,
    confirmed_classifications: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    decisions = confirmed_classifications or {}
    if not issues:
        return {
            "common_fields": {},
            "issue_type_fields": {},
            "confirmed_fields": [],
            "candidate_fields": [],
            "review_queue": [],
            "ignored_fields": [],
        }

    common_fields = _extract_common_fields(issues, field_schema, decisions)
    normalized_fields = {
        issue.get("source", f"issue-{index}"): _normalize_fields(issue.get("fields", {}), field_schema)
        for index, issue in enumerate(issues)
    }

    candidate_fields: list[dict[str, Any]] = []
    confirmed_fields: list[dict[str, Any]] = []
    ignored_fields: list[dict[str, Any]] = []
    issue_type_fields: dict[str, list[str]] = {}

    fields_by_type: dict[str, set[str]] = defaultdict(set)
    for issue in issues:
        source = issue.get("source", "")
        issue_type = issue.get("issue_type", "Unknown")
        for field_name, value in normalized_fields.get(source, {}).items():
            decision = decisions.get(field_name)
            if decision:
                action = str(decision.get("action", "review"))
                classification = str(decision.get("classification", "uncertain"))
                confidence = float(decision.get("confidence", 0.0))
                suggested_for = decision.get("suggested_for", [])
                reason = str(decision.get("reason", ""))
                if action == "drop":
                    ignored_fields.append({"field": field_name, "issue_type": issue_type, "reason": "confirmed_drop"})
                    continue
                fields_by_type[issue_type].add(field_name)
                confirmed_fields.append(
                    {
                        "field": field_name,
                        "issue_type": issue_type,
                        "classification": classification,
                        "confidence": confidence,
                        "action": action,
                        "suggested_for": suggested_for if isinstance(suggested_for, list) else [],
                        "reason": reason,
                    }
                )
                continue

            ignored_reason = _ignored_reason(field_name, value)
            if ignored_reason is not None:
                ignored_fields.append({"field": field_name, "issue_type": issue_type, "reason": ignored_reason})
                continue

            classification = _classify_field(field_name, issue_type)
            confidence = _classification_confidence(field_name, classification)
            fields_by_type[issue_type].add(field_name)
            candidate_fields.append(
                {
                    "field": field_name,
                    "issue_type": issue_type,
                    "classification": classification,
                    "confidence": confidence,
                    "action": "keep" if classification == "core_business" else "review",
                }
            )

    common_field_names = set(common_fields.get("fields", {}).keys())
    for issue_type, field_names in sorted(fields_by_type.items()):
        issue_type_fields[issue_type] = sorted(field_names)

    deduped_candidates = _dedupe_candidate_fields(candidate_fields, common_field_names)
    deduped_confirmed = _dedupe_confirmed_fields(confirmed_fields, common_field_names)
    review_queue = _build_review_queue(deduped_candidates)
    deduped_ignored = _dedupe_ignored_fields(ignored_fields)

    return {
        "common_fields": common_fields,
        "issue_type_fields": issue_type_fields,
        "confirmed_fields": deduped_confirmed,
        "candidate_fields": deduped_candidates,
        "review_queue": review_queue,
        "ignored_fields": deduped_ignored,
    }


def _extract_common_fields(
    issues: list[dict[str, Any]],
    field_schema: dict[str, str],
    decisions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    common_fields: dict[str, Any] = {}
    keys = set.intersection(*(set(issue.keys()) for issue in issues))
    for key in sorted(keys):
        if key == "fields":
            continue
        first_value = issues[0][key]
        if all(issue.get(key) == first_value for issue in issues[1:]):
            common_fields[key] = first_value

    normalized_fields = [_normalize_fields(issue.get("fields", {}), field_schema) for issue in issues]
    field_keys = set.intersection(*(set(fields.keys()) for fields in normalized_fields)) if normalized_fields else set()
    shared_fields: dict[str, Any] = {}
    for key in sorted(field_keys):
        first_value = normalized_fields[0][key]
        decision = decisions.get(key)
        if decision and str(decision.get("action", "review")) == "drop":
            continue
        if any(_ignored_reason(key, fields.get(key)) is not None for fields in normalized_fields):
            continue
        if all(fields.get(key) == first_value for fields in normalized_fields[1:]):
            shared_fields[key] = first_value
    if shared_fields:
        common_fields["fields"] = shared_fields
    return common_fields


def _normalize_fields(raw_fields: dict[str, Any], field_schema: dict[str, str]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in raw_fields.items():
        normalized[field_schema.get(key, key)] = value
    return normalized


def _ignored_reason(field_name: str, value: Any) -> str | None:
    lowered = field_name.lower()
    if any(token in lowered for token in NOISE_NAME_TOKENS):
        return "name_noise"
    if lowered in SYSTEM_FIELD_NAMES:
        return "system_field"
    if _is_html_like(value):
        return "html_value"
    return None


def _is_html_like(value: Any) -> bool:
    return isinstance(value, str) and ("<div" in value or "<a " in value or "</" in value)


def _classify_field(field_name: str, issue_type: str) -> str:
    lowered = field_name.lower()
    if lowered in {"summary", "description", "priority", "labels", "assignee", "epic_link", "epic_key"}:
        return "core_business"

    keywords = TYPE_SPECIFIC_KEYWORDS.get(issue_type, ())
    if any(keyword in lowered for keyword in keywords):
        return "type_specific_business"
    return "optional_business"


def _classification_confidence(field_name: str, classification: str) -> float:
    if classification == "core_business":
        return 0.98
    if classification == "type_specific_business":
        return 0.8 if "_" in field_name else 0.72
    return 0.55


def _dedupe_candidate_fields(
    candidate_fields: list[dict[str, Any]],
    common_field_names: set[str],
) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in candidate_fields:
        if candidate["field"] in common_field_names:
            continue
        key = (candidate["issue_type"], candidate["field"])
        existing = deduped.get(key)
        if existing is None or candidate["confidence"] > existing["confidence"]:
            deduped[key] = candidate
    return sorted(deduped.values(), key=lambda item: (item["issue_type"], item["field"]))


def _dedupe_confirmed_fields(
    confirmed_fields: list[dict[str, Any]],
    common_field_names: set[str],
) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in confirmed_fields:
        if item["field"] in common_field_names:
            continue
        key = (item["issue_type"], item["field"])
        deduped.setdefault(key, item)
    return sorted(deduped.values(), key=lambda item: (item["issue_type"], item["field"]))


def _dedupe_ignored_fields(ignored_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in ignored_fields:
        key = (item["field"], item["reason"])
        deduped.setdefault(key, item)
    return sorted(deduped.values(), key=lambda item: (item["field"], item["reason"]))


def _build_review_queue(candidate_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for item in candidate_fields:
        if item.get("action") != "review":
            continue
        queue.append(
            {
                "field": item["field"],
                "issue_type": item["issue_type"],
                "classification": item["classification"],
                "confidence": item["confidence"],
                "reason": "needs_human_confirmation",
            }
        )
    return sorted(queue, key=lambda entry: (entry["issue_type"], entry["field"]))
