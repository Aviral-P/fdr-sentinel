"""Health endpoint tests."""


def test_health_reports_application_and_database_ready(client) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_root_page_links_to_docs_and_health(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "FDR Sentinel API" in response.text
    assert "/docs" in response.text
    assert "/api/v1/health" in response.text


def test_favicon_is_served_as_svg(client) -> None:
    response = client.get("/favicon.ico")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in response.text


def test_cors_preflight_allows_vite_login_request(client) -> None:
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "POST" in response.headers["access-control-allow-methods"]
