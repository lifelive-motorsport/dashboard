import pytest
from fastapi.testclient import TestClient

from app import alkamel, rides, timesheets, users
from app.auth import require_user
from app.main import app


def row(*cells):
    """Ligne synthétique : (x, texte) ; un texte à plusieurs mots est éclaté sur des abscisses voisines."""
    out = []
    for x, t in cells:
        for i, w in enumerate(str(t).split()):
            out.append((x + 8 * i, w))
    return out


def test_time_helpers():
    assert alkamel.secs("2:12.829") == 132.829 and alkamel.secs("1:01:22.785") == 3682.785 and alkamel.secs("29.551") == 29.551 and alkamel.secs("x") is None
    assert alkamel.fmt(132.829) == "2:12.829" and alkamel.fmt(29.551) == "29.551"


def test_head_conditions_and_classification_columns():
    head = alkamel.parse_head([row((150, "CLASSIC TOURING CHALLENGE")), row((150, "IMOLA CLASSIC")), row((150, "RACE (60')"))])
    assert (head["series"], head["event"], head["kind"]) == ("CLASSIC TOURING CHALLENGE", "IMOLA CLASSIC", "race")
    assert alkamel.parse_head([row((10, "x"))], "23_Analysis_PRIVATE PRACTICE.PDF")["kind"] == "practice"
    c = alkamel.parse_conditions("Track Temp: 23,30 ºC Air Temp: 19,58 ºC Track Status: DRY\nCAR 65 - TIME PENALTY OF 9 SECONDS\n18/10/2026 Page 1 / 1")
    assert c["track_c"] == 23.3 and c["air_c"] == 19.58 and c["status"] == "DRY" and c["date"] == "2026-10-18" and len(c["notes"]) == 1
    rows = [row((20, "Nr."), (60, "Drivers"), (260, "Car"), (400, "Class"), (440, "Laps")),
            row((10, "1"), (30, "179"), (60, "John SPIERS/Nigel GREENSALL"), (260, "Ford Mustang 289 1965"), (400, "+2L"), (440, "26"), (470, "1:01:22.785"), (520, "-"), (540, "124.8"), (560, "17"), (580, "2:12.829"), (620, "133.0")),
            row((10, "2"), (30, "76"), (60, "Abraham BONTRUP"), (260, "Ford Mustang 289 1965"), (400, "+2L"), (440, "26"), (470, "1:01:27.739"), (520, "+4.954"), (540, "124.6"), (560, "7"), (580, "2:14.105"), (620, "131.8")),
            row((10, "5"), (30, "40"), (60, "Michael ERLICH"), (260, "Alfa Romeo Giulia 1965"), (400, "-2L"), (440, "25"), (470, "1:01:49.488"), (520, "1 Lap"), (540, "119.1"), (560, "3"), (580, "2:20.927"), (620, "125.4")),
            row((30, "89"), (60, "Phil MULACEK"), (260, "Ford Mustang 289 1965"), (400, "+2L"), (440, "10"), (470, "37:26.636"), (560, "9"), (580, "2:19.926"), (620, "126.3"))]
    cl = alkamel.parse_classification(rows, "race")
    assert [(e["pos"], e["no"], e["laps"], e["best"], e.get("gap")) for e in cl] == [(1, 179, 26, "2:12.829", "-"), (2, 76, 26, "2:14.105", "+4.954"), (5, 40, 25, "2:20.927", "1 Lap"), (None, 89, 10, "2:19.926", None)]
    assert cl[0]["drivers"] == ["John SPIERS", "Nigel GREENSALL"] and cl[0]["car"] == "Ford Mustang 289 1965" and cl[3]["classified"] is False
    assert 4.9 < alkamel.estimate_length([{"classification": [{"total_time": "1:01:22.785", "kph": 124.8, "laps": 26}]}]) < 4.92


def lap(x0, n, d, t, s1="30.000", s2="45.000", s3="1:05.000", top="190.0", el="2:30.000"):
    return row((x0, n), (x0 + 14, d), (x0 + 26, t), (x0 + 73, s1), (x0 + 106, s2), (x0 + 133, s3), (x0 + 168, top), (x0 + 205, el))


