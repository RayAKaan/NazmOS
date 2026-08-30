import re, glob

with open('app/database/models.py', 'rb') as f:
    content = f.read().decode('utf-8', errors='ignore')

# All table names
tables = re.findall(r'__tablename__\s*=\s*[\'"]([\'"]+)[\'"]', content)

# Used tables from imports
service_files = glob.glob('app/services/*.py') + glob.glob('app/routers/*.py')
used_models = set()
for sf in service_files:
    try:
        with open(sf, 'r', encoding='utf-8', errors='ignore') as f:
            c = f.read()
        imports = re.findall(r'from app\.database\.models import\s+([^#\n]+)', c)
        for imp in imports:
            for item in re.split(r'[,\s]+', imp):
                item = item.strip()
                if item and item not in ('Base', '(', ')'):
                    used_models.add(item)
    except:
        pass

# Map class name to table name
class_to_table = {}
for match in re.finditer(r'class\s+(\w+)\s*\([^)]*\):', content):
    cls = match.group(1)
    after = content[match.end():match.end()+2000]
    m = re.search(r'__tablename__\s*=\s*[\'"]([\'"]+)[\'"]', after)
    if m:
        class_to_table[cls] = m.group(1)

used_tables = set()
for m in used_models:
    if m in class_to_table:
        used_tables.add(class_to_table[m])

print(f'Total tables: {len(tables)}')
print(f'Used tables: {len(used_tables)}')
print(f'Unused tables: {len(set(tables) - used_tables)}')
print()
print('=== UNUSED TABLES ===')
for t in sorted(set(tables) - used_tables):
    print(f'  {t}')