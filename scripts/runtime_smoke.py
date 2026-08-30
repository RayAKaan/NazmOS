#!/usr/bin/env python3
import json, os, secrets, requests
BASE=os.getenv("API_BASE_URL","http://localhost:8000").rstrip("/"); FRONTEND=os.getenv("FRONTEND_URL","http://localhost:3000").rstrip("/")
EMAIL=os.getenv("E2E_EMAIL",f"runtime-smoke-{secrets.token_hex(4)}@example.com"); PASSWORD=os.getenv("E2E_PASSWORD","RuntimeSmoke!2026-Strong")
def req(method,url,**kw):
 r=requests.request(method,url,timeout=20,**kw); print(method,url,"->",r.status_code); return r
def fail(m): print("RUNTIME_SMOKE_FAILED:",m); raise SystemExit(1)
r=req("GET",FRONTEND)
if r.status_code>=500: fail("frontend unhealthy")
for path in ("/health","/api/v1/health","/api/v1/live","/api/v1/ready","/api/v1/health/redis","/api/v1/health/celery"):
 r=req("GET",BASE+path)
 if r.status_code!=200: fail(f"{path}: {r.status_code} {r.text[:500]}")
ready=req("GET",BASE+"/api/v1/ready").json(); celery=req("GET",BASE+"/api/v1/health/celery").json()
if ready.get("status")!="ready": fail(f"API not ready: {ready}")
if not celery.get("reachable") or not celery.get("workers_online"): fail(f"Celery worker not proven: {celery}")
r=req("POST",BASE+"/api/v1/auth/register",json={"email":EMAIL,"password":PASSWORD,"full_name":"NazmOS Runtime Smoke"})
if r.status_code==201: token=r.json().get("access_token")
else:
 r=req("POST",BASE+"/api/v1/auth/login",json={"email":EMAIL,"password":PASSWORD})
 if r.status_code!=200: fail("authentication failed")
 token=r.json().get("access_token")
if not token: fail("no access token")
headers={"Authorization":f"Bearer {token}"}
r=req("POST",BASE+"/api/v1/businesses/bootstrap",headers=headers,json={"name":"Runtime Smoke Business","type":"baqala","city":"Riyadh"})
if r.status_code!=200: fail("business creation failed")
bid=r.json()["id"]
r=req("GET",BASE+f"/api/v1/money-audit/current?business_id={bid}&auto_generate=false",headers=headers)
if r.status_code not in (200,404): fail("protected Money Audit route failed")
print("RUNTIME_SMOKE_PASSED")
print(json.dumps({"business_id":bid,"celery_workers":celery.get("workers_online"),"note":"Readiness only; full V5 not run."},indent=2))
