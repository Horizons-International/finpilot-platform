"""Integration checks for the static developer portal routes."""


def test_developer_portal_page_is_served(client):
    response = client.get("/developer-portal")

    assert response.status_code == 200
    assert len(response.content) == int(response.headers["content-length"])
    assert "FinPilot Developer Portal" in response.text
    assert "/developer-portal/styles.css" in response.text
    assert "/developer-portal/app.js" in response.text

    # SecurityMonitoringMiddleware uses a strict default-src 'none' policy for
    # regular API responses. The portal needs an explicit same-origin asset policy.
    csp = response.headers.get("content-security-policy", "")
    assert "style-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "connect-src 'self' http: https:" in csp


def test_developer_portal_assets_are_served(client):
    css_response = client.get("/developer-portal/styles.css")
    js_response = client.get("/developer-portal/app.js")

    assert css_response.status_code == 200
    assert len(css_response.content) == int(css_response.headers["content-length"])
    assert "--navy" in css_response.text
    assert js_response.status_code == 200
    assert len(js_response.content) == int(js_response.headers["content-length"])
    assert "key-login-button" in js_response.text
    # Dynamic status color uses CSS classes rather than inline styles, so the
    # portal stays compatible with style-src 'self'.
    assert 'classList.toggle("is-error", isError)' in js_response.text
    assert "el.style.color" not in js_response.text


def test_developer_portal_does_not_serve_arbitrary_paths(client):
    response = client.get("/developer-portal/../../main.py")

    assert response.status_code in {404, 422}
