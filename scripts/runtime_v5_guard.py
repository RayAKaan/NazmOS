import os,requests
api=os.getenv("API_BASE_URL","http://localhost:8000").rstrip("/"); front=os.getenv("FRONTEND_URL","http://localhost:3000").rstrip("/")
for url in (api+"/api/v1/ready",api+"/api/v1/health/redis",api+"/api/v1/health/celery",front):
 try: r=requests.get(url,timeout=10)
 except Exception as e: print("V5_BLOCKED:",e); raise SystemExit(2)
 if r.status_code!=200: print("V5_BLOCKED:",url,r.status_code); raise SystemExit(2)
ready=requests.get(api+"/api/v1/ready",timeout=10).json(); celery=requests.get(api+"/api/v1/health/celery",timeout=10).json()
if ready.get("status")!="ready" or not celery.get("reachable") or not celery.get("workers_online"): print("V5_BLOCKED: runtime readiness not proven"); raise SystemExit(2)
print("V5_RUNTIME_GATE_PASSED")
