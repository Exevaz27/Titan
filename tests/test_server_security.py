import os
import unittest

try:
    from fastapi.testclient import TestClient
    from server.web_server import app
except ImportError:
    TestClient = None
    app = None


@unittest.skipUnless(TestClient and app, "Requiere dependencias del servidor")
class TestServerSecurity(unittest.TestCase):
    def setUp(self):
        self.old_api = os.environ.get("TITAN_API_TOKEN")
        self.old_satellite = os.environ.get("TITAN_SATELLITE_TOKEN")
        os.environ["TITAN_API_TOKEN"] = "api-secret"
        os.environ["TITAN_SATELLITE_TOKEN"] = "satellite-secret"
        self.client = TestClient(app)

    def tearDown(self):
        for name, value in (("TITAN_API_TOKEN", self.old_api), ("TITAN_SATELLITE_TOKEN", self.old_satellite)):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_localhost_api_remains_available_without_token(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)

    def test_invalid_api_token_is_rejected(self):
        response = self.client.get("/api/status", headers={"x-titan-token": "wrong"})
        self.assertEqual(response.status_code, 401)

    def test_remote_api_accepts_valid_token(self):
        response = self.client.get(
            "/api/status",
            headers={"x-titan-token": "api-secret"},
        )
        self.assertEqual(response.status_code, 200)

    def test_chat_payload_is_limited(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "x" * 8_001},
        )
        self.assertEqual(response.status_code, 422)

    def test_api_key_payload_rejects_short_keys(self):
        response = self.client.post("/api/key", json={"api_key": "short"})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
