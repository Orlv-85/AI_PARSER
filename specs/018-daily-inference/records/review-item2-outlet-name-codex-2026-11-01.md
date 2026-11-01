**Verdict: merge after fixes.**

- **P2 — Empty attribution:** [bulletin_input.py:36](/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/codex-outlet/src/app/storage/bulletin_input.py:36) turns `"(main feed)"` into `""`; the earlier hostname fallback cannot catch this, so rendering produces `Title ()`. **Fix:** apply the hostname fallback after normalization and test a label-only source name.
- **P2 — Call sites lack regression coverage:** [test_bulletin_builder.py:410](/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/codex-outlet/tests/unit/test_bulletin_builder.py:410) tests only the helper. Removing either call-site invocation would leave the tests passing. **Fix:** seed `"TechCrunch (main feed)"` and `"www.news.example"`; existing loader assertions already check their normalized outputs. Alternatively, after loading both origins, add:
  ```python
  assert {c.origin: c.outlet for c in loaded.candidates} == {
      "digest": "TechCrunch", "world": "news.example",
  }
  ```

Edge checks confirmed:

| Input | Result |
|---|---|
| `Machine Intelligence Research Institute (MIRI)` | Loses `(MIRI)`, despite being a name component |
| `TechCrunch (main (RSS) feed)` | Unchanged: nested label is not removed |
| `WWW.bbc.com` | Unchanged: prefix matching is case-sensitive |
| IPv4 / IPv6 address | Unchanged |
| Internal parentheses or internal `www.` | Preserved |

The broad removal of trailing name components follows the supplied implementation prompt; it cannot distinguish names from feed labels. Both call sites use the helper, and `/daily` and digest rendering are untouched. [builder.md:47](/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/codex-outlet/src/app/core/bulletin/builder.md:47) names the correct test and matches ordinary cases, but should specify non-nested labels.

The requested test invocation failed before collection: `FileNotFoundError: No usable temporary directory found` under the read-only sandbox. Retrying with `--capture=sys -p no:cacheprovider` and bytecode writes disabled succeeded:

```text
39 passed in 0.70s
```