#!/usr/bin/env python3
from metabase_agent import MetabaseClient, load_env, print_json


DASHBOARD_NAME = "AI Chatbot Analytics Dashboard"
DATABASE_ID = 3

TEMPLATE_TAGS = {
    "start_date": {"id": "start_date", "name": "start_date", "display-name": "Start date", "type": "date", "required": False},
    "end_date": {"id": "end_date", "name": "end_date", "display-name": "End date", "type": "date", "required": False},
    "user_id": {"id": "user_id", "name": "user_id", "display-name": "User ID", "type": "number", "required": False},
    "session_id": {"id": "session_id", "name": "session_id", "display-name": "Session ID", "type": "text", "required": False},
    "llm_model": {"id": "llm_model", "name": "llm_model", "display-name": "LLM model", "type": "text", "required": False},
    "event_type": {"id": "event_type", "name": "event_type", "display-name": "App event type", "type": "text", "required": False},
    "event_action": {"id": "event_action", "name": "event_action", "display-name": "App event action", "type": "text", "required": False},
}


QUESTIONS = [
    {
        "name": "AI Chatbot - App Event KPI",
        "display": "scalar",
        "description": "Total ai_chat_bot app events. Use with date/user filters for entry-point volume.",
        "sql": """
select count() as ai_chat_bot_events
from app_events
where name = 'ai_chat_bot'
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and user_id = {{user_id}}]]
  [[and params['type'] = {{event_type}}]]
  [[and params['action'] = {{event_action}}]]
""",
    },
    {
        "name": "AI Chatbot - Chat KPI",
        "display": "table",
        "description": "Core chat metrics: chats, users, sessions, success rate, latency, token totals, and freshness.",
        "sql": """
select
  count() as chats,
  uniqExact(user_id) as users,
  uniqExact(session_id) as sessions,
  round(100 * avg(JSONExtractBool(raw_response, 'is_successful')), 2) as success_rate_pct,
  round(avg(toUInt32OrZero(extra['response_time_ms'])), 0) as avg_response_time_ms,
  quantile(0.90)(toUInt32OrZero(extra['response_time_ms'])) as p90_response_time_ms,
  sum(toUInt64OrZero(extra['total_tokens'])) as total_tokens,
  max(created_at) as latest_chat_at
from chatbot_chats
where 1 = 1
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and user_id = {{user_id}}]]
  [[and session_id = {{session_id}}]]
  [[and llm_model = {{llm_model}}]]
""",
    },
    {
        "name": "AI Chatbot - Daily App Events",
        "display": "line",
        "description": "Daily ai_chat_bot app entry events and unique users.",
        "sql": """
select
  toDate(created_at) as day,
  count() as events,
  uniqExact(user_id) as users
from app_events
where name = 'ai_chat_bot'
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and user_id = {{user_id}}]]
  [[and params['type'] = {{event_type}}]]
  [[and params['action'] = {{event_action}}]]
group by day
order by day
""",
    },
    {
        "name": "AI Chatbot - Daily Chats and Sessions",
        "display": "line",
        "description": "Daily chat volume, active users, and sessions.",
        "sql": """
select
  toDate(created_at) as day,
  count() as chats,
  uniqExact(user_id) as users,
  uniqExact(session_id) as sessions
from chatbot_chats
where 1 = 1
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and user_id = {{user_id}}]]
  [[and session_id = {{session_id}}]]
  [[and llm_model = {{llm_model}}]]
group by day
order by day
""",
    },
    {
        "name": "AI Chatbot - App Event Action and Type",
        "display": "bar",
        "description": "How users interact with the ai_chat_bot app event: startup, SEND, and other actions/types.",
        "sql": """
select
  params['action'] as action,
  if(params['type'] = '', 'unknown', params['type']) as type,
  count() as events,
  uniqExact(user_id) as users
from app_events
where name = 'ai_chat_bot'
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and user_id = {{user_id}}]]
  [[and params['type'] = {{event_type}}]]
  [[and params['action'] = {{event_action}}]]
group by action, type
order by events desc
""",
    },
    {
        "name": "AI Chatbot - Top User Need Tags",
        "display": "bar",
        "description": "Most common user intent tags extracted from question_tag.",
        "sql": """
select
  trim(BOTH ' ' from arrayJoin(splitByChar(',', question_tag))) as user_need_tag,
  count() as chats,
  uniqExact(user_id) as users
from chatbot_chats
where question_tag != ''
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and user_id = {{user_id}}]]
  [[and session_id = {{session_id}}]]
  [[and llm_model = {{llm_model}}]]
group by user_need_tag
order by chats desc
limit 30
""",
    },
    {
        "name": "AI Chatbot - Top Answer Tags",
        "display": "bar",
        "description": "What the assistant is returning most often: recommendations, diagnosis, maintenance, service history, etc.",
        "sql": """
select
  trim(BOTH ' ' from arrayJoin(splitByChar(',', answer_tag))) as answer_tag,
  count() as chats,
  uniqExact(user_id) as users
from chatbot_chats
where answer_tag != ''
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and user_id = {{user_id}}]]
  [[and session_id = {{session_id}}]]
  [[and llm_model = {{llm_model}}]]
group by answer_tag
order by chats desc
limit 30
""",
    },
    {
        "name": "AI Chatbot - Success Status",
        "display": "bar",
        "description": "Successful vs unsuccessful raw_response outcomes.",
        "sql": """
select
  if(JSONExtractBool(raw_response, 'is_successful'), 'successful', 'not_successful') as status,
  count() as chats,
  round(100 * count() / sum(count()) over (), 2) as pct
from chatbot_chats
where 1 = 1
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and user_id = {{user_id}}]]
  [[and session_id = {{session_id}}]]
  [[and llm_model = {{llm_model}}]]
group by status
order by chats desc
""",
    },
    {
        "name": "AI Chatbot - Daily Latency",
        "display": "line",
        "description": "Average, median, and p90 response time from extra.response_time_ms.",
        "sql": """
select
  toDate(created_at) as day,
  round(avg(toUInt32OrZero(extra['response_time_ms'])), 0) as avg_ms,
  quantile(0.50)(toUInt32OrZero(extra['response_time_ms'])) as p50_ms,
  quantile(0.90)(toUInt32OrZero(extra['response_time_ms'])) as p90_ms
from chatbot_chats
where extra['response_time_ms'] != ''
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and user_id = {{user_id}}]]
  [[and session_id = {{session_id}}]]
  [[and llm_model = {{llm_model}}]]
group by day
order by day
""",
    },
    {
        "name": "AI Chatbot - Daily Token Usage",
        "display": "line",
        "description": "Input, output, and total token usage from extra JSON-string values.",
        "sql": """
select
  toDate(created_at) as day,
  sum(toUInt64OrZero(extra['input_tokens'])) as input_tokens,
  sum(toUInt64OrZero(extra['output_tokens'])) as output_tokens,
  sum(toUInt64OrZero(extra['total_tokens'])) as total_tokens
from chatbot_chats
where extra['total_tokens'] != ''
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and user_id = {{user_id}}]]
  [[and session_id = {{session_id}}]]
  [[and llm_model = {{llm_model}}]]
group by day
order by day
""",
    },
    {
        "name": "AI Chatbot - Vendor Recommendation Funnel",
        "display": "table",
        "description": "Vendor-search demand vs actual recommended vendors in raw_response.",
        "sql": """
select
  count() as chats,
  countIf(position(question_tag, 'vendor_search') > 0 or position(answer_tag, 'vendor') > 0) as vendor_related_chats,
  countIf(JSONLength(JSONExtractRaw(raw_response, 'data', 'recommended_vendor')) > 0) as chats_with_recommended_vendor,
  sum(JSONLength(JSONExtractRaw(raw_response, 'data', 'recommended_vendor'))) as recommended_vendor_items,
  round(100 * chats_with_recommended_vendor / chats, 2) as recommendation_rate_pct
from chatbot_chats
where 1 = 1
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and user_id = {{user_id}}]]
  [[and session_id = {{session_id}}]]
  [[and llm_model = {{llm_model}}]]
""",
    },
    {
        "name": "AI Chatbot - LLM Model Performance",
        "display": "table",
        "description": "Volume, success, latency, and token usage by LLM model.",
        "sql": """
select
  llm_model,
  count() as chats,
  uniqExact(user_id) as users,
  round(100 * avg(JSONExtractBool(raw_response, 'is_successful')), 2) as success_rate_pct,
  round(avg(toUInt32OrZero(extra['response_time_ms'])), 0) as avg_response_time_ms,
  quantile(0.90)(toUInt32OrZero(extra['response_time_ms'])) as p90_response_time_ms,
  round(avg(toUInt64OrZero(extra['total_tokens'])), 0) as avg_total_tokens
from chatbot_chats
where 1 = 1
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and user_id = {{user_id}}]]
  [[and session_id = {{session_id}}]]
  [[and llm_model = {{llm_model}}]]
group by llm_model
order by chats desc
""",
    },
    {
        "name": "AI Chatbot - Recent Chat Trace",
        "display": "table",
        "description": "Recent conversation trace for product and support review, including JSON-derived success and recommendation count.",
        "sql": """
select
  created_at,
  user_id,
  session_id,
  llm_model,
  question_tag,
  answer_tag,
  left(question, 180) as question_sample,
  left(answer, 240) as answer_sample,
  JSONExtractBool(raw_response, 'is_successful') as is_successful,
  JSONLength(JSONExtractRaw(raw_response, 'data', 'recommended_vendor')) as recommended_vendor_count,
  toUInt32OrZero(extra['response_time_ms']) as response_time_ms,
  toUInt64OrZero(extra['total_tokens']) as total_tokens,
  JSONExtractString(raw_response, 'data', 'next_ai_question') as next_ai_question
from chatbot_chats
where 1 = 1
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and user_id = {{user_id}}]]
  [[and session_id = {{session_id}}]]
  [[and llm_model = {{llm_model}}]]
order by created_at desc
limit 200
""",
    },
    {
        "name": "AI Chatbot - Extra Field Coverage",
        "display": "bar",
        "description": "Coverage of extra map keys, including profile/car/location/services JSON strings and token fields.",
        "sql": """
select
  arrayJoin(mapKeys(extra)) as extra_key,
  count() as rows_with_key,
  round(100 * rows_with_key / (select count() from chatbot_chats), 2) as coverage_pct,
  any(extra[extra_key]) as sample_value
from chatbot_chats
where 1 = 1
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and user_id = {{user_id}}]]
  [[and session_id = {{session_id}}]]
  [[and llm_model = {{llm_model}}]]
group by extra_key
order by rows_with_key desc
""",
    },
    {
        "name": "AI Chatbot - Freshness Monitor",
        "display": "table",
        "description": "Compares latest app event and latest persisted chat to catch ingestion/product tracking gaps.",
        "sql": """
select
  'app_events.ai_chat_bot' as source,
  count() as rows,
  max(created_at) as latest_at
from app_events
where name = 'ai_chat_bot'
union all
select
  'chatbot_chats' as source,
  count() as rows,
  max(created_at) as latest_at
from chatbot_chats
order by latest_at desc
""",
    },
]


