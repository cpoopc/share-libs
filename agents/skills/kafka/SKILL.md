---
name: kafka
description: Use when a task needs IVA Kafka topic inspection, Redpanda Console access, or environment bootstrap resolution for stage, cnlab01, or cnlab03, especially when internal versus external bootstrap endpoints, topic families, or environment aliases are easy to mix up.
---

# Kafka

Use the repository-backed IVA Kafka environment map instead of guessing bootstrap hosts, console URLs, or topic ownership.

## References

- Read `references/environment-profiles.yaml` to resolve the canonical environment, aliases, console URL, bootstrap endpoints, and default topic or consumer-group mappings.
- Run `scripts/resolve_profile.py` when you need a deterministic resolved view instead of reading the YAML by hand.
- Treat `scripts/resolve_profile.py` as skill-relative. Do not hardcode a global install path.

## Workflow

1. Confirm the task is actually a Kafka task.
   - Use this skill for topic inspection, console access, bootstrap lookup, or IVA message-versus-event routing.
   - Route session tracing or saved trace analysis to `iva-logtracer`.
2. Resolve the requested environment alias through `references/environment-profiles.yaml`.
   - Treat that file as the single source of truth for `stage`, `cnlab01`, and `cnlab03`.
   - Prefer `python3 scripts/resolve_profile.py <profile-or-alias>` when you need a copyable resolved result.
3. Choose the right access path for the current execution context.
   - Use `console_url` when the task only needs browsing or message inspection in Redpanda Console.
   - Use `in_cluster_bootstrap` only when the command will run inside the IVA cluster or pod network.
   - Use `external_bootstrap` only after checking the profile notes and current network reachability.
4. Pick the right topic family before drawing conclusions.
   - Use `iva.messages` for persisted caller or assistant conversation messages.
   - Use `iva.conversations` for conversation-level records.
   - Use `iva.events` or regional `*.iva.events` topics for memory-event style flows, not for the primary persisted message stream.
   - Use `iva.assistant.events` for assistant change events.
5. When investigating missing messages, distinguish the two common paths.
   - `kafka-reader` consumes `iva.messages` with group `iva-kafka-reader` for message persistence.
   - `memory-controller` event consumption is separate and uses `iva.events` plus any environment-specific consumer topics.
6. Validate the resolved environment and endpoint before reporting anything as a Kafka outage or persistence failure.

## Quick Reference

- Canonical environments: `stage`, `cnlab01`, `cnlab03`
- Alias and endpoint truth: `references/environment-profiles.yaml`
- Resolved profile command: `python3 scripts/resolve_profile.py <profile>`
- Primary persisted message topic: `iva.messages`
- Primary persisted message consumer group: `iva-kafka-reader`

## Constraints

- Do not guess environment aliases, bootstrap hosts, or console URLs outside `references/environment-profiles.yaml`.
- Do not treat `iva.events` as the primary persisted conversation message stream when the task is about caller or assistant messages.
- Do not claim an external bootstrap endpoint is unreachable without checking it from the current network context.
- Do not duplicate profile mappings in ad hoc notes when the YAML can be cited directly.
- Do not conflate Redpanda Console connectivity with raw Kafka broker connectivity; they are separate access paths.

## Commands

List the supported canonical profiles and aliases:

```bash
python3 scripts/resolve_profile.py --list
```

Resolve a profile or alias to a concrete environment record:

```bash
python3 scripts/resolve_profile.py stage
python3 scripts/resolve_profile.py cnlab01 --format yaml
python3 scripts/resolve_profile.py iva-cn-lab03
```

## Validation

- Confirm the requested alias resolves to exactly one canonical profile.
- Confirm the reported endpoint type matches the execution context: console, in-cluster bootstrap, or external bootstrap.
- Confirm any topic or consumer-group claim is backed by the resolved profile data.
- Call out profile notes such as region-specific event consumers or local-network-only bootstrap access when they affect the result.
