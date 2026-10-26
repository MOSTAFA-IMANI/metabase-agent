# Chatbot analytics

Chatbot records and app events live in ClickHouse database 3. Its configured timezone is UTC. The schema and dashboard were checked against the live Metabase instance on 2026-10-10.

## Tables

### `analytics.chatbot_chats` — Metabase table 259

One persisted question/answer record per chat row. A user can create multiple rows per day.

```text
question String, answer String, question_tag String, answer_tag String,
user_id Int64, llm_model String, created_at DateTime, extra Map,
session_id String, raw_response String, app_name String, os String,
auto_service_id Int64
```

Metabase field IDs: `user_id` 2093, `llm_model` 2094, `created_at` 2095, `extra` 2096, `session_id` 2097, `raw_response` 2098, `app_name` 2198, `os` 2197, `auto_service_id` 2199.

### `analytics.app_events` — Metabase table 241

One tracked event row. Chatbot entry events use `name = 'ai_chat_bot'` in current questions.

```text
name String, created_at DateTime, user_id Int64, auto_service_id Int64,
device_id UUID, params Map, os String, app_name String
```

Metabase field IDs: `name` 1916, `created_at` 1920, `user_id` 1917, `params` 1919, `app_name` 2133, `os` 2132, `auto_service_id` 1918.

## How to read the story

1. App events indicate tracked interaction, such as entering the chatbot, sending a message, or another action. They are not equivalent to a successfully persisted chat.
2. `chatbot_chats` rows show saved questions and answers. Count rows as chats, distinct `user_id` as users, and distinct `session_id` as sessions.
3. `extra` is a map. Chat source is recorded in `extra['s']`; missing, null-like, or empty values should be retained as an `Unknown` source bucket. Some other values inside `extra` are JSON-formatted strings; parse with ClickHouse JSON functions after checking actual keys and shapes.
4. `raw_response` is a JSON string. Use JSON extraction, not text splitting, to derive success or recommendation fields.
5. `app_name` is the recorded application label. Event labels and chat labels may differ; do not combine them as if they share one source taxonomy.
6. Timestamps are UTC. Convert explicitly for Asia/Tehran date reporting.

Daily distinct-user counts are not additive across days. Event volume, chat volume, and distinct users should be reported separately.

## Live dashboard cards

- [AI Chatbot Analytics Dashboard](https://mt.soupop.ir/dashboard/37)
- [Chat KPI](https://mt.soupop.ir/question/967)
- [Daily chats and sessions](https://mt.soupop.ir/question/969)
- [Success status](https://mt.soupop.ir/question/973)
- [Latency](https://mt.soupop.ir/question/974)
- [Token usage](https://mt.soupop.ir/question/975)
- [LLM model performance](https://mt.soupop.ir/question/977)
- [Recent chat trace](https://mt.soupop.ir/question/978)
- [Freshness monitor](https://mt.soupop.ir/question/980)
- [Chats and users by source](https://mt.soupop.ir/question/1078)
- [Chats, sessions, and users by `extra['s']` source](https://mt.soupop.ir/question/1089)
- [App events and users by source](https://mt.soupop.ir/question/1081)
- [App event actions by source](https://mt.soupop.ir/question/1084)

The chat-source distribution uses `chatbot_chats.extra['s']`; it is distinct from the older `app_name` grouping in question 1078. The `Unknown` row includes records where `s` is absent or empty. Event source cards continue to use `app_events.app_name` and should not be equated with chat `extra['s']` without a validated mapping.

The existing dashboard includes chat text and recent traces. Use aggregate cards for routine reporting and restrict access to raw question, answer, and `raw_response` content.

## Repository implementation

- `build_ai_chatbot_analytics_dashboard.py` creates questions and a new dashboard. It is not an update script.
- `add_ai_chatbot_source_analytics.py` is the idempotent updater for dashboard 37. It reads the dashboard first and preserves existing cards and filter mappings.
