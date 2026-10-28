#!/usr/bin/env python3
"""Create or safely refresh the BNPL AR and DSO dashboard."""

from urllib.parse import urlencode

from metabase_agent import MetabaseClient, load_env


DATABASE_ID = 2
DASHBOARD_NAME = "BNPL Accounts Receivable and DSO"
DASHBOARD_DESCRIPTION = (
    "Accounts receivable and collection performance across all installment sources. "
    "Amounts are shown in native database units, without conversion. Business rule: "
    "installment number 1 is due at invoice time and is excluded from AR, DPD, and DSO; "
    "numbers greater than 1 are scheduled receivables. Confirmed gateway evidence is "
    "deduplicated across direct and installment-payment links. Origination uses installment "
    "created_at as its date proxy. Cash-collection days use scheduled installment value as "
    "an NMV proxy; current unpaid cohorts are incomplete and can understate the measure."
)

TEMPLATE_TAGS = {
    "source": {
        "id": "source",
        "name": "source",
        "display-name": "Product source",
        "type": "text",
        "required": False,
    }
}

BASE_CTES = """
payment_links AS (
  SELECT installment_id, payment_id
  FROM bnpl_gateway_installments_payment
  WHERE installment_id IS NOT NULL AND payment_id IS NOT NULL
  UNION
  SELECT id AS installment_id, payment_id
  FROM bnpl_credit_installments
  WHERE payment_id IS NOT NULL
),
payment_status AS (
  SELECT links.installment_id,
    MIN(payments.confirmed_at) FILTER (WHERE payments.confirmed_at IS NOT NULL) AS first_confirmed_at
  FROM payment_links links
  JOIN bnpl_gateway_payments payments ON payments.id = links.payment_id
  GROUP BY links.installment_id
),
base AS (
  SELECT i.id AS installment_id,
    COALESCE(i.source, 'Unknown') AS product_source,
    i.number AS installment_number,
    i.created_at::date AS origination_date,
    i.due_date,
    COALESCE(i.amount, 0)::numeric AS scheduled_amount,
    COALESCE(i.penalty, 0)::numeric AS penalty,
    p.first_confirmed_at,
    p.first_confirmed_at::date AS paid_date
  FROM bnpl_credit_installments i
  LEFT JOIN payment_status p ON p.installment_id = i.id
  WHERE i.created_at::date <= CURRENT_DATE
    [[AND COALESCE(UPPER(i.source), 'UNKNOWN') = UPPER({{source}})]]
)
"""

DAILY_CTES = """
events AS (
  SELECT product_source, origination_date AS day,
    scheduled_amount AS ar_change, scheduled_amount AS credit_sales
  FROM base
  WHERE installment_number > 1
  UNION ALL
  SELECT product_source, GREATEST(paid_date, origination_date) AS day,
    -scheduled_amount AS ar_change, 0::numeric AS credit_sales
  FROM base
  WHERE installment_number > 1 AND paid_date IS NOT NULL
),
event_days AS (
  SELECT product_source, day, SUM(ar_change) AS ar_change, SUM(credit_sales) AS credit_sales
  FROM events
  GROUP BY product_source, day
),
source_list AS (
  SELECT DISTINCT product_source FROM base WHERE installment_number > 1
),
date_bounds AS (
  SELECT COALESCE(MIN(day), CURRENT_DATE) AS first_day FROM event_days
),
calendar AS (
  SELECT source_list.product_source, generated.day::date AS day
  FROM source_list
  CROSS JOIN date_bounds
  CROSS JOIN LATERAL generate_series(date_bounds.first_day::timestamp,
    CURRENT_DATE::timestamp, INTERVAL '1 day') AS generated(day)
),
daily AS (
  SELECT calendar.product_source, calendar.day,
    SUM(COALESCE(event_days.ar_change, 0)) OVER (
      PARTITION BY calendar.product_source ORDER BY calendar.day
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS ar_balance,
    COALESCE(event_days.credit_sales, 0) AS credit_sales
  FROM calendar
  LEFT JOIN event_days USING (product_source, day)
)
"""


def question(name, sql, display, description, width, height, visualization_settings=None):
    return {
        "name": name,
        "sql": sql.strip(),
        "display": display,
        "description": description,
        "width": width,
        "height": height,
        "visualization_settings": visualization_settings or {},
    }


