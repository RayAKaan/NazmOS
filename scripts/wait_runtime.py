import os,time,requests
api=os.getenv("API_BASE_URL","http://localhost:8000").rstrip("/"); front=os.getenv("FRONTEND_URL","http://localhost:3000").rstrip("/")
deadline=time.time()+180
while time.time()<deadline:
 try:
  a=requests.get(api+"/api/v1/ready",timeout=5); f=requests.get(front,timeout=5)
  if a.status_code==200 and f.status_code<500: print("RUNTIME_SERVICES_REACHABLE"); raise SystemExit(0)
 except Exception: pass
 time.sleep(3)
print("RUNTIME_SERVICES_NOT_READY"); raise SystemExit(1)
