import json
e=json.load(open(r'H:\NAZMOS\nazmos\results\v12\evidence\evaluation.json',encoding='utf-8'))
r=e.get('rows',[])
bad=[x for x in r if not x.get('classification_match')]
print('mismatch count:', len(bad))
for x in bad:
    print(f"{x['sku']:<14} exp={x['expected_classification']:<12} db={x['db_classification']:<12}")

# also show action status for all rows
print('\nAction status histogram:')
from collections import Counter
print(Counter(x.get('action_status') for x in r))
print('\nROWS where expected_action differs from actual, or status not matched:')
actbad=[x for x in r if x.get('expected_primary_action')!=x.get('actual_primary_action')]
print('primary-action mismatches:', len(actbad))
for x in actbad:
    print(f"  {x['sku']:<14} expA={x.get('expected_primary_action')} actA={x.get('actual_primary_action')} st={x.get('action_status')}")