QUESTIONS = [
    question(
        "BNPL - AR and DSO KPI Summary",
        f"""
WITH {BASE_CTES}, {DAILY_CTES},
portfolio_daily AS (
  SELECT day, SUM(ar_balance) AS ar_balance, SUM(credit_sales) AS credit_sales
  FROM daily GROUP BY day
),
mtd AS (
  SELECT AVG(ar_balance) AS average_ar_mtd,
    SUM(ar_balance) AS ar_days_mtd,
    SUM(credit_sales) AS credit_sales_mtd,
    COUNT(*) AS elapsed_days
  FROM portfolio_daily
  WHERE day >= DATE_TRUNC('month', CURRENT_DATE)::date AND day <= CURRENT_DATE
),
contractual AS (
  SELECT SUM(scheduled_amount * (due_date - origination_date)) /
    NULLIF(SUM(scheduled_amount), 0) AS contractual_dso_mtd_days
  FROM base
  WHERE installment_number > 1 AND due_date IS NOT NULL
    AND origination_date >= DATE_TRUNC('month', CURRENT_DATE)::date
),
upfront AS (
  SELECT
    SUM(scheduled_amount) FILTER (WHERE installment_number = 1) AS scheduled_down_payment_mtd,
    SUM(scheduled_amount) FILTER (WHERE installment_number = 1 AND first_confirmed_at IS NOT NULL) AS confirmed_down_payment_mtd,
    SUM(scheduled_amount) FILTER (WHERE installment_number = 1 AND first_confirmed_at IS NULL) AS unconfirmed_down_payment_mtd
  FROM base
  WHERE origination_date >= DATE_TRUNC('month', CURRENT_DATE)::date
),
cash_days AS (
  SELECT
    SUM(scheduled_amount * GREATEST(paid_date - origination_date, 0))
      FILTER (WHERE first_confirmed_at IS NOT NULL AND installment_number >= 1)
      / NULLIF(SUM(scheduled_amount) FILTER (WHERE installment_number >= 1), 0) AS cash_collection_days_mtd,
    SUM(scheduled_amount) FILTER (WHERE installment_number >= 1) AS scheduled_nmv_proxy_mtd
  FROM base
  WHERE origination_date >= DATE_TRUNC('month', CURRENT_DATE)::date
),
current_ar AS (
  SELECT
    SUM(scheduled_amount) FILTER (WHERE installment_number > 1 AND first_confirmed_at IS NULL) AS current_ar,
    SUM(scheduled_amount) FILTER (WHERE installment_number > 1 AND first_confirmed_at IS NULL AND due_date < CURRENT_DATE) AS overdue_ar
  FROM base
)
SELECT CURRENT_DATE AS as_of_date,
  current_ar.current_ar,
  current_ar.overdue_ar,
  mtd.average_ar_mtd,
  mtd.credit_sales_mtd,
  mtd.ar_days_mtd / NULLIF(mtd.credit_sales_mtd, 0) AS standard_dso_mtd_days,
  contractual.contractual_dso_mtd_days,
  upfront.scheduled_down_payment_mtd,
  upfront.confirmed_down_payment_mtd,
  upfront.unconfirmed_down_payment_mtd,
  cash_days.scheduled_nmv_proxy_mtd,
  cash_days.cash_collection_days_mtd,
  mtd.elapsed_days
FROM current_ar CROSS JOIN mtd CROSS JOIN contractual CROSS JOIN upfront CROSS JOIN cash_days
""",
        "table",
        "Current AR excludes installment number 1. MTD Standard DSO = sum of daily closing AR / MTD scheduled credit sales (numbers greater than 1). Contractual DSO is weighted due-date days from installment creation. Cash collection days use all number >= 1 scheduled amounts as an NMV proxy; unpaid rows remain in the denominator, so current cohorts can understate the result. Amounts are in native database units.",
        24, 8,
    ),
    question(
        "BNPL - Monthly Standard vs Contractual DSO",
        f"""
WITH {BASE_CTES}, {DAILY_CTES},
actual_month AS (
  SELECT DATE_TRUNC('month', day)::date AS month_start, product_source,
    AVG(ar_balance) AS average_ar,
    SUM(ar_balance) AS ar_days,
    SUM(credit_sales) AS credit_sales,
    SUM(ar_balance) / NULLIF(SUM(credit_sales), 0) AS standard_dso_days
  FROM daily GROUP BY 1, 2
),
contractual_month AS (
  SELECT DATE_TRUNC('month', origination_date)::date AS month_start, product_source,
    SUM(scheduled_amount * (due_date - origination_date)) /
      NULLIF(SUM(scheduled_amount), 0) AS contractual_dso_days
  FROM base
  WHERE installment_number > 1 AND due_date IS NOT NULL
  GROUP BY 1, 2
)
SELECT actual_month.month_start, actual_month.product_source,
  actual_month.average_ar, actual_month.credit_sales,
  actual_month.standard_dso_days, contractual_month.contractual_dso_days,
  actual_month.standard_dso_days - contractual_month.contractual_dso_days AS dso_gap_days
FROM actual_month
LEFT JOIN contractual_month USING (month_start, product_source)
WHERE actual_month.month_start >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '18 months'
ORDER BY actual_month.month_start, actual_month.product_source
""",
        "line",
        "Monthly Standard DSO follows the PDF period method: average daily AR divided by average daily credit sales, equivalent to AR-days / credit sales. Contractual DSO is the schedule-weighted due-date horizon for installments originated that month. These are portfolio and schedule measures, respectively, and are not customer-level payment-delay metrics.",
        24, 10,
        {"graph.dimensions": ["month_start", "product_source"], "graph.metrics": ["standard_dso_days", "contractual_dso_days"]},
    ),
    question(
        "BNPL - Daily AR Balance",
        f"""
WITH {BASE_CTES}, {DAILY_CTES}
SELECT day, product_source, ar_balance, credit_sales
FROM daily
WHERE day >= CURRENT_DATE - INTERVAL '180 days'
ORDER BY day, product_source
""",
        "line",
        "Daily end-of-day receivables by source. AR increases on installment creation and decreases on the first confirmed linked gateway payment date. Installment number 1 is excluded. The chart displays the latest 180 days while opening balances include the full available history.",
        24, 9,
        {"graph.dimensions": ["day", "product_source"], "graph.metrics": ["ar_balance"]},
    ),
    question(
        "BNPL - Current AR Aging and DPD",
        f"""
WITH {BASE_CTES}
SELECT product_source,
  CASE
    WHEN due_date IS NULL THEN 'Missing due date'
    WHEN due_date > CURRENT_DATE THEN 'Not yet due'
    WHEN due_date = CURRENT_DATE THEN 'Due today'
    WHEN CURRENT_DATE - due_date <= 30 THEN '1-30 days overdue'
    WHEN CURRENT_DATE - due_date <= 60 THEN '31-60 days overdue'
    WHEN CURRENT_DATE - due_date <= 90 THEN '61-90 days overdue'
    ELSE 'Over 90 days overdue'
  END AS dpd_bucket,
  COUNT(*) AS installments,
  SUM(scheduled_amount) AS outstanding_ar,
  SUM(penalty) AS scheduled_penalty
FROM base
WHERE installment_number > 1 AND first_confirmed_at IS NULL
GROUP BY product_source, dpd_bucket
ORDER BY product_source, MIN(COALESCE(due_date, CURRENT_DATE))
""",
        "table",
        "Unpaid scheduled installments only (number > 1). DPD is max(0, today - due date); due-today and not-yet-due balances are shown separately. Outstanding AR is principal schedule amount; penalty is displayed separately and is not included in AR. Amounts are native database units.",
        12, 10,
    ),
    question(
        "BNPL - Confirmed Installment Payment Delay",
        f"""
WITH {BASE_CTES}, paid AS (
  SELECT product_source, due_date, first_confirmed_at::date - due_date AS delay_days
  FROM base
  WHERE installment_number > 1 AND first_confirmed_at IS NOT NULL AND due_date IS NOT NULL
)
SELECT product_source,
  COUNT(*) AS confirmed_installments,
  ROUND(AVG(delay_days)::numeric, 2) AS average_payment_delay_days,
  ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delay_days))::numeric, 2) AS median_payment_delay_days,
  COUNT(*) FILTER (WHERE delay_days <= 0) AS early_or_on_time,
  COUNT(*) FILTER (WHERE delay_days BETWEEN 1 AND 5) AS late_1_to_5_days,
  COUNT(*) FILTER (WHERE delay_days > 5) AS over_5_days_late,
  ROUND(100.0 * COUNT(*) FILTER (WHERE delay_days <= 0) / NULLIF(COUNT(*), 0), 2) AS early_or_on_time_pct
FROM paid GROUP BY product_source ORDER BY product_source
""",
        "table",
        "Actual payment delay for scheduled installments, computed from the first confirmed payment date minus due date. Negative values mean early payment. Confirmation is payment evidence only; the source tables do not establish refunds or reversals.",
        12, 10,
    ),
    question(
        "BNPL - Cash Collection Days on Scheduled NMV",
        f"""
WITH {BASE_CTES}
SELECT DATE_TRUNC('month', origination_date)::date AS month_start,
  product_source,
  SUM(scheduled_amount) FILTER (WHERE installment_number >= 1) AS scheduled_nmv_proxy,
  SUM(scheduled_amount) FILTER (WHERE installment_number >= 1 AND first_confirmed_at IS NOT NULL) AS confirmed_scheduled_amount,
  SUM(scheduled_amount * GREATEST(paid_date - origination_date, 0))
    FILTER (WHERE installment_number >= 1 AND first_confirmed_at IS NOT NULL)
    / NULLIF(SUM(scheduled_amount) FILTER (WHERE installment_number >= 1), 0) AS cash_collection_days
FROM base
WHERE installment_number >= 1
GROUP BY 1, 2
HAVING DATE_TRUNC('month', origination_date)::date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '18 months'
ORDER BY month_start, product_source
""",
        "line",
        "PDF weighted cash-collection-days measure using scheduled installment amounts as the NMV proxy: confirmed scheduled amount times elapsed days from installment creation, divided by total scheduled value. Number 1 contributes at day zero. This is not invoice-level NMV; unpaid rows remain in the denominator, so recent/incomplete cohorts can understate the measure. Amounts are native database units.",
        24, 9,
        {"graph.dimensions": ["month_start", "product_source"], "graph.metrics": ["cash_collection_days"]},
    ),
    question(
        "BNPL - Invoice-Time Payment Reconciliation",
        f"""
WITH {BASE_CTES}
SELECT DATE_TRUNC('month', origination_date)::date AS month_start,
  product_source,
  COUNT(*) FILTER (WHERE installment_number = 1) AS invoice_time_rows,
  SUM(scheduled_amount) FILTER (WHERE installment_number = 1) AS scheduled_down_payment,
  SUM(scheduled_amount) FILTER (WHERE installment_number = 1 AND first_confirmed_at IS NOT NULL) AS confirmed_down_payment,
  SUM(scheduled_amount) FILTER (WHERE installment_number = 1 AND first_confirmed_at IS NULL) AS unconfirmed_down_payment,
  COUNT(*) FILTER (WHERE installment_number = 1 AND first_confirmed_at IS NULL) AS unconfirmed_invoice_time_rows
FROM base
WHERE installment_number = 1
GROUP BY 1, 2
HAVING DATE_TRUNC('month', origination_date)::date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '18 months'
ORDER BY month_start, product_source
""",
        "bar",
        "Tracks number 1 as invoice-time/down-payment per the business rule. It is excluded from AR and DSO. A missing confirmed payment is surfaced as an exception rather than silently treated as collected. Amounts are native database units.",
        24, 9,
        {"graph.dimensions": ["month_start", "product_source"], "graph.metrics": ["scheduled_down_payment", "confirmed_down_payment"]},
    ),
]

