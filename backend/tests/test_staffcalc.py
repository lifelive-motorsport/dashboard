import json
import subprocess
from pathlib import Path

JS = Path(__file__).resolve().parents[2] / "frontend" / "staffcalc.js"


def run(expr: str):
    out = subprocess.run(["node", "-e", f"const SC=require('{JS}');console.log(JSON.stringify({expr}))"], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_employee_costs_annualisation_daily_and_hourly():
    p = {"brut_override": None, "patronal_pct": 25, "monthly_other": 100, "fte": 100, "hours_week": 38,
         "payslips": [{"month": "2026-01", "brut": 3000}, {"month": "2026-02", "brut": 4000, "patronal": 1000}],
         "extras": [{"monthly": 300}, {"monthly": 50}]}
    r = run(f"SC.employeeCosts({json.dumps(p)}, {{annual_factor: 13.92, days_per_year: 220}})")
    assert r["brut"] == 4000 and r["patronal"] == 1000                                   # dernière fiche : brut et cotisations réelles
    assert round(r["remunAnnual"], 2) == round(5000 * 13.92, 2) == 69600
    assert r["recurringAnnual"] == 1200 and r["extrasAnnual"] == 4200
    assert r["annual"] == 69600 + 1200 + 4200 and round(r["monthly"], 2) == round(75000 / 12, 2)
    assert round(r["daily"], 2) == round(75000 / 220, 2) and round(r["hourly"], 2) == round(75000 / 220 / 7.6, 2)


def test_estimated_patronal_part_time_and_override():
    p = {"brut_override": 2000, "patronal_pct": 25, "monthly_other": 0, "fte": 50, "hours_week": 38, "payslips": [{"month": "2026-03", "brut": 9999, "patronal": 1}], "extras": []}
    r = run(f"SC.employeeCosts({json.dumps(p)}, {{annual_factor: 13.92, days_per_year: 220}})")
    assert r["brut"] == 2000 and r["patronal"] == 500                                    # le brut de référence l'emporte : patronal estimé à 25 %
    assert round(r["daily"], 2) == round(2500 * 13.92 / 110, 2)                          # mi-temps : 110 jours


def test_independent_allocation_and_payroll_by_month():
    ind = run("SC.independentCosts({extras:[{monthly:200}], fte:100, hours_week:38}, {annual_factor:13.92, days_per_year:220}, 30000, 6)")
    assert ind["invoicedMonthlyAvg"] == 5000 and ind["invoicedAnnual"] == 60000 and ind["annual"] == 62400
    a = run("SC.allocate(100000, {XC: 60, HISTORIC_RACING: 10, SHARED: 20})")
    assert a["XC"] == 60000 and a["HISTORIC_RACING"] == 10000 and a["SHARED"] == 20000 and a["UNALLOCATED"] == 10000 and a["pct"] == 90
    m = run("SC.payrollByMonth([{kind:'salarie', patronal_pct:25, payslips:[{month:'2026-01', brut:1000},{month:'2026-02', brut:1000, patronal:300}]},"
            "{kind:'independant', payslips:[{month:'2026-01', brut:5000}]}])")
    assert m == {"2026-01": 1250, "2026-02": 1300}


def test_person_factor_overrides_global_factor():
    p = {"brut_override": 3000, "patronal_pct": 0, "factor": 12, "monthly_other": 0, "fte": 100, "hours_week": 38, "payslips": [], "extras": []}
    r = run(f"SC.employeeCosts({json.dumps(p)}, {{annual_factor: 13.92, days_per_year: 220}})")
    assert r["factor"] == 12 and r["remunAnnual"] == 36000
    p["factor"] = None
    assert run(f"SC.employeeCosts({json.dumps(p)}, {{annual_factor: 13.92, days_per_year: 220}})")["remunAnnual"] == 3000 * 13.92
