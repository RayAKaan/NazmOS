# NazmOS Controlled Pilot SOP

## Goal

Prove this loop with real merchant files:

```txt
Sales + inventory upload -> Money Audit -> owner approval -> completed action -> Money Recovered
```

## Merchant onboarding

1. Explain the offer in one sentence:
   "Send two files. NazmOS finds cash trapped in your store."
2. Ask for:
   - last 30-90 days sales export
   - current inventory export
3. Accept messy CSV/XLS/XLSX. Do not force templates on first contact.
4. Confirm column mapping in NazmOS.
5. Generate Money Audit.
6. Founder reviews audit before sending.

## Allowed Recovery Match categories

Allowed for v1 only if healthy shelf-life and founder-reviewed:

```txt
ambient packaged goods
water/beverages not cold-chain
dry groceries
packaged dates/sweets
household non-regulated goods
```

Excluded:

```txt
expired/near-expiry
cold-chain/chilled/frozen
medicine
baby formula
fresh dairy
meat
cosmetics
regulated categories
```

## WhatsApp approval

Manual first:

1. Copy WhatsApp summary from `/money-audit`.
2. Send to merchant manually.
3. If merchant approves, mark action approved in NazmOS.
4. When done, mark completed and enter recovered/protected SAR.

## Recovery Match v1

Rules:

```txt
no escrow
no payment handling
no delivery promise
no invoice generation
no automatic contact reveal
both sides approve first
founder review before reveal
```

## Production pilot exit criteria

A pilot is successful when one merchant reaches:

```txt
1 sales file imported
1 inventory file imported
1 Money Audit generated
1 action approved
1 action completed
Money Recovered > 0
```
