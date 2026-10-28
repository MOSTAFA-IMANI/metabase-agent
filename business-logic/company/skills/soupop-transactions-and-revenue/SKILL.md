---
name: soupop-transactions-and-revenue
description: Explains SouPop's transaction lifecycle, invoice recording, contractual settlement, and vendor commission revenue.
---

# SouPop Transactions and Revenue

## Purpose

Use this skill to analyze the transaction core and distinguish transaction activity from actual revenue.

## Transaction lifecycle

1. The customer accesses BNPL credit or a loan through SouPop.
2. The customer visits a contracted automotive service vendor.
3. The vendor delivers the automotive service.
4. The purchase or service transaction is recorded and an invoice is issued.
5. Settlement takes place according to the applicable contractual mechanism.
6. SouPop earns commission from the vendor for the transaction.

## Revenue model

The primary revenue model stated in the source is a percentage-based commission charged to the vendor on automotive service transactions completed using SouPop credit.

## Important distinctions

- **Allocated credit:** Credit made available to a customer.
- **Transaction value:** The value of a purchase or service transaction.
- **Commission revenue:** The commission SouPop earns from the vendor.
- **Settlement:** The process governed by the relevant contractual arrangement.

These concepts are related but are not interchangeable.

## Analysis guidelines

When reviewing transaction performance:

- Count successful transactions separately from registrations and credit allocations.
- Analyze transaction count and transaction value separately.
- Distinguish gross transaction value from SouPop's commission revenue.
- Confirm the applicable commission rules before calculating revenue.
- Confirm transaction status definitions and settlement rules before designing financial reports.

## Guardrails

The source does not specify exact commission rates, refunds, cancellations, taxes, payment timing, settlement schedules, or accounting recognition rules. Do not invent these details or assume that transaction value equals SouPop revenue.

Request the relevant contract, financial rules, or data definitions when an exact calculation is required.
