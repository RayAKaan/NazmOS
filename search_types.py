import os
import re

app_dir = r"backend/app"
action_types = set()
decision_types = set()

for root, dirs, files in os.walk(app_dir):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for fname in files:
        if fname.endswith('.py'):
            full = os.path.join(root, fname)
            try:
                with open(full, 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
                for m in re.findall(r"action_type\s*=\s*['\"]([^'\"]+)['\"]", content):
                    action_types.add(m)
                for m in re.findall(r'"action_type"\s*:\s*[\'"]([^\'"]+)[\'"]', content):
                    action_types.add(m)
                for m in re.findall(r'"decision_type"\s*:\s*[\'"]([^\'"]+)[\'"]', content):
                    decision_types.add(m)
            except:
                pass

print('Action types found:', sorted(action_types))
print('Decision types found:', sorted(decision_types))