import requests, time, json, statistics
BASE='http://localhost:8000'
tok=requests.post(BASE+'/api/v1/auth/login', json={'email':'v12owner@nazmortestmail.com','password':'v12ownerPassw0rd'}, timeout=60).json()['access_token']
h={'Authorization':'Bearer '+tok}
bid='6d5312ba-c4c3-4e15-bacc-ab29a85adfa7'
print('SKUs=113')

def bench(name, fn, n=5):
    ts=[]
    for _ in range(n):
        t0=time.perf_counter(); fn(); ts.append((time.perf_counter()-t0)*1000)
    print(f'{name:<40} min={min(ts):.0f}ms med={sorted(ts)[len(ts)//2]:.0f}ms max={max(ts):.0f}ms')

bench('GET money-audit/current (enriched, nocache)',
      lambda: requests.get(BASE+'/api/v1/money-audit/current?business_id='+bid+'&auto_generate=false', headers=h, timeout=180))
bench('POST money-audit/generate (fresh audit)',
      lambda: requests.post(BASE+'/api/v1/money-audit/generate', headers=h, json={'business_id':bid}, timeout=180))
bench('GET inventory list (113)',
      lambda: requests.get(BASE+'/api/v1/items/?business_id='+bid, headers=h, timeout=180))
print('done')
