import sys, asyncio, csv
sys.path.insert(0, r'H:\NAZMOS\nazmos\backend')
from app.services.evidence_package import ItemEvidence, BusinessContext
from app.services.ab_decision_framework import deterministic_decision_for_item
from app.services.business_context import BusinessContextEngine
from app.services.ai_challenge import challenge_deterministic, select_final_decision_v11, ChallengeStatus
from app.services.llm_orchestrator import LLMOrchestrator
from datetime import date

orchestrator = LLMOrchestrator()
print('use_mock:', orchestrator.use_mock)
print('providers:', orchestrator._real_providers())

async def test():
    async def mock_caller(sp, up):
        return '{"status": "NO_CHALLENGE", "reason": "test"}'

    ctx_engine = BusinessContextEngine()
    business_ctx = BusinessContext(
        business_id='al_noor_supermarket',
        business_type='supermarket',
        total_inventory_value_sar=50000.0,
        total_capital_at_risk_sar=50000.0,
        total_recoverable_high_sar=30000.0,
    )
    virtual_date = date(2026, 8, 26)

    with open(r'H:\NAZMOS\nazmos\sample_data\v11\al_noor_supermarket_inventory_d0.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)[:3]

    for row in rows:
        ev_dict = {
            'sku': row['SKU'], 'product_name': row['Product'],
            'classification': row['Category'],
            'current_stock': float(row['Current Stock']),
            'cost_price_sar': float(row['Cost Price SAR']),
            'sell_price_sar': float(row['Shelf Price SAR']),
            'inventory_value_sar': float(row['Current Stock']) * float(row['Cost Price SAR']),
            'daily_velocity': float(row['Normal Velocity']),
            'recent_velocity_per_day': float(row['Normal Velocity']),
            'prior_velocity_per_day': float(row['Normal Velocity']) * 0.9,
            'days_of_supply': float(row['Current Stock']) / max(float(row['Normal Velocity']), 0.01),
            'days_since_last_sale': 7, 'inventory_age_days': 30,
            'margin_pct': (float(row['Shelf Price SAR']) - float(row['Cost Price SAR'])) / max(float(row['Shelf Price SAR']), 0.01),
            'supplier_name': row['Supplier'],
        }
        ev = ItemEvidence(**{k: v for k, v in ev_dict.items() if k in ItemEvidence.__dataclass_fields__})
        det = deterministic_decision_for_item(ev)
        print(f'{ev.sku}: det={det}', end='')

        ctx = await ctx_engine.build_context(ev, business_ctx, virtual_date)
        challenge = await challenge_deterministic(ctx, mock_caller)
        final, source = select_final_decision_v11(det, challenge, ctx)
        print(f' -> final={final}, src={source}, challenge={challenge.status.value}')

asyncio.run(test())
print('Experiment dry-run OK')
