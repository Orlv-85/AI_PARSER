# Verified registry repair, 2026-10-10

The existing registry audit found dead URLs, selectors returning no article
links, and a redirect alias of the Google DeepMind feed. Repair only verified
endpoints, retaining source keys and article history. Model judgments alone
must not disable existing sources.

- Use the canonical DeepMind RSS URL. Disable the separately approved duplicate
  `deepmind-google-blog-rss-xml`; retain both records and all article relations.
- Replace Microsoft AI's gone feed with the official Microsoft Cloud RSS feed.
- Read Rainbird's current resource publication cards instead of its dead feed.
- Correct Dify and AGI relative paths, E2B resource cards, Linguamatics's own blog,
  the Outerbounds redirect destination, and Vellum's official legacy blog listing.
- Prefer Prompt Engineering's verified RSS feed over its changed HTML template.
- Leave ZAPTEST unchanged until a usable current publication endpoint is found.
  Old `/blog`, `/articles`, and `/feed` redirects return 404 on its new domain.
- Do not remove sources, change scheduling/weights or approve other candidates.

`scripts/repair_source_registry.py` defaults to dry-run. Applying requires an
exclusive, private JSON backup before any mutation and updates only existing
records. Reset conditional HTTP state when a source URL/type changes. Refuse to
disable the duplicate if its URL changed or the canonical record is missing.
Reapplying produces no changes. Deploy the reviewed tag before running it:

```sh
docker exec ai-news-app python scripts/repair_source_registry.py
docker exec ai-news-app python scripts/repair_source_registry.py --apply \
  --backup /app/data/source_cleanup_backups/registry_repair_20261010.json
```

Check selected live listings with the actual RSS/HTML parsers, run the full repo
lint/test gates, verify the production registry and health after application.
