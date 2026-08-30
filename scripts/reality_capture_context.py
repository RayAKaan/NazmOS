import sys, json, httpx, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = 'http://localhost:8000'
EMAIL = 'reality-core@example.com'
PASSWORD = 'Reality!2026-Strong'
BID = '50e23176-9b8f-4974-9490-c4228c690f28'

def login():
    r = httpx.post(BASE + '/api/v1/auth/login', json={'email': EMAIL, 'password': PASSWORD})
    r.raise_for_status()
    return {'Authorization': 'Bearer ' + r.json()['access_token']}

h = login()

# business context (products/suppliers/branches/constraints)
j = httpx.get(BASE + f'/api/v1/intelligence/business-context?business_id={BID}&max_products=100', headers=h).json()

out = {
    'business': j.get('business'),
    'constraints': j.get('constraints'),
    'source_period': j.get('source_period'),
    'products': j.get('products'),
    'suppliers': j.get('suppliers'),
    'branches': j.get('branches'),
    'recent_actions': j.get('recent_actions'),
    'outcomes': j.get('outcomes'),
    'captured_at': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
}

with open('reality_test_output/business_context_full.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, indent=2, default=str)

print('products', len(out['products']), 'suppliers', len(out['suppliers']), 'branches', len(out['branches']))
print('outcomes', len(out['outcomes']), 'recent_actions', len(out['recent_actions']))
print('constraints', json.dumps(out['constraints'], default=str)[:500])
