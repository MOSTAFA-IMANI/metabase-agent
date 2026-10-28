#!/usr/bin/env python3
"""Read aggregate, non-PII inputs for the BNPL cash-flow model."""

import json
from pathlib import Path

from metabase_agent import MetabaseClient


AS_OF = "2026-10-01 00:00:00+03:30"
# Written to data/ (git-ignored); scripts-js/build_cashflow_projection.mjs reads it from there.
OUT = Path(__file__).resolve().parents[1] / "data" / "soupop_cashflow_source.json"

BASE = """
WITH eligible_invoices AS (
    SELECT i.id AS invoice_id,
           i.created_at AS invoice_created_at,
           DATE_TRUNC('month', i.created_at AT TIME ZONE 'Asia/Tehran')::date AS invoice_month,
           i.amount AS invoice_amount,
           i.customer_id
    FROM public.invoices i
    WHERE i.status = 'CONFIRMED'
      AND (i.customer_id IS NULL OR i.customer_id NOT IN (7964, 13110))
),
installment_payments AS (
    SELECT ci.id AS installment_id,
           ci.number AS installment_number,
           ci.amount AS installment_amount,
           ci.due_date,
           ci.payment_id,
           p.transaction_id AS payment_transaction_id,
           p.confirmed_at,
           p.created_at AS payment_created_at
    FROM public.bnpl_credit_installments ci
    LEFT JOIN public.bnpl_gateway_payments p
      ON p.id = ci.payment_id
),
direct_payment_invoice AS (
    SELECT ip.installment_id,
           it.invoice_id
    FROM installment_payments ip
    JOIN public.bnpl_invoice_transactions it
      ON it.id = ip.payment_transaction_id
    JOIN eligible_invoices ei
      ON ei.invoice_id = it.invoice_id
),
unique_item_invoice AS (
    SELECT iti.installment_id,
           MIN(it.invoice_id) AS invoice_id
    FROM public.bnpl_credit_installment_transaction_items iti
    JOIN public.bnpl_invoice_transactions it
      ON it.id = iti.transaction_id
    JOIN eligible_invoices ei
      ON ei.invoice_id = it.invoice_id
    GROUP BY iti.installment_id
    HAVING COUNT(DISTINCT it.invoice_id) = 1
),
invoice_installments AS (
    SELECT ei.invoice_id,
           ei.invoice_created_at,
           ei.invoice_month,
           ei.invoice_amount,
           ip.*
    FROM installment_payments ip
    LEFT JOIN direct_payment_invoice dpi
      ON dpi.installment_id = ip.installment_id
    LEFT JOIN unique_item_invoice uii
      ON uii.installment_id = ip.installment_id
    JOIN eligible_invoices ei
      ON ei.invoice_id = COALESCE(dpi.invoice_id, uii.invoice_id)
)
"""

