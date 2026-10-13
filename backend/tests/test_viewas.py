import pytest
from fastapi.testclient import TestClient

from app import auth, settings, users
from app.main import app

TARGET = "mec@lifelive-motorsport.com"


@pytest.fixture()
def c(monkeypatch):
    monkeypatch.setattr(settings, "SESSION_SECRET", "s" * 40)
    return TestClient(app)


def test_view_as_is_read_only_by_default_then_write_with_audit(c, monkeypatch):
    seen = []
    monkeypatch.setattr(auth, "audit_viewas", lambda real, target, method, path: seen.append((real, target, method, path)))
    import app.main as m
    monkeypatch.setattr(m, "audit_viewas", auth.audit_viewas)
    assert c.get("/api/session").json()["viewing_as"] is None
    r = c.post("/api/session/view-as", json={"email": TARGET})
    assert r.status_code == 200 and r.json()["viewing_as"]["write"] is False
    s = c.get("/api/session").json()
    assert s["email"] == TARGET and s["viewing_as"]["real"] == "anonymous"
    assert c.post("/api/leaves", json={"type": "paid", "start": "2030-01-07", "end": "2030-01-07"}).status_code == 403          # lecture seule
    assert seen == []
    c.post("/api/session/view-as", json={"email": TARGET, "write": True})
    assert c.get("/api/session").json()["viewing_as"]["write"] is True
    r = c.post("/api/leaves", json={"type": "paid", "start": "2030-01-07", "end": "2030-01-07"})
    assert "lecture seule" not in r.text                                                                                              # l’écriture n’est plus bloquée par le mode (refus métier : fiche non liée)
    assert any(x[0] == "anonymous" and x[1] == TARGET and x[2] == "POST" and x[3] == "/api/leaves" for x in seen)
    assert c.delete("/api/session/view-as").json()["viewing_as"] is None
    c.cookies.clear()
    assert c.get("/api/session").json()["email"] == "anonymous"


def test_view_as_only_for_super_users_and_valid_targets(c, monkeypatch):
    assert c.post("/api/session/view-as", json={"email": "pirate@gmail.com"}).status_code == 422
    assert c.post("/api/session/view-as", json={"email": "anonymous"}).status_code == 422
    monkeypatch.setattr(users, "is_super", lambda e: False)
    assert c.post("/api/session/view-as", json={"email": TARGET}).status_code == 403
    assert c.get("/api/session/view-as/candidates").status_code == 403


def test_tampered_or_foreign_cookie_is_ignored(c):
    c.cookies.set(auth.VIEWAS, "abc.def")
    assert c.get("/api/session").json()["email"] == "anonymous"
    forged = auth.make_viewas("someone@else.com", TARGET, True)                              # lié à une autre session : ignoré
    c.cookies.set(auth.VIEWAS, forged)
    assert c.get("/api/session").json()["email"] == "anonymous"
    expired = auth.make_viewas("anonymous", TARGET, True, now=1)
    c.cookies.set(auth.VIEWAS, expired)
    assert c.get("/api/session").json()["email"] == "anonymous"
