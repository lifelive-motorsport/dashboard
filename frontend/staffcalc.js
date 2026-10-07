// Calculs des coûts du personnel (fonctions pures, testées avec node). Montants en euros.
// Coût société annualisé d'un salarié = (brut mensuel + cotisations patronales) × facteur d'annualisation (13,92 : 12 mois + 13e mois + double pécule)
//   + autres coûts société récurrents × 12 (+ cotisations sociales d'un gérant payées via la comptabilité, `socialMonthly`) + coûts « hors salaire » (véhicule, carte essence, téléphone…) × 12.
const SC = (() => {
  const sortedSlips = p => (p.payslips || []).slice().sort((a, b) => (a.month < b.month ? -1 : 1));
  const lastSlip = p => { const s = sortedSlips(p); return s.length ? s[s.length - 1] : null; };
  const extrasMonthly = p => (p.extras || []).reduce((t, e) => t + (+e.monthly || 0), 0);
  const slipPatronal = (p, s) => (s.patronal != null ? +s.patronal : (+s.brut || 0) * (+p.patronal_pct || 0) / 100);

  function finish(annual, p, params) {
    const days = (+params.days_per_year || 220) * (+p.fte || 100) / 100, hoursDay = (+p.hours_week || 38) / 5;
    return {annual, monthly: annual / 12, daily: days ? annual / days : 0, hourly: days && hoursDay ? annual / days / hoursDay : 0};
  }

  function employeeCosts(p, params, socialMonthly = 0) {
    const last = lastSlip(p), brut = p.brut_override != null ? +p.brut_override : (last ? +last.brut || 0 : 0);
    const patronal = (last && p.brut_override == null && last.patronal != null) ? +last.patronal : brut * (+p.patronal_pct || 0) / 100;
    const remunMonthly = brut + patronal, factor = (p.factor != null ? +p.factor : +params.annual_factor) || 13.92, remunAnnual = remunMonthly * factor;
    const recurringAnnual = ((+p.monthly_other || 0) + (+socialMonthly || 0)) * 12, extrasAnnual = extrasMonthly(p) * 12;
    return {brut, patronal, factor, remunMonthly, remunAnnual, recurringAnnual, extrasAnnual, ...finish(remunAnnual + recurringAnnual + extrasAnnual, p, params)};
  }

  // Indépendant : facturé HT depuis le début de l'année ÷ mois écoulés = moyenne mensuelle ; annualisé × 12 ; + coûts « hors facture » × 12.
  function independentCosts(p, params, invoicedYtd, monthsElapsed) {
    const avg = monthsElapsed > 0 ? invoicedYtd / monthsElapsed : 0, invoicedAnnual = avg * 12, extrasAnnual = extrasMonthly(p) * 12;
    return {invoicedYtd, invoicedMonthlyAvg: avg, invoicedAnnual, extrasAnnual, ...finish(invoicedAnnual + extrasAnnual, p, params)};
  }

  // Imputation : coût annuel × % par entité ; le reste (jusqu'à 100 %) est « non imputé ».
  function allocate(annual, alloc) {
    const keys = ['XC', 'MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING', 'SHARED'], out = {};
    let used = 0;
    keys.forEach(k => { const v = +((alloc || {})[k]) || 0; out[k] = annual * v / 100; used += v; });
    out.UNALLOCATED = annual * Math.max(0, 100 - used) / 100; out.pct = used;
    return out;
  }

  // Contrôle comptable : par mois, coût « rémunération » des fiches de paie (brut + patronal) face aux comptes 620/621 ; seuls les salariés comptent, hors ceux dont la rémunération n'est pas en 620/621 (gérant).
  function payrollByMonth(people, outside = false) {
    const m = {};
    people.filter(p => p.kind === 'salarie' && (p.in_payroll === false) === !!outside).forEach(p => (p.payslips || []).forEach(s => { m[s.month] = (m[s.month] || 0) + (+s.brut || 0) + slipPatronal(p, s); }));
    return m;
  }

  return {employeeCosts, independentCosts, allocate, payrollByMonth, lastSlip, sortedSlips, extrasMonthly};
})();
if (typeof module !== 'undefined') module.exports = SC;
