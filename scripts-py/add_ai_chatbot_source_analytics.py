#!/usr/bin/env python3
"""Add source analytics to the existing AI Chatbot dashboard."""

from metabase_agent import MetabaseClient


DASHBOARD_ID = 37
DATABASE_ID = 3


def tags(created_at_field_id, events=False):
    result = {
        "date_range": {
            "id": "date_range",
            "name": "date_range",
            "display-name": "Date range",
            "type": "dimension",
            "dimension": ["field", created_at_field_id, None],
            "widget-type": "date/all-options",
        },
        "user_id": {
            "id": "user_id",
            "name": "user_id",
            "display-name": "User ID",
            "type": "number",
            "required": False,
        },
    }
    other_names = ("event_type", "event_action") if events else ("session_id", "llm_model")
    for name in other_names:
        result[name] = {
            "id": name,
            "name": name,
            "display-name": name.replace("_", " ").title(),
            "type": "text",
            "required": False,
        }
    return result


CHAT_FILTERS = """
  [[and {{date_range}}]]
  [[and user_id = {{user_id}}]]
  [[and session_id = {{session_id}}]]
  [[and llm_model = {{llm_model}}]]
"""

EVENT_FILTERS = """
  [[and {{date_range}}]]
  [[and user_id = {{user_id}}]]
  [[and params['type'] = {{event_type}}]]
  [[and params['action'] = {{event_action}}]]
"""

SOURCE = "if(app_name = '', 'Unknown', app_name)"

QUESTIONS = [
    {
        "name": "AI Chatbot - Chats and Users by Source",
        "description": "Chats and distinct chat users by the recorded chatbot_chats.app_name. Counts obey dashboard chat filters.",
        "display": "bar",
        "events": False,
        "sql": f"""
select {SOURCE} as source, count() as chats, uniqExact(user_id) as users
from chatbot_chats
where 1 = 1 {CHAT_FILTERS}
group by source
order by chats desc
""",
        "width": 24,
        "height": 8,
    },
    {
        "name": "AI Chatbot - Chats, Sessions and Users by Extra Source",
        "description": "Distribution of persisted chatbot chat rows by extra['s']. Missing, null-like, and empty source values are grouped as Unknown. Sessions count distinct nonblank session_id values; users count distinct user_id values. Obeys dashboard chat filters.",
        "display": "table",
        "events": False,
        "sql": f"""
select
  if(mapContains(extra, 's') AND trim(extra['s']) != '', trim(extra['s']), 'Unknown') as source,
  count() as chats,
  uniqExactIf(session_id, session_id != '') as sessions,
  uniqExact(user_id) as users
from chatbot_chats
where 1 = 1 {CHAT_FILTERS}
group by source
order by chats desc
""",
        "width": 24,
        "height": 8,
    },
    {
        "name": "AI Chatbot - Daily Chats by Source",
        "description": "Daily chat count by chatbot_chats.app_name. A user can contribute multiple chats per day.",
        "display": "line",
        "events": False,
        "sql": f"""
select toDate(created_at) as day, {SOURCE} as source, count() as chats
from chatbot_chats
where 1 = 1 {CHAT_FILTERS}
group by day, source
order by day, source
""",
        "width": 12,
        "height": 9,
    },
    {
        "name": "AI Chatbot - Daily Users by Source",
        "description": "Distinct users per day and chatbot_chats.app_name; daily user counts are not additive across days.",
        "display": "line",
        "events": False,
        "sql": f"""
select toDate(created_at) as day, {SOURCE} as source, uniqExact(user_id) as users
from chatbot_chats
where 1 = 1 {CHAT_FILTERS}
group by day, source
order by day, source
""",
        "width": 12,
        "height": 9,
    },
    {
        "name": "AI Chatbot - App Events and Users by Source",
        "description": "ai_chat_bot events and distinct event users by the recorded app_events.app_name. Event source labels may differ from chat source labels.",
        "display": "bar",
        "events": True,
        "sql": f"""
select {SOURCE} as source, count() as events, uniqExact(user_id) as users
from app_events
where name = 'ai_chat_bot' {EVENT_FILTERS}
group by source
order by events desc
""",
        "width": 24,
        "height": 8,
    },
    {
        "name": "AI Chatbot - Daily App Events by Source",
        "description": "Daily ai_chat_bot event volume by app_events.app_name.",
        "display": "line",
        "events": True,
        "sql": f"""
select toDate(created_at) as day, {SOURCE} as source, count() as events
from app_events
where name = 'ai_chat_bot' {EVENT_FILTERS}
group by day, source
order by day, source
""",
        "width": 12,
        "height": 9,
    },
    {
        "name": "AI Chatbot - Daily App Event Users by Source",
        "description": "Daily distinct ai_chat_bot event users by app_events.app_name.",
        "display": "line",
        "events": True,
        "sql": f"""
select toDate(created_at) as day, {SOURCE} as source, uniqExact(user_id) as users
from app_events
where name = 'ai_chat_bot' {EVENT_FILTERS}
group by day, source
order by day, source
""",
        "width": 12,
        "height": 9,
    },
    {
        "name": "AI Chatbot - App Event Actions by Source",
        "description": "Event type and action by app_events.app_name, with event and distinct-user counts.",
        "display": "table",
        "events": True,
        "sql": f"""
select
  {SOURCE} as source,
  if(params['type'] = '', 'Unknown', params['type']) as event_type,
  if(params['action'] = '', 'Unknown', params['action']) as event_action,
  count() as events,
  uniqExact(user_id) as users
from app_events
where name = 'ai_chat_bot' {EVENT_FILTERS}
group by source, event_type, event_action
order by events desc
limit 100
""",
        "width": 24,
        "height": 10,
    },
]


