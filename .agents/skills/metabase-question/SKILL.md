---
name: metabase-question
description: Answer a Soupop data question and, when the person wants to keep it, save it as a Metabase question in the staff collection. Use for "how many", "show me", "trend of", or "save this as a question".
---

# Answer a question, optionally save it

1. **Pin down the metric.** Restate it in one line: what is counted, at which grain, which filter, which date range and time zone. If one of these is genuinely ambiguous, ask one short question; otherwise pick the usual reading from `soupop-rules` and say so.
2. **Check the schema live.** mcp mode: the metadata tools. api mode: `python3 scripts-py/metabase_agent.py sql "<information_schema query>" --database-id 2` (or `DESCRIBE TABLE` on database 3).
3. **Run a small check query first** (a count, or `limit 20`) and confirm the numbers look sane.
4. **Answer:** the number or a short table first, then one line with the definition used.
5. **Save only if asked** (or offer: "Want me to save this as a question?").
   - mcp mode: the MCP tool for creating a native question, with `collection_id` = the staff collection.
   - api mode:
     ```bash
     python3 scripts-py/metabase_agent.py create-native-card --database-id 2 \
       --name "<clear name>" --display <table|line|bar|scalar> \
       --collection-id <staff_collection_id> \
       --description "<metric definition and caveats>" --sql "<sql>"
     ```
   - Name it so a colleague understands it without opening it, for example `BNPL - Weekly confirmed sales (Tehran time)`.
6. **Run the saved question** once and check it returns the same result.
7. **Reply with the link** `https://mt.soupop.ir/question/<id>`.

Never overwrite or edit an existing question. If a similar one exists, link it and offer to save a new copy in the staff collection.