def test_analysis_reads_left_column_then_right_then_next_page():
    """La voiture qui commence en bas de la colonne de gauche continue en haut de la colonne de droite, puis la page suivante."""
    p1 = [row((70, "30"), (94, "Alfa Romeo Giulia 1965")), row((94, "1.Carlo VÖGELE")),
          lap(64, 1, 1, "2:30.000"), lap(64, 2, 1, "2:25.000"),
          lap(325, 3, 2, "2:24.000"), lap(325, 4, 2, "2:23.000"),
          row((327, "40"), (355, "Alfa Romeo Giulia 1965")), row((355, "1.Michael ERLICH")), lap(325, 1, 1, "2:20.000")]
    p2 = [lap(64, 2, 1, "2:21.000"), lap(64, 3, 1, "2:22.000")]                # suite de la 40 en haut de la page suivante
    cars = alkamel.parse_analysis([p1, p2])
    assert [x["n"] for x in cars[30]["laps"]] == [1, 2, 3, 4] and [x["n"] for x in cars[40]["laps"]] == [1, 2, 3]
    assert cars[30]["drivers"] == ["Carlo VÖGELE"] and cars[30]["laps"][2]["d"] == 2
    s = alkamel.best_summary(cars[30]["laps"], "2:23.000")
    assert s["best"] == "2:23.000" and s["best_lap_no"] == 4 and s["top_speed"] == 190.0


@pytest.fixture()
def api(monkeypatch):
    for n in ("_cars", "_parts", "_runs", "_circuits", "_catalog", "_maint", "_templates", "_sessions"):
        monkeypatch.setattr(rides, n, None)
    monkeypatch.setattr(timesheets, "_blobs", None)
    monkeypatch.setattr(users, "is_super", lambda e: True)
    app.dependency_overrides[require_user] = lambda: "chef@lifelive-motorsport.com"
    yield TestClient(app)
    app.dependency_overrides.pop(require_user, None)


def test_import_creates_one_run_per_session_with_manual_session(api):
    cs = {c["name"]: c["key"] for c in api.get("/api/rides/cars").json()["cars"]}
    m3 = cs["BMW M3 E30"]
    cl = [{"pos": 1, "no": 20, "drivers": ["C. DUMOLIN", "R. de BORMAN"], "car": "Ford Mustang 289 1965", "class": "+2L", "classified": True, "laps": 25, "total_time": "1:03:36.849", "best": "2:18.061",
           "lap_list": [{"n": 25, "d": 2, "time": "2:25.941", "s1": "30.318", "s2": "48.891", "s3": "1:06.732", "top": 191.5, "elapsed": "1:03:02.474", "flags": []}]},
          {"pos": 2, "no": 76, "drivers": ["A. BONTRUP"], "car": "Ford Mustang 289 1965", "class": "+2L", "classified": True, "laps": 26}]
    body = {"series": "CTC", "event": "Imola Classic", "date": "2026-10-17", "circuit": "Imola", "circuit_km": 4.909,
            "sessions": [{"date": "2026-10-18", "session": "RACE (60')", "kind": "race", "conditions": {"track_c": 23.3}, "classification": cl, "cars": {"20": m3}}],
            "manual": [{"date": "2026-10-17", "name": "Essais de la veille", "cars": [{"key": m3, "laps": 8, "drivers": ["Raphaël"]}]}]}
    r = api.post("/api/rides/alkamel/import", json=body)
    assert r.status_code == 200 and len(r.json()["sessions"]) == 2 and r.json()["runs"] == 2
    ses = {s["name"]: s for s in api.get("/api/rides/sessions").json()["sessions"]}
    race, veille = ses["Imola Classic — RACE (60')"], ses["Imola Classic — Essais de la veille"]
    assert race["date"] == "2026-10-18" and race["circuit"] == "Imola" and race["alkamel"]["conditions"]["track_c"] == 23.3
    assert race["cars"][0]["laps"] == 25 and race["cars"][0]["km"] == 122.72 and race["cars"][0]["timing"]["best"] == "2:18.061" and race["cars"][0]["drivers"] == ["C. DUMOLIN", "R. de BORMAN"]   # 25 × 4,909
    assert veille["date"] == "2026-10-17" and veille["cars"][0]["laps"] == 8 and veille["cars"][0]["timing"] is None and veille["alkamel"] is None
    assert api.post("/api/rides/alkamel/import", json=body).status_code == 200            # ré-import : aucune duplication
    assert len(api.get("/api/rides/sessions").json()["sessions"]) == 2 and len(api.get(f"/api/rides/cars/{m3}").json()["runs_list"]) == 2
    bad = {**body, "sessions": [{**body["sessions"][0], "cars": {}}], "manual": []}
    assert api.post("/api/rides/alkamel/import", json=bad).status_code == 422                # aucune voiture associée
    assert api.post("/api/rides/alkamel/import", json={**body, "circuit": ""}).status_code == 422
    assert api.post("/api/rides/alkamel/parse", json={"files": [{"name": "x.pdf", "data": "bm90IGEgcGRm"}]}).status_code == 422


