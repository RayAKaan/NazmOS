import sys, time, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

BASE = 'http://localhost:3000'
EMAIL = 'reality-core@example.com'
PASSWORD = 'Reality!2026-Strong'
SHOT_DIR = 'reality_test_output/shots'

def main():
    import os
    os.makedirs(SHOT_DIR, exist_ok=True)
    report = {'steps': []}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={'width': 1440, 'height': 900})
        pg = ctx.new_page()
        pg.goto(BASE + '/login', timeout=40000)
        pg.wait_for_load_state('networkidle')
        # Fill login form
        pg.fill('input[name="email"]', EMAIL)
        pg.fill('input[name="password"]', PASSWORD)
        pg.screenshot(path=f'{SHOT_DIR}/01_login_filled.png')
        # Submit
        pg.click('button[type="submit"]')
        pg.wait_for_url('**/dashboard', timeout=40000)
        time.sleep(3)
        pg.screenshot(path=f'{SHOT_DIR}/02_dashboard.png')
        report['steps'].append({'step': 'login', 'url': pg.url, 'title': pg.title()})
        print('AFTER LOGIN URL:', pg.url)

        # Navigate to money-audit
        pg.goto(BASE + '/money-audit', timeout=40000)
        pg.wait_for_load_state('networkidle')
        time.sleep(4)
        body = pg.inner_text('body')
        report['money_audit_text'] = body[:4000]
        pg.screenshot(path=f'{SHOT_DIR}/03_money_audit.png', full_page=True)
        print('MONEY AUDIT URL:', pg.url)
        print('MONEY AUDIT TEXT (first 1500):')
        print(body[:1500])
        print('===')

        # Try to locate findings/ops
        for path in ['/ops', '/findings', '/recovery-match']:
            try:
                pg.goto(BASE + path, timeout=20000)
                pg.wait_for_load_state('domcontentloaded')
                time.sleep(2)
                t = pg.inner_text('body')
                report['nav_' + path.strip('/')] = t[:1500]
                pg.screenshot(path=f'{SHOT_DIR}/04_{path.strip("/")}.png', full_page=True)
                print('NAV', path, 'URL:', pg.url)
            except Exception as e:
                print('nav error', path, e)
        b.close()
    with open('reality_test_output/playwright_owner_journey.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, default=str)
    print('SAVED playwright_owner_journey.json')

if __name__ == '__main__':
    main()
