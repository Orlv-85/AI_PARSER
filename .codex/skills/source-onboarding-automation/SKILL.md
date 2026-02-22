---
name: source-onboarding-automation
description: Use when adding or tuning many entries in sources.yaml (RSS/HTML blogs). Provides a fast workflow and helper script to lint selector quality, probe candidate CSS selectors, and run a short executor/reviewer validation loop.
---

# Source Onboarding Automation

Use this skill when:
- adding a batch of new sources to `sources.yaml`
- converting `html` sources from generic config to explicit `html.link_selector`
- cleaning noisy selectors / disabled-source hygiene
- validating a curated block (AI agents / IDE / MLOps) quickly

## Goal

Replace long manual onboarding loops with:
1. Add/edit sources.
2. Run static lint on a section.
3. Probe selectors for a few problematic HTML sources.
4. Generate patch-ready `html:` suggestions.
5. Run one fetch smoke test.
6. Check section results in DB quickly.
7. Optional nested reviewer for config-only audit.

## Helper Script

Use:
- `scripts/sources_onboarding_helper.py`

Examples:

```bash
python3 scripts/sources_onboarding_helper.py lint
python3 scripts/sources_onboarding_helper.py lint --section "User-curated: AI agents"
python3 scripts/sources_onboarding_helper.py probe --ids llamaindex_blog,dify_blog,e2b_blog
python3 scripts/sources_onboarding_helper.py probe --section "User-curated: AI-native coding"
python3 scripts/sources_onboarding_helper.py suggest-patch --ids source_a,source_b
python3 scripts/sources_onboarding_helper.py apply-suggested --ids source_a,source_b
python3 scripts/sources_onboarding_helper.py apply-suggested --ids source_a,source_b --write
python3 scripts/sources_onboarding_helper.py fetch-check --section "User-curated: AI agents"
```

## Fast Workflow

### 1) Add sources

- Prefer `rss` when available.
- For `html`, start with explicit `html:` block (`link_selector`, `extraction_strategy`).
- If disabled, use:
  - `enabled: false`
  - placeholder selector `a[href^="/__<id>_disabled_placeholder__/"]`
  - short inline comment explaining why

### 2) Static lint (first)

```bash
python3 scripts/sources_onboarding_helper.py lint --section "User-curated: AI agents"
```

`lint` flags:
- obvious over-broad active selectors (`a[href]`, `[href*="/"]`)
- wide substring matchers (`/blog/`, `/learn/`) on active sources
- disabled-source hygiene issues (missing placeholder/comment)

### 3) Probe only problematic HTML sources

```bash
python3 scripts/sources_onboarding_helper.py probe --ids source_a,source_b
```

Use output to choose/tighten selectors:
- prefer `^=` path-prefix
- avoid `*=` substring on active sources if possible
- exclude tags/categories/pagination when obvious

### 4) One fetch smoke run

Run a single `ai-news fetch --once`, inspect errors/new counts, then patch.

### 4.5) Emit patch-ready `html:` suggestions (optional but useful)

```bash
python3 scripts/sources_onboarding_helper.py suggest-patch --ids source_a,source_b
```

This prints YAML snippets (not auto-applied) using simple ranking heuristics.

### 3.6) Apply suggestions (dry-run by default)

```bash
python3 scripts/sources_onboarding_helper.py apply-suggested --ids source_a,source_b
python3 scripts/sources_onboarding_helper.py apply-suggested --ids source_a,source_b --write
```

- `dry-run` prints current vs suggested selector.
- `--write` updates only `link_selector:` lines for the selected IDs.

### 5) Check section results in DB

```bash
python3 scripts/sources_onboarding_helper.py fetch-check --section "User-curated: AI agents"
```

Use this to quickly see:
- article counts per source in the section
- enabled HTML sources still at `0`
- recent `fetch_runs` summary

### 6) Optional nested review (recommended for big batches)

Use `multi-agent-orchestration-universal`:
- `executor`: summarize target `sources.yaml` block
- `reviewer`: PASS/FAIL on selector quality + disabled-source hygiene

Scope nested agents to:
- read `sources.yaml`
- write `tmp/...` only

## Practical Heuristics

- Good defaults:
  - `a[href^="/blog/"]`
  - `a[href^="./blog/"]`
  - `article h2 a[...]`, `article h3 a[...]`
- Avoid on active sources:
  - `a[href]`
  - `a[href*="/"]`
  - broad domain-wide `article a[href^="https://example.com/"]`

## Done Criteria

- `lint` returns no failures for the target section
- target HTML sources use explicit `html.link_selector`
- disabled sources use placeholder selectors + comments
- one fetch smoke run has no unexpected config-level failures