def test_grid_lapchart_and_field_ranks():
    grid = alkamel.parse_grid([row((262, "246"), (336, "112")), row((300, "-"), (306, "7"), (313, "-")),
                               row((72, "2:15.403"), (268, "76"), (336, "179"), (438, "1965")), row((300, "-"), (306, "1"), (313, "-"))])
    assert grid == {246: 14, 112: 13, 76: 2, 179: 1}
    rows = [row((103, "Grid")), row((64, "Nr"), (81, "Pos"), (239, "10")), row((118, "1"), (131, "2"), (145, "3")),
            row((64, "179"), (85, "1"), (102, "179"), (118, "76"), (130, "179"), (144, "179")),
            row((66, "76"), (85, "2"), (104, "76"), (116, "179"), (132, "76"), (145, "76"))]
    chart = alkamel.parse_lapchart(rows)
    assert chart[179][:4] == [1, 2, 1, 1] and chart[76][:4] == [2, 1, 2, 2]
    st = alkamel.race_story({"no": 179}, chart)
    assert (st["start"], st["finish"], st["best"], st["led"]) == (1, 1, 1, 2)
    cl = [{"no": 1, "summary": {"sectors": {"s1": "28.000", "s2": "45.000", "s3": "1:03.000"}, "top_speed": 200.0, "ideal": "2:16.000"}},
          {"no": 2, "summary": {"sectors": {"s1": "27.500", "s2": "46.000", "s3": "1:03.500"}, "top_speed": 210.0, "ideal": "2:17.000"}}]
    alkamel.add_field_ranks(cl)
    a, b = cl[0]["summary"], cl[1]["summary"]
    assert a["rank"] == {"s1": 2, "s2": 1, "s3": 1, "top": 2, "ideal": 1} and b["rank"]["top"] == 1 and a["gap"]["s1"] == 0.5 and b["gap"]["s2"] == 1.0 and a["field"] == 2


