---
name: metabase-dashboard
description: Build a new Metabase dashboard in the Soupop staff collection from a few questions, with filters that actually apply. Use when someone asks for a dashboard, a report page, or "put these charts together".
---

# Build a dashboard

New dashboards only, always in the staff collection. Never change an existing dashboard; if the person wants one changed, build a new one next to it and tell them an analyst can merge it.

1. **Agree the layout in one message:** the title, 3 to 8 cards (metric, chart type), and the filters (usually a date range, sometimes product). Start building unless the person objects.
2. **Check for existing assets.** Search Metabase for questions with the same metric. Reuse a saved question by id when its definition matches `soupop-rules`; otherwise create a new one with `metabase-question`.
3. **Create each card's question** in the staff collection. For a date filter use a field filter template tag:
   ```sql
   select ... from invoices where status = 'CONFIRMED' [[and {{date_range}}]]
   ```
   with tag type `dimension` on the live `created_at` field id and widget `date/all-options`. Look the field id up live; never reuse a field id from another table.
4. **Create the dashboard** in the staff collection (mcp: dashboard tool; api: `MetabaseClient.create_standard_dashboard(name, description, collection_id, parameters)`).
5. **Add the cards** in one update (`update_standard_dashboard_cards`), on a 24-column grid: number cards 6 wide by 3 tall across the top, charts 12 wide by 6 tall below. Map the dashboard date filter to each card's `["dimension", ["template-tag", "date_range"]]`.
6. **Verify:** read the dashboard back, run one card with and without a bounded date range, and confirm the counts change.
7. **Reply** with `https://mt.soupop.ir/dashboard/<id>`, the list of cards, and any caveat (for example, ClickHouse cards use UTC days).

If a step fails partway, say which cards were created so nothing is left half-built without the person knowing.
