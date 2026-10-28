#!/usr/bin/env python3
"""Create a Metabase question summarizing promo-code usage in shop orders."""

from metabase_agent import MetabaseClient, load_env, print_json


DATABASE_ID = int(load_env().get("METABASE_DATABASE_ID", "2"))
QUESTION_NAME = "Promo Code Usage in Shop Orders"

SQL = r"""
with order_usage as (
  select
    o.promo_code_id,
    count(*) filter (where o.deleted_at is null) as active_orders,
    count(distinct o.customer_id) filter (where o.deleted_at is null) as unique_customers,
    count(*) filter (where o.deleted_at is null and o.status = 'DONE') as completed_orders,
    count(*) filter (where o.deleted_at is null and i.status = 'CONFIRMED') as confirmed_invoice_orders,
    count(*) filter (where o.deleted_at is null and o.status = 'CANCELED_BY_CUSTOMER') as canceled_orders,
    count(*) filter (where o.deleted_at is null and o.status = 'EXPIRED') as expired_orders,
    count(*) filter (where o.deleted_at is not null) as deleted_orders,
    min(o.created_at) filter (where o.deleted_at is null) as first_order_at,
    max(o.created_at) filter (where o.deleted_at is null) as last_order_at,
    coalesce(sum(
      coalesce(o.soupop_promo_code_discount_amount, 0)
      + coalesce(o.auto_service_promo_code_discount_amount, 0)
    ) filter (where o.deleted_at is null), 0) as applied_discount_total,
    coalesce(sum(
      coalesce(o.soupop_promo_code_discount_amount, 0)
      + coalesce(o.auto_service_promo_code_discount_amount, 0)
    ) filter (where o.deleted_at is null and i.status = 'CONFIRMED'), 0) as confirmed_invoice_discount_total
  from shop_orders o
  left join invoices i on i.id = o.invoice_id
  where o.promo_code_id is not null
  group by o.promo_code_id
),
assignments as (
  select promo_code_id, count(distinct customer_id) as assigned_customers
  from shop_promo_code_customers
  group by promo_code_id
),
rules as (
  select
    promo_code_id,
    count(*) as rule_count,
    count(distinct auto_service_id) as eligible_auto_services,
    count(distinct service_type_id) as eligible_service_types
  from shop_promo_code_rules
  group by promo_code_id
),
gamification as (
  select
    promo_code_id,
    count(*) as gamification_rule_count,
    count(distinct auto_service_id) as gamification_auto_services
  from shop_promo_code_gamifications
  group by promo_code_id
)
select
  p.code as promo_code,
  p.created_at as code_created_at,
  p.soupop_percent,
  p.auto_service_percent,
  p.soupop_amount,
  p.auto_service_amount,
  p.min_order_amount,
  p.max_amount,
  p.duration_days,
  p.is_customer_assignment_required_for_usage,
  coalesce(a.assigned_customers, 0) as assigned_customers,
  coalesce(r.rule_count, 0) as promo_rule_count,
  coalesce(r.eligible_auto_services, 0) as eligible_auto_services,
  coalesce(r.eligible_service_types, 0) as eligible_service_types,
  coalesce(g.gamification_rule_count, 0) as gamification_rule_count,
  coalesce(u.active_orders, 0) as orders_with_code,
  coalesce(u.unique_customers, 0) as unique_customers,
  coalesce(u.completed_orders, 0) as completed_orders,
  coalesce(u.confirmed_invoice_orders, 0) as confirmed_invoice_orders,
  coalesce(u.canceled_orders, 0) as canceled_orders,
  coalesce(u.expired_orders, 0) as expired_orders,
  coalesce(u.deleted_orders, 0) as deleted_orders,
  coalesce(u.applied_discount_total, 0) as applied_discount_total,
  coalesce(u.confirmed_invoice_discount_total, 0) as confirmed_invoice_discount_total,
  u.first_order_at,
  u.last_order_at
from shop_promo_codes p
left join order_usage u on u.promo_code_id = p.code
left join assignments a on a.promo_code_id = p.code
left join rules r on r.promo_code_id = p.code
left join gamification g on g.promo_code_id = p.code
order by orders_with_code desc, p.code;
"""


def main():
    result = MetabaseClient().create_native_card(
        DATABASE_ID,
        QUESTION_NAME,
        SQL,
        display="table",
        description=(
            "One row per configured promo code. Usage is counted from shop_orders.promo_code_id; "
            "order and invoice outcomes are shown separately. Discount totals use the applied "
            "amounts stored on shop_orders. Assignment, eligibility-rule, and gamification "
            "tables are pre-aggregated to avoid multiplying order counts. Amounts are in the "
            "database's stored currency units."
        ),
    )
    print_json(result)
    question_id = result.get("id")
    if question_id:
        print(f"Question link: {MetabaseClient().base_url}/question/{question_id}")


if __name__ == "__main__":
    main()