def _import_imola(api):
    m3 = {c["name"]: c["key"] for c in api.get("/api/rides/cars").json()["cars"]}["BMW M3 E30"]
    laps = [{"n": i, "d": 1, "time": f"2:{20 + i % 3}.000", "s1": "29.000", "s2": "46.000", "s3": "1:05.000", "top": 190.0 + i, "elapsed": "x", "flags": []} for i in range(1, 8)]
    cl = [{"pos": 3, "no": 20, "drivers": ["C. DUMOLIN", "R. de BORMAN"], "car": "Ford Mustang", "class": "+2L", "classified": True, "laps": 7, "best": "2:21.000", "grid": 8,
           "summary": {"best": "2:21.000", "sectors": {"s1": "29.000", "s2": "46.000", "s3": "1:05.000"}, "top_speed": 197.0, "ideal": "2:20.000", "rank": {"s1": 5, "s2": 5, "s3": 5, "top": 10, "ideal": 5}, "gap": {"s1": 1.3, "s2": 2.1, "s3": 1.9}, "field": 14},
           "story": {"start": 8, "finish": 3, "best": 3, "led": 0, "positions": [8, 7, 6, 5, 4, 3, 3]}, "lap_list": laps}]
    body = {"series": "CTC", "event": "Imola Classic", "date": "2026-10-18", "circuit": "Imola", "circuit_km": 4.909,
            "sessions": [{"date": "2026-10-18", "session": "RACE (60')", "kind": "race", "conditions": {"track_c": 23.3, "air_c": 19.5, "status": "DRY"}, "classification": cl, "cars": {"20": m3}}],
            "manual": [{"date": "2026-10-17", "name": "Essais de la veille", "cars": [{"key": m3, "laps": 8, "drivers": ["Raphaël"]}]}]}
    assert api.post("/api/rides/alkamel/import", json=body).status_code == 200
    return m3


def test_run_report_flow_print_and_client_privacy(api):
    from app import runreport
    m3 = _import_imola(api)
    ms = api.get("/api/rides/reports").json()["meetings"]
    assert len(ms) == 1 and ms[0]["event"] == "Imola Classic" and ms[0]["cars"][0]["status"] == "none" and ms[0]["cars"][0]["sessions"] == 2
    mid = ms[0]["meeting"]
    v = api.get(f"/api/rides/reports/{mid}/{m3}").json()
    assert [e["date"] for e in v["entries"]] == ["2026-10-17", "2026-10-18"] and v["entries"][1]["timing"]["best"] == "2:21.000" and v["km_total"] == 73.6
    assert [d["date"] for d in v["days"]] == ["2026-10-17", "2026-10-18"] and v["days"][1]["best"] == "2:21.000" and v["days"][1]["laps"] == 7
    rid_race = v["entries"][1]["run_id"]
    body = {"header": {"engineer": "Adam", "type_of_event": "Classic Touring Challenge"}, "general": "- Essayer les R8\n- 4500 tr/min en 3e", "actions_car": "- Setdown", "actions_logistics": "- Acheter un chronomètre",
            "runs": {rid_race: {"objective": "Course", "tyres_start": ["1.3", "1.4", "1.3", "1.4"], "observations": "1ère place\n65°C pneus ok", "driver_feedback": "Sur-virage en appui", "fuel_l": 70}, "inconnu": {"objective": "x"}},
            "tyre_sets": [{"set": "S9", "model": "HOOSIER", "laps": 49, "km": 186.2}, {"set": "", "model": ""}], "pressure_base": ""}
    s = api.put(f"/api/rides/reports/{mid}/{m3}", json=body).json()
    assert s["status"] == "draft" and "inconnu" not in s["runs"] and len(s["tyre_sets"]) == 1 and s["days"][1]["fuel"] == 70
    fr = api.get(f"/api/rides/reports/{mid}/{m3}/print").text
    assert "Synthèse générale" in fr and "HOOSIER" in fr and "Essayer les R8" in fr and "Acheter un chronomètre" in fr and "Brouillon" in fr and "2:21.000" in fr and "P8 → arrivée : P3" in fr and "5/14" in fr and "<svg" in fr
    assert "General summary" in api.get(f"/api/rides/reports/{mid}/{m3}/print?lang=en").text
    assert runreport.validated_for_car(m3) == []                                                    # un brouillon n'est pas visible du client
    assert api.post(f"/api/rides/reports/{mid}/{m3}/validate").json()["status"] == "validated"
    assert api.put(f"/api/rides/reports/{mid}/{m3}", json=body).status_code == 422                 # validé : verrouillé
    assert [r["event"] for r in runreport.validated_for_car(m3)] == ["Imola Classic"]
    cl_html = runreport.print_page(runreport.view(mid, m3), "fr", client=True)
    assert "Essayer les R8" in cl_html and "Setdown" in cl_html and "Acheter un chronomètre" not in cl_html and "Rapport validé" in cl_html   # la logistique reste interne
    assert api.post(f"/api/rides/reports/{mid}/{m3}/reopen").json()["status"] == "draft"
    assert api.get(f"/api/rides/reports/{mid}/zzz").status_code == 404


