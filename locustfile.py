from locust import HttpUser, task, between

class AdminUser(HttpUser):

    wait_time = between(1,3)

    def on_start(self):
        self.client.post(
            "/login",
            data={
                "identifier":"1001",
                "password":"adel123"
            }
        )

    @task(3)
    def dashboard(self):
        self.client.get("/admin")

    @task(2)
    def report(self):
        self.client.get("/admin/report")

    @task(1)
    def manage_user(self):
        self.client.get("/admin/manage-user")


class TechnicianUser(HttpUser):

    wait_time = between(1,3)

    def on_start(self):
        self.client.post(
            "/login",
            data={
                "identifier":"2001",
                "password":"diky123"   # ganti dengan password teknisi yang benar
            }
        )

    @task(3)
    def dashboard(self):
        self.client.get("/technician")

    @task(2)
    def history(self):
        self.client.get("/technician/history")

    @task(1)
    def report(self):
        self.client.get("/technician/report")