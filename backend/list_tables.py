import re

with open('app/database/models.py', 'rb') as f:
    content = f.read().decode('utf-8', errors='ignore')

tables = []
for line in content.split('\n'):
    m = re.search(r'__tablename__\s*=\s*[\'"]([\'"]+)', line)
    if m:
        tables.append(m.group(1))

print(f'Total tables: {len(tables)}')
for t in sorted(tables):
    print(f'  {t}')