POSITIONS = [
    (0, 0, 24, 8),
    (8, 0, 24, 10),
    (18, 0, 24, 9),
    (27, 0, 12, 10),
    (27, 12, 12, 10),
    (37, 0, 24, 9),
    (46, 0, 24, 9),
]

SOURCE_PARAMETER = {
    "id": "source",
    "name": "Product source",
    "slug": "source",
    "type": "string/=",
    "sectionId": "string",
    "default": None,
    "mappings": [],
}


def exact_search(client, model, name):
    result = client.call("GET", "/api/search?" + urlencode({"type": model, "q": name}))
    return next((item for item in result.get("data", []) if item.get("name") == name), None)


def save_question(client, spec):
    match = exact_search(client, "card", spec["name"])
    body = {
        "name": spec["name"],
        "type": "question",
        "display": spec["display"],
        "description": spec["description"],
        "dataset_query": {
            "database": DATABASE_ID,
            "type": "native",
            "native": {"query": spec["sql"], "template-tags": TEMPLATE_TAGS},
        },
        "visualization_settings": spec["visualization_settings"],
    }
    saved = client.call("PUT", f"/api/card/{int(match['id'])}", body) if match else client.call("POST", "/api/card", body)
    card_id = saved.get("id") or (match or {}).get("id")
    if not card_id:
        raise SystemExit(f"Metabase did not return a card id for {spec['name']}.")
    return int(card_id)


