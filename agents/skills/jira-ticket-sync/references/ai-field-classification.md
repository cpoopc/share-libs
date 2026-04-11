# AI Field Classification

Use this after `jira-ticket-sync import ... --real` has produced a review-sized candidate set.

## Purpose

The import engine should narrow the field list first. AI should classify only the remaining business-field candidates.

This keeps the workflow:

1. deterministic for obvious noise
2. explainable for borderline fields
3. reviewable by a human before profile updates

## Candidate Input

Prepare one record per candidate field with:

- `issue_key`
- `issue_type`
- `field_id`
- `field_alias`
- `field_display_name`
- `value_preview`
- `value_type`
- `is_common_across_samples`
- `heuristic_classification`
- `heuristic_confidence`

Prefer structured values over screenshots. Use screenshots only to resolve label mismatches or unclear Jira UI placement.

## Required Output

Return strict JSON objects in this shape:

```json
{
  "field": "exist_on_production",
  "classification": "type_specific_business",
  "confidence": 0.91,
  "reason": "Operational impact field used to distinguish production-facing bugs.",
  "suggested_for": ["Bug"],
  "action": "review"
}
```

## Allowed Values

`classification` must be one of:

- `core_business`
- `type_specific_business`
- `optional_business`
- `system_noise`
- `ui_noise`
- `uncertain`

`action` must be one of:

- `keep`
- `review`
- `drop`

## Review Rules

Escalate to human review when:

- `confidence < 0.85`
- `classification == "uncertain"`
- the field conflicts with an already confirmed classification

Do not write AI-only decisions straight into a profile.

## Persistence Rules

Write confirmed decisions to a project-local cache first, for example:

`state/field-classification/<PROJECT>.json`

Promote fields into profile aliases only after repeated confirmation that:

- the field is business-relevant
- the field meaning is stable
- the field should be synchronized across future manifests