def dashboard_cards(card_ids):
    cards = []
    row = 0
    for index, card_id in enumerate(card_ids):
        is_half = index in {0, 1, 4, 7, 10, 11, 13, 14}
        size_x = 12 if is_half else 24
        size_y = 7 if is_half else 9
        col = 12 if is_half and len(cards) > 0 and cards[-1]["size_x"] == 12 and cards[-1]["row"] == row else 0
        if col == 0 and cards:
            row = max(card["row"] + card["size_y"] for card in cards)
        cards.append({
            "id": -(index + 1),
            "card_id": int(card_id),
            "row": row,
            "col": col,
            "size_x": size_x,
            "size_y": size_y,
            "parameter_mappings": [],
            "series": [],
        })
    return cards


def require_id(response, label):
    value = response.get("id") or response.get(f"{label}_id")
    if not value:
        raise SystemExit(f"Could not find {label} id in response: {response}")
    return value


def main():
    env = load_env()
    if env.get("METABASE_DATABASE_ID") != str(DATABASE_ID):
        raise SystemExit("Set METABASE_DATABASE_ID=3 in .env before running this script.")

    client = MetabaseClient()
    print("Checking Metabase Agent API...")
    print_json(client.ping())

    created_questions = []
    for question in QUESTIONS:
        print(f"Creating question: {question['name']}")
        saved = client.create_native_card(
            database_id=DATABASE_ID,
            name=question["name"],
            sql=question["sql"].strip(),
            display=question["display"],
            description=question["description"],
            template_tags=TEMPLATE_TAGS,
        )
        created_questions.append({"id": require_id(saved, "card"), "name": question["name"]})

    print(f"Creating dashboard: {DASHBOARD_NAME}")
    dashboard = client.create_standard_dashboard(
        name=DASHBOARD_NAME,
        description=(
            "Analytics dashboard for App Events where name = ai_chat_bot and chatbot_chats. "
            "It covers activation, usage, user needs, answer behavior, success/failure, latency, token usage, "
            "vendor recommendations, raw_response JSON-derived fields, and recent chat traces. "
            "Recommended dashboard filters: date range, user_id, session_id, llm_model, app event type, app event action."
        ),
    )
    dashboard_id = require_id(dashboard, "dashboard")
    print("Adding questions to dashboard...")
    updated = client.update_standard_dashboard_cards(
        dashboard_id,
        dashboard_cards([question["id"] for question in created_questions]),
    )

    dashboard_url = f"{client.base_url}/dashboard/{dashboard_id}"
    print_json({
        "dashboard_id": dashboard_id,
        "dashboard_url": dashboard_url,
        "questions": created_questions,
        "updated_dashboard": updated,
    })
    print(f"\nOpen dashboard: {dashboard_url}")


if __name__ == "__main__":
    main()
