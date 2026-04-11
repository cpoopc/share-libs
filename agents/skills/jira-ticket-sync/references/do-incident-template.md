# DO Incident Template for IVA

Use this template when creating a DevOps/SRE ticket in Jira project `DO` for IVA environment issues.

## Defaults

- Project: `DO`
- Issue type: `Incident`
- Due date: next business day unless the requester specifies another date
- Component: mention in the description body because `components` cannot be set on the DO create screen
- Sync profile: `<bootstrapped-root>/profiles/DO.yaml`
- Sync template: `<bootstrapped-root>/templates/imported/DO.incident.template.yaml`

## Required Fields Confirmed from DO Create Flow

- `customfield_18562` Environment type: option field
  Example for non-prod IVA environments: `{"value":"Other LAB"}`
- `customfield_18552` Environment name: plain string
  Example: `"iva stage"`
- `customfield_20264` Urgency: option field
  Suggested default: `{"value":"Medium"}`
- `customfield_20258` Impact: option field
  Suggested default: `{"value":"M (Medium) "}`
- `duedate`: ISO date string
  Example: `"2026-03-19"`

## Summary Template

`<service> fails to start in <environment> due to <primary error>`

Example:

`assistant-runtime fails to start in iva stage due to Kafka connection closed error`

## Description Template

```jira
h3. *Technical Request: Investigate <service> issue in <environment>*

*1) Objective:*
Investigate and resolve <short problem statement>. Include the impacted service and environment.

*2) Business Value/Urgency:*
*Urgency: Medium.* Explain what testing, validation, or release activity is blocked.

*3) Resources Needed:*
 * Ask DevOps/SRE to investigate the dependent infrastructure path.
 * Ask for config, network, credential, broker, queue, or deployment verification as appropriate.
 * Ask for remediation support if infra-side recovery or reconfiguration is needed.

*4) Observed Error:*
{code}
<paste stack trace or error log>
{code}

*5) Expected Result:*
State the healthy end state in one sentence.

*6) Reference:*
 * Similar DO ticket: [<DO-KEY>|https://jira.ringcentral.com/browse/<DO-KEY>]
 * Component: {{<service>}}
 * Environment: {{<environment>}}
```

## Example Create Payload

```json
{
  "project_key": "DO",
  "issue_type": "Incident",
  "summary": "assistant-runtime fails to start in iva stage due to Kafka connection closed error",
  "description": "<rendered jira wiki text>",
  "additional_fields": {
    "customfield_18562": { "value": "Other LAB" },
    "customfield_18552": "iva stage",
    "customfield_20264": { "value": "Medium" },
    "customfield_20258": { "value": "M (Medium) " },
    "duedate": "2026-03-19"
  }
}
```

## Notes

- For IVA stage or lab environments, start with environment type `Other LAB` unless Jira rejects it.
- Keep `summary` and `description` in polished English even when the request is given in Chinese.
- If the user provides a concrete urgency or impact, use that instead of the defaults above.