def main():
    if not load_env().get("METABASE_API_KEY"):
        raise SystemExit("Set METABASE_API_KEY in .env before running this script.")
    client = MetabaseClient()

    dashboard_match = exact_search(client, "dashboard", DASHBOARD_NAME)
    if dashboard_match:
        dashboard_id = int(dashboard_match["id"])
        dashboard = client.call("GET", f"/api/dashboard/{dashboard_id}")
        if dashboard.get("name") != DASHBOARD_NAME:
            raise SystemExit("The matching dashboard name could not be verified; stopping without changes.")
        cards = [{key: value for key, value in item.items() if key in {
            "id", "card_id", "row", "col", "size_x", "size_y", "parameter_mappings",
            "series", "visualization_settings", "dashboard_tab_id", "inline_parameters", "action_id"
        }} for item in dashboard.get("dashcards", [])]
        parameters = dashboard.get("parameters", [])
        if not any(p.get("id") == "source" for p in parameters):
            parameters.append(SOURCE_PARAMETER)
    else:
        dashboard = client.create_standard_dashboard(name=DASHBOARD_NAME, description=DASHBOARD_DESCRIPTION)
        dashboard_id = int(dashboard["id"])
        cards = []
        parameters = [SOURCE_PARAMETER]

    existing_ids = {item.get("card_id") for item in cards}
    existing_names = {(item.get("card") or {}).get("name") for item in cards}
    row_end = max((item.get("row", 0) + item.get("size_y", 0) for item in cards), default=0)
    added = []

    for index, spec in enumerate(QUESTIONS):
        card_id = save_question(client, spec)
        if card_id in existing_ids or spec["name"] in existing_names:
            continue
        row, col, width, height = POSITIONS[index]
        if cards:
            row = max(row, row_end)
        cards.append({
            "id": -(index + 1),
            "card_id": card_id,
            "row": row,
            "col": col,
            "size_x": width,
            "size_y": height,
            "parameter_mappings": [{
                "parameter_id": "source",
                "card_id": card_id,
                "target": ["variable", ["template-tag", "source"]],
            }],
            "series": [],
            "visualization_settings": spec["visualization_settings"],
        })
        existing_ids.add(card_id)
        existing_names.add(spec["name"])
        added.append({"id": card_id, "name": spec["name"]})
        row_end = max(row_end, row + height)

    updated = client.call("PUT", f"/api/dashboard/{dashboard_id}", {
        "parameters": parameters,
        "dashcards": cards,
    })

    print(f"Dashboard: {client.base_url}/dashboard/{dashboard_id}")
    for spec in QUESTIONS:
        match = exact_search(client, "card", spec["name"])
        if not match:
            raise SystemExit(f"Could not find saved question {spec['name']}.")
        card_id = int(match["id"])
        result = client.call("POST", f"/api/card/{card_id}/query", {"parameters": []})
        rows = result.get("data", {}).get("rows", [])
        print(f"{spec['name']}: {client.base_url}/question/{card_id} ({result.get('status')}, {len(rows)} rows)")
        if result.get("status") != "completed":
            raise SystemExit(f"Question failed validation: {spec['name']}")

    print(f"Dashboard cards: {len(updated.get('dashcards', cards))}; added this run: {len(added)}")


if __name__ == "__main__":
    main()