QUERIES = {
    "link_coverage": BASE + """
SELECT
    (SELECT COUNT(*) FROM public.bnpl_credit_installment_transaction_items) AS mapping_rows,
    (SELECT COUNT(DISTINCT installment_id) FROM public.bnpl_credit_installment_transaction_items) AS distinct_installments,
    (SELECT COUNT(DISTINCT invoice_id) FROM invoice_installments) AS invoices_with_installments,
    (SELECT COUNT(*) FROM invoice_installments) AS modeled_installments,
    (SELECT COUNT(*) FROM invoice_installments WHERE payment_id IS NULL) AS no_gateway_payment,
    (SELECT COUNT(*) FROM invoice_installments WHERE confirmed_at IS NOT NULL
      AND confirmed_at < TIMESTAMPTZ '2026-10-01 00:00:00+03:30') AS confirmed_to_cutoff
""",
    "mapping_quality": BASE + """
, installment_invoice_counts AS (
    SELECT iti.installment_id,
           COUNT(*) AS mapping_rows,
           COUNT(DISTINCT it.invoice_id) AS invoice_count
    FROM public.bnpl_credit_installment_transaction_items iti
    JOIN public.bnpl_invoice_transactions it
      ON it.id = iti.transaction_id
    GROUP BY 1
)
SELECT COUNT(*) AS installments,
       COUNT(*) FILTER (WHERE mapping_rows > 1) AS installments_with_duplicate_rows,
       COUNT(*) FILTER (WHERE invoice_count > 1) AS installments_linked_to_multiple_invoices,
       MAX(invoice_count) AS maximum_invoices_per_installment,
       (SELECT COUNT(*) FROM direct_payment_invoice) AS resolved_by_direct_payment,
       (SELECT COUNT(*) FROM unique_item_invoice) AS resolved_by_unique_item_link,
       (SELECT COUNT(*) FROM invoice_installments) AS resolved_for_model
FROM installment_invoice_counts
""",
    "monthly_actuals": BASE + """
, monthly_invoices AS (
    SELECT ei.invoice_month AS month,
           SUM(ei.invoice_amount) AS nmv
    FROM eligible_invoices ei
    WHERE ei.invoice_month <= DATE '2026-09-01'
    GROUP BY 1
),
monthly_cash_out AS (
    SELECT DATE_TRUNC('month', i.created_at AT TIME ZONE 'Asia/Tehran')::date AS month,
           SUM(i.amount - (COALESCE(ic.percent, 0)::numeric * i.amount / 100.0)) AS merchant_cash_out
    FROM public.invoices i
    LEFT JOIN public.invoice_commissions ic ON ic.invoice_id = i.id
    WHERE i.status = 'CONFIRMED'
      AND (i.customer_id IS NULL OR i.customer_id NOT IN (7964, 13110))
      AND i.created_at < TIMESTAMPTZ '2026-10-01 00:00:00+03:30'
    GROUP BY 1
),
monthly_cash_in AS (
    SELECT DATE_TRUNC('month', confirmed_at AT TIME ZONE 'Asia/Tehran')::date AS month,
           SUM(installment_amount) AS customer_cash_in,
           SUM(installment_amount) FILTER (WHERE installment_number = 1) AS first_installment_cash_in,
           SUM(installment_amount) FILTER (WHERE installment_number > 1) AS later_installment_cash_in
    FROM invoice_installments
    WHERE confirmed_at IS NOT NULL
      AND confirmed_at < TIMESTAMPTZ '2026-10-01 00:00:00+03:30'
    GROUP BY 1
)
SELECT COALESCE(mi.month, mco.month, mci.month) AS month,
       COALESCE(mi.nmv, 0) AS nmv,
       COALESCE(mci.customer_cash_in, 0) AS customer_cash_in,
       COALESCE(mci.first_installment_cash_in, 0) AS first_installment_cash_in,
       COALESCE(mci.later_installment_cash_in, 0) AS later_installment_cash_in,
       COALESCE(mco.merchant_cash_out, 0) AS merchant_cash_out,
       COALESCE(mci.customer_cash_in, 0) - COALESCE(mco.merchant_cash_out, 0) AS net_cash_flow
FROM monthly_invoices mi
FULL JOIN monthly_cash_out mco ON mco.month = mi.month
FULL JOIN monthly_cash_in mci ON mci.month = COALESCE(mi.month, mco.month)
WHERE COALESCE(mi.month, mco.month, mci.month) >= DATE '2025-01-01'
ORDER BY 1
""",
    "cohort_schedule": BASE + """
SELECT invoice_month,
       installment_number,
       COUNT(*) AS installments,
       SUM(installment_amount) AS installment_generated,
       AVG(due_date - (invoice_created_at AT TIME ZONE 'Asia/Tehran')::date) AS average_due_days,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY due_date - (invoice_created_at AT TIME ZONE 'Asia/Tehran')::date) AS median_due_days,
       SUM(installment_amount) FILTER (
           WHERE confirmed_at IS NOT NULL
             AND confirmed_at < TIMESTAMPTZ '2026-10-01 00:00:00+03:30'
       ) AS confirmed_through_cutoff
FROM invoice_installments
WHERE invoice_month BETWEEN DATE '2025-01-01' AND DATE '2026-06-01'
GROUP BY 1, 2
ORDER BY 1, 2
""",
    "installment_profile": BASE + """
, mature_invoices AS (
    SELECT DISTINCT invoice_id, invoice_amount
    FROM invoice_installments
    WHERE invoice_month BETWEEN DATE '2025-10-01' AND DATE '2026-03-01'
),
profile AS (
    SELECT ii.installment_number,
           COUNT(*) AS installments,
           SUM(ii.installment_amount) AS installment_generated,
           AVG(ii.due_date - (ii.invoice_created_at AT TIME ZONE 'Asia/Tehran')::date) AS average_due_days,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ii.due_date - (ii.invoice_created_at AT TIME ZONE 'Asia/Tehran')::date) AS median_due_days
    FROM invoice_installments ii
    WHERE ii.invoice_month BETWEEN DATE '2025-10-01' AND DATE '2026-03-01'
    GROUP BY 1
),
counts AS (
    SELECT ii.invoice_id, MAX(ii.installment_number) AS installment_count
    FROM invoice_installments ii
    WHERE ii.invoice_month BETWEEN DATE '2025-10-01' AND DATE '2026-03-01'
    GROUP BY 1
)
SELECT p.installment_number,
       p.installments,
       p.installment_generated,
       p.installment_generated / NULLIF((SELECT SUM(invoice_amount) FROM mature_invoices), 0) AS amount_share_of_nmv,
       p.average_due_days,
       p.median_due_days,
       (SELECT AVG(installment_count::numeric) FROM counts) AS average_installment_count,
       (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY installment_count) FROM counts) AS median_installment_count
FROM profile p
ORDER BY 1
""",
    "term_mix_by_invoice_month": BASE + """
, invoice_term AS (
    SELECT invoice_id,
           MIN(invoice_month) AS invoice_month,
           MIN(invoice_amount) AS invoice_amount,
           MAX(installment_number) AS installment_count,
           SUM(installment_amount) AS linked_installment_amount
    FROM invoice_installments
    WHERE invoice_month BETWEEN DATE '2026-06-01' AND DATE '2026-09-01'
    GROUP BY 1
),
cohort_nmv AS (
    SELECT invoice_month,
           SUM(invoice_amount) AS total_nmv,
           COUNT(*) AS total_invoices
    FROM eligible_invoices
    WHERE invoice_month BETWEEN DATE '2026-06-01' AND DATE '2026-09-01'
    GROUP BY 1
),
term_nmv AS (
    SELECT invoice_month,
           SUM(invoice_amount) AS linked_nmv,
           SUM(invoice_amount) FILTER (WHERE installment_count = 4) AS four_installment_nmv,
           SUM(invoice_amount) FILTER (WHERE installment_count <> 4) AS loan_nmv,
           SUM(invoice_amount) FILTER (WHERE installment_count = 6) AS six_installment_nmv,
           SUM(invoice_amount) FILTER (WHERE installment_count <= 3) AS below_four_installment_nmv,
           COUNT(*) AS linked_invoices,
           COUNT(*) FILTER (WHERE installment_count = 4) AS four_installment_invoices,
           COUNT(*) FILTER (WHERE installment_count <> 4) AS loan_invoices,
           COUNT(*) FILTER (WHERE installment_count = 6) AS six_installment_invoices
    FROM invoice_term
    GROUP BY 1
)
SELECT cn.invoice_month,
       cn.total_nmv,
       cn.total_invoices,
       COALESCE(tn.linked_nmv, 0) AS linked_nmv,
       COALESCE(tn.four_installment_nmv, 0) AS four_installment_nmv,
       COALESCE(tn.loan_nmv, 0) AS loan_nmv,
       COALESCE(tn.six_installment_nmv, 0) AS six_installment_nmv,
       COALESCE(tn.below_four_installment_nmv, 0) AS below_four_installment_nmv,
       COALESCE(tn.four_installment_nmv, 0) / NULLIF(COALESCE(tn.four_installment_nmv, 0) + COALESCE(tn.loan_nmv, 0), 0) AS four_share_of_bnpl_and_loan_nmv,
       COALESCE(tn.loan_nmv, 0) / NULLIF(COALESCE(tn.four_installment_nmv, 0) + COALESCE(tn.loan_nmv, 0), 0) AS loan_share_of_bnpl_and_loan_nmv,
       COALESCE(tn.four_installment_nmv, 0) / NULLIF(cn.total_nmv, 0) AS four_share_of_total_nmv,
       COALESCE(tn.loan_nmv, 0) / NULLIF(cn.total_nmv, 0) AS loan_share_of_total_nmv,
       COALESCE(tn.six_installment_nmv, 0) / NULLIF(cn.total_nmv, 0) AS six_share_of_total_nmv,
       COALESCE(tn.linked_nmv, 0) / NULLIF(cn.total_nmv, 0) AS linkage_coverage_by_nmv,
       COALESCE(tn.four_installment_invoices, 0) AS four_installment_invoices,
       COALESCE(tn.loan_invoices, 0) AS loan_invoices,
       COALESCE(tn.six_installment_invoices, 0) AS six_installment_invoices
FROM cohort_nmv cn
LEFT JOIN term_nmv tn ON tn.invoice_month = cn.invoice_month
ORDER BY 1
""",
    "term_installment_profiles": BASE + """
, invoice_term AS (
    SELECT invoice_id,
           MIN(invoice_amount) AS invoice_amount,
           MAX(installment_number) AS installment_count
    FROM invoice_installments
    WHERE invoice_month BETWEEN DATE '2026-06-01' AND DATE '2026-09-01'
    GROUP BY 1
),
term_nmv AS (
    SELECT CASE WHEN installment_count = 4 THEN 'BNPL - 4 installments'
                ELSE 'Loan - non-4 installment terms' END AS product_model,
           SUM(invoice_amount) AS model_nmv,
           COUNT(*) AS model_invoices
    FROM invoice_term
    WHERE installment_count IS NOT NULL
    GROUP BY 1
)
SELECT tn.product_model,
       ii.installment_number,
       COUNT(*) AS installments,
       SUM(ii.installment_amount) AS installment_generated,
       SUM(ii.installment_amount) / NULLIF(tn.model_nmv, 0) AS raw_amount_share_of_model_nmv,
       AVG(ii.due_date - (ii.invoice_created_at AT TIME ZONE 'Asia/Tehran')::date) AS average_due_days,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ii.due_date - (ii.invoice_created_at AT TIME ZONE 'Asia/Tehran')::date) AS median_due_days,
       tn.model_nmv,
       tn.model_invoices
FROM invoice_installments ii
JOIN invoice_term it ON it.invoice_id = ii.invoice_id
JOIN term_nmv tn ON tn.product_model = CASE WHEN it.installment_count = 4 THEN 'BNPL - 4 installments'
                                            ELSE 'Loan - non-4 installment terms' END
WHERE it.installment_count IS NOT NULL
GROUP BY tn.product_model, ii.installment_number, tn.model_nmv, tn.model_invoices
ORDER BY 1, 2
""",
    "loan_term_distribution": BASE + """
, invoice_term AS (
    SELECT invoice_id,
           MIN(invoice_month) AS invoice_month,
           MIN(invoice_amount) AS invoice_amount,
           MAX(installment_number) AS installment_count
    FROM invoice_installments
    WHERE invoice_month BETWEEN DATE '2026-06-01' AND DATE '2026-09-01'
    GROUP BY 1
),
monthly_linked_nmv AS (
    SELECT invoice_month, SUM(invoice_amount) AS linked_nmv
    FROM invoice_term
    GROUP BY 1
)
SELECT it.invoice_month,
       it.installment_count,
       COUNT(*) AS invoices,
       SUM(it.invoice_amount) AS nmv,
       SUM(it.invoice_amount) / NULLIF(mln.linked_nmv, 0) AS share_of_linked_nmv
FROM invoice_term it
JOIN monthly_linked_nmv mln ON mln.invoice_month = it.invoice_month
GROUP BY it.invoice_month, it.installment_count, mln.linked_nmv
ORDER BY 1, 2
""",
    "collection_curve": BASE + """
, due_base AS (
    SELECT *,
           (EXTRACT(YEAR FROM due_date)::int * 12 + EXTRACT(MONTH FROM due_date)::int) AS due_period,
           CASE WHEN confirmed_at IS NULL OR confirmed_at >= TIMESTAMPTZ '2026-10-01 00:00:00+03:30' THEN NULL
                ELSE EXTRACT(YEAR FROM (confirmed_at AT TIME ZONE 'Asia/Tehran'))::int * 12
                   + EXTRACT(MONTH FROM (confirmed_at AT TIME ZONE 'Asia/Tehran'))::int
           END AS confirmed_period
    FROM invoice_installments
    WHERE installment_number > 1
      AND due_date BETWEEN DATE '2025-10-01' AND DATE '2026-06-30'
)
SELECT CASE
           WHEN confirmed_period IS NULL THEN 'Unpaid as of cutoff'
           WHEN confirmed_period <= due_period THEN 'Due month or earlier'
           WHEN confirmed_period = due_period + 1 THEN '+1 month'
           WHEN confirmed_period = due_period + 2 THEN '+2 months'
           WHEN confirmed_period = due_period + 3 THEN '+3 months'
           ELSE '+4 months or later'
       END AS collection_bucket,
       COUNT(*) AS installments,
       SUM(installment_amount) AS amount,
       SUM(installment_amount) / NULLIF(SUM(SUM(installment_amount)) OVER (), 0) AS amount_share
FROM due_base
GROUP BY 1
ORDER BY CASE
  WHEN CASE
           WHEN confirmed_period IS NULL THEN 'Unpaid as of cutoff'
           WHEN confirmed_period <= due_period THEN 'Due month or earlier'
           WHEN confirmed_period = due_period + 1 THEN '+1 month'
           WHEN confirmed_period = due_period + 2 THEN '+2 months'
           WHEN confirmed_period = due_period + 3 THEN '+3 months'
           ELSE '+4 months or later'
       END = 'Due month or earlier' THEN 1
  WHEN CASE
           WHEN confirmed_period IS NULL THEN 'Unpaid as of cutoff'
           WHEN confirmed_period <= due_period THEN 'Due month or earlier'
           WHEN confirmed_period = due_period + 1 THEN '+1 month'
           WHEN confirmed_period = due_period + 2 THEN '+2 months'
           WHEN confirmed_period = due_period + 3 THEN '+3 months'
           ELSE '+4 months or later'
       END = '+1 month' THEN 2
  WHEN CASE
           WHEN confirmed_period IS NULL THEN 'Unpaid as of cutoff'
           WHEN confirmed_period <= due_period THEN 'Due month or earlier'
           WHEN confirmed_period = due_period + 1 THEN '+1 month'
           WHEN confirmed_period = due_period + 2 THEN '+2 months'
           WHEN confirmed_period = due_period + 3 THEN '+3 months'
           ELSE '+4 months or later'
       END = '+2 months' THEN 3
  WHEN CASE
           WHEN confirmed_period IS NULL THEN 'Unpaid as of cutoff'
           WHEN confirmed_period <= due_period THEN 'Due month or earlier'
           WHEN confirmed_period = due_period + 1 THEN '+1 month'
           WHEN confirmed_period = due_period + 2 THEN '+2 months'
           WHEN confirmed_period = due_period + 3 THEN '+3 months'
           ELSE '+4 months or later'
       END = '+3 months' THEN 4
  WHEN CASE
           WHEN confirmed_period IS NULL THEN 'Unpaid as of cutoff'
           WHEN confirmed_period <= due_period THEN 'Due month or earlier'
           WHEN confirmed_period = due_period + 1 THEN '+1 month'
           WHEN confirmed_period = due_period + 2 THEN '+2 months'
           WHEN confirmed_period = due_period + 3 THEN '+3 months'
           ELSE '+4 months or later'
       END = '+4 months or later' THEN 5
  ELSE 6 END
""",
    "cohort_actual_cash": BASE + """
, cohort_base AS (
    SELECT invoice_month,
           installment_amount,
           CASE WHEN confirmed_at IS NULL OR confirmed_at >= TIMESTAMPTZ '2026-10-01 00:00:00+03:30' THEN NULL
                ELSE (EXTRACT(YEAR FROM (confirmed_at AT TIME ZONE 'Asia/Tehran'))::int * 12
                      + EXTRACT(MONTH FROM (confirmed_at AT TIME ZONE 'Asia/Tehran'))::int)
                     - (EXTRACT(YEAR FROM invoice_month)::int * 12 + EXTRACT(MONTH FROM invoice_month)::int)
           END AS cash_offset
    FROM invoice_installments
    WHERE invoice_month BETWEEN DATE '2025-10-01' AND DATE '2026-06-01'
)
SELECT invoice_month,
       COUNT(*) AS installments,
       SUM(installment_amount) AS installment_generated,
       SUM(installment_amount) FILTER (WHERE cash_offset <= 0) AS same_month_or_earlier,
       SUM(installment_amount) FILTER (WHERE cash_offset = 1) AS plus_1_month,
       SUM(installment_amount) FILTER (WHERE cash_offset = 2) AS plus_2_month,
       SUM(installment_amount) FILTER (WHERE cash_offset >= 3) AS later,
       SUM(installment_amount) FILTER (WHERE cash_offset IS NULL) AS unpaid_as_of_cutoff
FROM cohort_base
GROUP BY 1
ORDER BY 1
""",
    "opening_ar": BASE + """
SELECT CASE
           WHEN due_date < DATE '2026-09-01' THEN 'Overdue before Sep-26'
           WHEN due_date < DATE '2026-10-01' THEN 'Due in Sep-26'
           WHEN due_date < DATE '2026-11-01' THEN 'Due in Oct-26'
           WHEN due_date < DATE '2026-12-01' THEN 'Due in Nov-26'
           WHEN due_date < DATE '2027-01-01' THEN 'Due in Dec-26'
           WHEN due_date < DATE '2027-02-01' THEN 'Due in Jan-27'
           WHEN due_date < DATE '2027-03-01' THEN 'Due in Feb-27'
           WHEN due_date < DATE '2027-04-01' THEN 'Due in Mar-27'
           ELSE 'Due after Mar-27'
       END AS due_bucket,
       COUNT(*) AS installments,
       SUM(installment_amount) AS outstanding_amount
FROM invoice_installments
WHERE (confirmed_at IS NULL OR confirmed_at >= TIMESTAMPTZ '2026-10-01 00:00:00+03:30')
  AND invoice_month <= DATE '2026-09-01'
GROUP BY 1
ORDER BY MIN(due_date)
""",
    "merchant_share_ratio": """
SELECT DATE_TRUNC('month', i.created_at AT TIME ZONE 'Asia/Tehran')::date AS month,
       SUM(i.amount) AS nmv,
       SUM(i.amount - (COALESCE(ic.percent, 0)::numeric * i.amount / 100.0)) AS merchant_cash_out,
       SUM(i.amount - (COALESCE(ic.percent, 0)::numeric * i.amount / 100.0)) / NULLIF(SUM(i.amount), 0) AS cash_out_ratio
FROM public.invoices i
LEFT JOIN public.invoice_commissions ic ON ic.invoice_id = i.id
WHERE i.status = 'CONFIRMED'
  AND (i.customer_id IS NULL OR i.customer_id NOT IN (7964, 13110))
  AND i.created_at >= TIMESTAMPTZ '2026-04-01 00:00:00+03:30'
  AND i.created_at < TIMESTAMPTZ '2026-10-01 00:00:00+03:30'
GROUP BY 1
ORDER BY 1
""",
}


def rows(response):
    return response["data"]["rows"]


def main():
    client = MetabaseClient()
    result = {name: rows(client.execute_sql(2, query)) for name, query in QUERIES.items()}
    result["metabase_question_287_nmv"] = client.call(
        "POST", "/api/card/287/query", {"parameters": []}
    )["data"]["rows"]
    result["metabase_question_280_ar"] = client.call(
        "POST", "/api/card/280/query", {"parameters": []}
    )["data"]["rows"]
    result["metabase_question_290_cashflow"] = client.call(
        "POST", "/api/card/290/query", {"parameters": []}
    )["data"]["rows"]
    result["as_of"] = AS_OF
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
