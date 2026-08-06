"""Locust load-test definition for NazmOS public endpoints.

Install Locust separately (it is not in requirements.txt to keep the core
image small):

    pip install locust
    locust -f backend/tests/load/locustfile.py --host http://localhost:8000
"""
try:
    from locust import HttpUser, task, between
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Locust is not installed. Run: pip install locust"
    ) from exc


class NazmOSUser(HttpUser):
    """Simulates a single merchant owner browsing the dashboard and agent feed."""

    wait_time = between(1, 3)

    def on_start(self):
        self.email = f"locust_{self.user_id}@example.com"
        self.password = "Locust123!"
        self.token = None
        self.business_id = None

        register = self.client.post(
            "/api/v1/auth/register",
            json={"email": self.email, "password": self.password, "full_name": "Locust User"},
        )
        if register.status_code not in (200, 201):
            raise Exception(f"Registration failed: {register.text}")

        login = self.client.post(
            "/api/v1/auth/login",
            json={"email": self.email, "password": self.password},
        )
        if login.status_code != 200:
            raise Exception(f"Login failed: {login.text}")

        self.token = login.json()["access_token"]

        bootstrap = self.client.post(
            "/api/v1/businesses/bootstrap",
            json={"name": "Locust Baqala", "type": "baqala", "city": "Riyadh"},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        if bootstrap.status_code != 200:
            raise Exception(f"Bootstrap failed: {bootstrap.text}")

        self.business_id = bootstrap.json()["id"]

    @task(3)
    def health_check(self):
        self.client.get("/health")

    @task(5)
    def dashboard_summary(self):
        self.client.get(
            f"/api/v1/dashboard/summary?business_id={self.business_id}",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    @task(5)
    def agent_feed(self):
        self.client.get(
            f"/api/v1/agent/feed?business_id={self.business_id}",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    @task(2)
    def dashboard_alerts(self):
        self.client.get(
            f"/api/v1/dashboard/alerts?business_id={self.business_id}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
