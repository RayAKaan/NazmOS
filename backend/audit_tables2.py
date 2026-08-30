import re

with open('app/database/models.py', 'rb') as f:
    content = f.read().decode('utf-8', errors='ignore')

# Use a simpler regex - match double quotes only since the file uses them
tables = re.findall(r'__tablename__\s*=\s*"([^"]+)"', content)

print(f'Total tables: {len(tables)}')
for t in sorted(tables):
    print(f'  {t}')