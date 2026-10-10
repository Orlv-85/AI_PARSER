# JSON source intake with automatic review

Extends `.specify/specs/003-source-onboarding-management/spec.md`.

## Problem and outcome

Operators cannot easily find the latest import or approve useful sources. Raw
URL extraction also imports article evidence links from JSON research reports.
An operator should upload JSON, see background verification progress and plain
decisions, then connect recommended sources with one action.

## Requirements

- Accept a `sources` array or a top-level array of URL strings/source objects.
  Import only each record's `url`; preserve its declared type and small metadata.
  Never import `website_url`, evidence, replacements or unverified links.
- Preserve plain text/Markdown import and existing API/CLI behavior.
- Show the latest batch automatically, accept a JSON file and pasted JSON, and
  start the new bounded verification workflow after import.
- Run network/model work in a background worker. Commit each candidate result
  separately. Return immediately and expose progress; serialize verification
  jobs to avoid repeated concurrent work on a small VPS.
- Probe only the source feed/list page, with a response size limit, timeout,
  redirect limit and public-network URL checks. Never crawl the archive or read
  complete articles for a source decision. Confirm RSS/Atom entries or HTML
  publication links. Source declarations are untrusted evidence.
- Reject exact existing URLs in code. Flag same-host families for review, without
  assuming all sections on one host are duplicates.
- Give Jev a bounded brief: observed page/feed title and description plus at most
  five publication titles, URLs and dates, and capped declared metadata.
- Ask Jev whether the evidence shows a recurring publication source, suitable AI
  coverage and sufficient evidence. Use conservative confidence thresholds;
  probabilities are model judgments, not guarantees of source quality.
- Send uncertain technically usable sources to DeepSeek using the same brief.
  DeepSeek returns a decision, bounded reason and confidence in JSON. It may not
  override technical failures, exact duplicates or unresolved source overlap.
- Provider errors, missing keys and inadequate evidence leave manual review,
  never automatic approval. Stop reusing a provider after a provider failure in
  the batch. Bound model requests and DeepSeek output.
- Cache successful AI decisions by normalized URL, observed evidence, models
  and prompt version in existing validation details. Rechecking unchanged
  evidence reuses decisions; repeated imports do not trigger duplicate work.
- Present `ready`, `review`, `reject`, `duplicate` with reasons and progress.
  Sources become enabled only after an explicit bulk or individual approval.
  Bulk approval rechecks persisted readiness and technical validation.
- Keep validation results in existing tables without a schema migration.
  Pending work can be restarted after app restart; do not silently mark it done.
- Use the configured Jev key and `DS_API_KEY`, never expose keys in responses or
  logs. No production authentication or runtime defaults change.

## Validation

- JSON research examples import source URLs only; malformed JSON fails clearly.
- Mock network probes cover RSS, HTML, redirects, oversize, private addresses,
  unavailable pages and pages without publication evidence.
- Mock Jev/DeepSeek calls cover routing, bounds, invalid answers, unavailable
  keys/providers and cached repeat checks.
- Verify health remains available during a slow background probe and progress
  survives completed candidate commits.
- Verify bulk approval skips failed/uncertain/duplicate/already-approved records.
- Run full `make lint PYTHON=./venv1/bin/python` and `./venv1/bin/pytest` before
  commit/push, then CI and production health/version checks.