def test_circuit_suggestion_and_title_case():
    assert alkamel.title_case("IMOLA CLASSIC") == "Imola Classic" and alkamel.title_case("Imola Classic") == "Imola Classic"
    assert alkamel.suggest_circuit("Imola Classic", [{"name": "Imola", "length_km": 4.9}]) == {"name": "Imola", "existing": True}
    assert alkamel.suggest_circuit("Imola Classic", []) == {"name": "Imola", "existing": False}
    assert alkamel.suggest_circuit("Dijon Historic Festival", [{"name": "Spa", "length_km": 7}])["name"] == "Dijon"


def test_unexpected_pdf_does_not_crash_the_import():
    import pymupdf
    def pdf(lines):
        d = pymupdf.open(); p = d.new_page()
        for i, ln in enumerate(lines):
            p.insert_text((60, 80 + i * 16), ln)
        return d.tobytes()
    odd = pdf(["SERIE X", "EVENT Y", "RACE", "Final Classification", "Nr. Drivers Car 1 2 3"])           # en-tête sans colonne « Class » : plantait avec une KeyError
    ok = pdf(["SERIE X", "EVENT Y", "RACE", "Sector Analysis"])
    r = alkamel.parse_files([("03_Classification_RACE.PDF", odd), ("23_Analysis_RACE.PDF", ok)])
    assert r["event"] and isinstance(r["sessions"], list) and isinstance(r["errors"], list)
    with pytest.raises(ValueError):
        alkamel.parse_files([("x.pdf", b"pas un pdf")])


def test_suggested_cars_only_for_numbers_present_in_the_event(api):
    cs = {c["name"]: c["key"] for c in api.get("/api/rides/cars").json()["cars"]}
    for name, no in (("BMW M3 E30", "20"), ("Porsche 992 Rally", "99")):
        meta = rides.cars_coll().get(cs[name]) or {"id": cs[name]}
        rides.cars_coll().put(cs[name], {**meta, "race_number": no})
    sug = alkamel.suggest_cars({"sessions": [{"classification": [{"no": 20}, {"no": 76}]}]})
    assert sug == [{"no": 20, "key": cs["BMW M3 E30"]}]                                           # la Porsche n° 99 n'est pas engagée : non proposée


def test_timed_session_refuses_manual_car_association_but_keeps_untimed_open(api):
    m3 = _import_imola(api)
    p992 = {c["name"]: c["key"] for c in api.get("/api/rides/cars").json()["cars"]}["Porsche 992 Rally"]
    ses = {s["name"]: s for s in api.get("/api/rides/sessions").json()["sessions"]}
    race, veille = ses["Imola Classic — RACE (60')"], ses["Imola Classic — Essais de la veille"]
    r = api.post(f"/api/rides/sessions/{race['id']}/cars/{p992}", json={"laps": 12})
    assert r.status_code == 422 and "Al Kamel" in r.json()["detail"] and race["alkamel"]
    assert api.post(f"/api/rides/sessions/{veille['id']}/cars/{p992}", json={"laps": 6}).status_code == 200      # la session non chronométrée reste ouverte
    # corriger la participation chronométrée garde le chronométrage
    run = next(c for c in race["cars"] if c["key"] == m3)
    cur = api.get(f"/api/rides/cars/{m3}").json()["runs_list"]
    mine = next(x for x in cur if x["id"] == run["run_id"])
    api.put(f"/api/rides/runs/{mine['id']}", json={"date": "2026-10-18", "name": "x", "laps": mine["laps"], "km": mine["km"], "drivers": ["Autre"]})
    assert next(x for x in api.get(f"/api/rides/cars/{m3}").json()["runs_list"] if x["id"] == mine["id"])["timing"]["best"] == "2:21.000"
