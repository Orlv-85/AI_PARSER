# Item 4a feature document review

Reviewer: separate Codex agent session `storage_doc_review`, 2026-11-02.
Scope: bulletin_store.md, builder.md and writer.md against the item 4a contract,
implementation and tests. No network, paid calls or database operations by the reviewer.

Findings resolved:

- Builder introduction still described dry-run-only behavior. It now shows optional --dry-run
  and links to the storage contract.
- First CLI save could reach an existing database without the bulletins table. The save helper
  now calls create_all, following existing CLI initialization. A focused test first failed with
  `OperationalError: no such table: bulletins`, then passed after the fix.

Re-review: both findings resolved; no remaining defects found in the reviewed docs or corrections.
Exact Bulletin.as_dict() storage follows the explicit 4a contract; no article-id schema expansion.

Handoff rule: save prompts for another session before giving them to the user. Feature prompts,
reviews and reports belong in specs/<NNN>-<name>/records/, never docs/ root.