def mappings(card_id, events):
    names = ["date_range", "user_id"]
    names += ["event_type", "event_action"] if events else ["session_id", "llm_model"]
    return [
        {
            "parameter_id": name,
            "card_id": card_id,
            "target": ["dimension" if name == "date_range" else "variable", ["template-tag", name]],
        }
        for name in names
    ]


def preserved_dashcard(card):
    keys = (
        "id", "card_id", "row", "col", "size_x", "size_y",
        "parameter_mappings", "series", "visualization_settings",
        "dashboard_tab_id", "inline_parameters", "action_id",
    )
    return {key: card[key] for key in keys if key in card}


def main():
    client = MetabaseClient()
    dashboard = client.call("GET", f"/api/dashboard/{DASHBOARD_ID}")
    if dashboard.get("name") != "AI Chatbot Analytics Dashboard":
        raise SystemExit("Dashboard 37 has an unexpected name; no changes made.")

    existing = {card["card"]["name"]: card for card in dashboard["dashcards"] if card.get("card")}
    cards = [preserved_dashcard(card) for card in dashboard["dashcards"]]
    row = max((card["row"] + card["size_y"] for card in cards), default=0)
    added = []
    repaired = []

    for question in QUESTIONS:
        if question["name"] in existing:
            card_id = existing[question["name"]]["card_id"]
            expected = mappings(card_id, question["events"])
            for card in cards:
                if card.get("card_id") == card_id and card.get("parameter_mappings") != expected:
                    card["parameter_mappings"] = expected
                    repaired.append(question["name"])
                    break
            continue
        is_event = question["events"]
        field_id = 1920 if is_event else 2095
        card = client.create_native_card(
            database_id=DATABASE_ID,
            name=question["name"],
            sql=question["sql"].strip(),
            display=question["display"],
            description=question["description"],
            template_tags=tags(field_id, events=is_event),
        )
        card_id = int(card["id"])
        width = question["width"]
        col = 12 if width == 12 and cards and cards[-1]["row"] == row and cards[-1]["col"] == 0 and cards[-1]["size_x"] == 12 else 0
        if col == 0 and added:
            row = max(item["row"] + item["size_y"] for item in added)
        dashcard = {
            "id": -(len(added) + 1),
            "card_id": card_id,
            "row": row,
            "col": col,
            "size_x": width,
            "size_y": question["height"],
            "parameter_mappings": mappings(card_id, is_event),
            "series": [],
        }
        added.append(dashcard)
        cards.append(dashcard)
        print(f"Created {question['name']}: /question/{card_id}")

    if added or repaired:
        client.update_standard_dashboard_cards(DASHBOARD_ID, cards)
        print(f"Added {len(added)} questions and repaired {len(repaired)} mappings on {client.base_url}/dashboard/{DASHBOARD_ID}")
    else:
        print("All source questions and filter mappings are already on the dashboard.")


if __name__ == "__main__":
    main()
