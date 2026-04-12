# IVA Logtracer Component Explainability Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first production slice of component-aware tracing: a canonical component catalog, explainable component resolution output, `doctor --components`, `trace --explain-components`, and saved component coverage artifacts.

**Architecture:** Keep the existing orchestrator and loader pipeline, but introduce a runtime-owned component catalog and correlation graph as the single source of truth. Thread component resolution and explain output through the existing CLI and session tracer with strict fallback behavior so resolver failures never break classic trace.

**Tech Stack:** Python, argparse, existing `cptools_kibana` client, pytest

---

## Chunk 1: Plan And Test Surface

### Task 1: Add CLI-facing failing tests

**Files:**
- Modify: `packages/iva-logtracer/tests/test_discover_command.py`
- Create: `packages/iva-logtracer/tests/test_component_explainability.py`

- [ ] **Step 1: Write failing parser and dispatch tests for `doctor --components` and `trace --explain-components`**
- [ ] **Step 2: Run the targeted pytest selection and verify the new assertions fail for the expected reason**
- [ ] **Step 3: Commit no code yet; keep the repo red until runtime support exists**

### Task 2: Add runtime contract tests

**Files:**
- Create: `packages/iva-logtracer/tests/test_component_catalog.py`
- Modify: `packages/iva-logtracer/tests/test_session_orchestrator_prefetch.py`

- [ ] **Step 1: Write failing tests for catalog consistency, component alias resolution, and explain-output fallback semantics**
- [ ] **Step 2: Write a failing orchestrator/session-tracer test for `component_coverage.json` emission and `unknown/not_probed` behavior**
- [ ] **Step 3: Run the targeted pytest selection and verify the failures are caused by missing runtime features, not bad test setup**

## Chunk 2: Runtime Metadata

### Task 3: Introduce canonical component metadata

**Files:**
- Create: `packages/iva-logtracer/logtracer_extractors/iva/component_catalog.py`
- Create: `packages/iva-logtracer/logtracer_extractors/iva/correlation_graph.py`
- Modify: `packages/iva-logtracer/logtracer_extractors/iva/loaders/__init__.py`
- Modify: `packages/iva-logtracer/logtracer_extractors/__init__.py`

- [ ] **Step 1: Define typed component metadata for the current IVA/Nova components**
- [ ] **Step 2: Define initial correlation edges for assistant runtime, agent service, NCA, AIG, GMG, and CPRC**
- [ ] **Step 3: Expose catalog helpers for lookup by canonical name or alias**
- [ ] **Step 4: Run the new catalog tests and make them pass**

### Task 4: Extend field and coverage context

**Files:**
- Modify: `packages/iva-logtracer/logtracer_extractors/iva/trace_context.py`

- [ ] **Step 1: Add typed derived-field storage, resolved index state, component coverage, and correlation path containers**
- [ ] **Step 2: Preserve compatibility for existing `session_id`, `conversation_id`, `srs_session_id`, and `sgs_session_id` fields**
- [ ] **Step 3: Update `to_result()` serialization to include new explainable metadata without breaking current consumers**
- [ ] **Step 4: Run trace-context-related tests and keep them green**

## Chunk 3: Explainability Execution

### Task 5: Add resolver and doctor support

**Files:**
- Create: `packages/iva-logtracer/logtracer_extractors/iva/index_resolver.py`
- Modify: `tools/python/libs/kibana/cptools_kibana/client.py`
- Modify: `packages/iva-logtracer/logtracer_extractors/runtime.py`
- Modify: `packages/iva-logtracer/logtracer_extractors/cli.py`

- [ ] **Step 1: Add a client helper for application-oriented index resolution**
- [ ] **Step 2: Implement resolver logic with cacheable statuses like `matched`, `empty`, `unreachable`, `auth_error`, and `not_probed`**
- [ ] **Step 3: Extend `doctor` to expose `--components` in both text and json formats**
- [ ] **Step 4: Run doctor-focused tests and make them pass**

### Task 6: Add trace explain output and saved coverage artifact

**Files:**
- Modify: `packages/iva-logtracer/logtracer_extractors/iva/orchestrator.py`
- Modify: `packages/iva-logtracer/logtracer_extractors/iva/session_tracer.py`
- Modify: `packages/iva-logtracer/logtracer_extractors/loaders/base.py`

- [ ] **Step 1: Thread explainability state through the orchestrator without breaking classic trace**
- [ ] **Step 2: Add fallback behavior so resolver failures only degrade explain output, never the trace itself**
- [ ] **Step 3: Add `--explain-components` to session tracing and persist `component_coverage.json` when saving output**
- [ ] **Step 4: Run the explainability and session-tracer tests and make them pass**

## Chunk 4: Verification

### Task 7: Run focused verification

**Files:**
- Test: `packages/iva-logtracer/tests/test_discover_command.py`
- Test: `packages/iva-logtracer/tests/test_component_catalog.py`
- Test: `packages/iva-logtracer/tests/test_component_explainability.py`
- Test: `packages/iva-logtracer/tests/test_session_orchestrator_prefetch.py`

- [ ] **Step 1: Run the full targeted pytest command for all touched tests**
- [ ] **Step 2: Fix any regressions until the targeted suite is green**
- [ ] **Step 3: Run a final verification command and record the exact passing output before claiming completion**

