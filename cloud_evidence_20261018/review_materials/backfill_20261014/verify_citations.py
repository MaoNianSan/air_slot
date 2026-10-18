"""Verify that every quantitative claim cited in the backfilled Section 5 matches the
extracted audited values. Fails loudly on any mismatch.
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

ROOT = Path("D:/Local_Projects/airslot/backfill_20261014")
TEX = (ROOT / "paper" / "sections" / "05_experiment.tex").read_text(encoding="utf-8")
SUP = (ROOT / "paper" / "SUPPLEMENT.tex").read_text(encoding="utf-8")
YEARS = (2017, 2018, 2019, 2020, 2021, 2022)

e1 = json.loads((ROOT / "extracted" / "e1_six_year.json").read_text(encoding="utf-8"))
e2 = json.loads((ROOT / "extracted" / "e2_six_year.json").read_text(encoding="utf-8"))
e3 = json.loads((ROOT / "extracted" / "e3_six_year.json").read_text(encoding="utf-8"))
der = json.loads((ROOT / "extracted" / "derived_and_checks.json").read_text(encoding="utf-8"))

checks: list[tuple[str, object, object]] = []


def span(values, nd=4):
    return (round(min(values), nd), round(max(values), nd))


def nominal(year, stage, view, key):
    return e1[str(year)]["nominal_q010"][stage][view][key]


# --- E1 screening ranges -----------------------------------------------------------
pre_share = [nominal(y, "PRE", "DELAY", "replacement") / nominal(y, "PRE", "DELAY", "k") for y in YEARS]
turn_share = [nominal(y, "TURN", "DELAY", "replacement") / nominal(y, "TURN", "DELAY", "k") for y in YEARS]
checks.append(("PRE displaced share span %", span([v * 100 for v in pre_share], 1), (37.4, 53.1)))
checks.append(("TURN displaced share span %", span([v * 100 for v in turn_share], 1), (39.6, 55.3)))
checks.append(("PRE L_att span", span([nominal(y, "PRE", "DELAY", "attention_loss") for y in YEARS]),
               (0.1006, 0.1840)))
checks.append(("TURN L_att span", span([nominal(y, "TURN", "DELAY", "attention_loss") for y in YEARS]),
               (0.1068, 0.1811)))
_ci = lambda y, s: {k: round(v, 4) for k, v in nominal(y, s, "DELAY", "attention_loss_ci").items()}
checks.append(("2020 PRE L_att CI", (round(nominal(2020, "PRE", "DELAY", "attention_loss"), 4), _ci(2020, "PRE")),
               (0.1006, {"low": 0.0712, "high": 0.1461})))
checks.append(("2022 PRE L_att CI", (round(nominal(2022, "PRE", "DELAY", "attention_loss"), 4), _ci(2022, "PRE")),
               (0.1840, {"low": 0.1506, "high": 0.2163})))
checks.append(("2022 TURN L_att CI", (round(nominal(2022, "TURN", "DELAY", "attention_loss"), 4), _ci(2022, "TURN")),
               (0.1811, {"low": 0.1618, "high": 0.1996})))
checks.append(("PRE replaced counts span", (min(nominal(y, "PRE", "DELAY", "replacement") for y in YEARS),
                                            max(nominal(y, "PRE", "DELAY", "replacement") for y in YEARS)),
               (27, 76)))
checks.append(("TURN replaced counts span", (min(nominal(y, "TURN", "DELAY", "replacement") for y in YEARS),
                                             max(nominal(y, "TURN", "DELAY", "replacement") for y in YEARS)),
               (154, 215)))
pass_reduction_pre = [1 - nominal(y, "PRE", "DELAY_PASSENGER", "attention_loss") / nominal(y, "PRE", "DELAY", "attention_loss") for y in YEARS]
pass_reduction_turn = [1 - nominal(y, "TURN", "DELAY_PASSENGER", "attention_loss") / nominal(y, "TURN", "DELAY", "attention_loss") for y in YEARS]
checks.append(("Delay+Passenger reduction PRE %", (round(min(pass_reduction_pre) * 100), round(max(pass_reduction_pre) * 100)),
               (6, 45)))
checks.append(("Delay+Passenger reduction TURN %", (round(min(pass_reduction_turn) * 100), round(max(pass_reduction_turn) * 100)),
               (20, 38)))
dp = span([nominal(y, s, "DELAY_PASSENGER", "attention_loss") for y in YEARS for s in ("PRE", "TURN")])
checks.append(("Delay+Passenger L_att span (both stages)",
               (round(min(nominal(y, "PRE", "DELAY_PASSENGER", "attention_loss") for y in YEARS), 4),
                round(max(nominal(y, "PRE", "DELAY_PASSENGER", "attention_loss") for y in YEARS), 4),
                round(min(nominal(y, "TURN", "DELAY_PASSENGER", "attention_loss") for y in YEARS), 4),
                round(max(nominal(y, "TURN", "DELAY_PASSENGER", "attention_loss") for y in YEARS), 4)),
               (0.0626, 0.1721, 0.0674, 0.1446)))
downstream_delta = max(
    abs(nominal(y, s, "DELAY", "attention_loss") - nominal(y, s, "DELAY_DOWNSTREAM", "attention_loss"))
    for y in YEARS for s in ("PRE", "TURN")
)
checks.append(("max |DELAY - DOWNSTREAM| L_att", round(downstream_delta, 4) <= 0.003, True))
checks.append(("2022 PRE passenger residual", (round(nominal(2022, "PRE", "DELAY", "attention_loss"), 4),
                                               round(nominal(2022, "PRE", "DELAY_PASSENGER", "attention_loss"), 4)),
               (0.1840, 0.1721)))
q_means = {}
for view in ("DELAY", "DELAY_PASSENGER"):
    for stage in ("PRE", "TURN"):
        q_means[(view, stage)] = [statistics.fmean(
            next(r for r in e1[str(y)]["q_grid"] if r["stage"] == stage and abs(r["q"] - q) < 1e-9 and r["view"] == view)["attention_loss"]
            for y in YEARS) for q in (0.05, 0.10, 0.20, 0.30)]
checks.append(("year-mean delay L_att q=0.05 -> q=0.30 (PRE)", (round(q_means[("DELAY", "PRE")][0], 3), round(q_means[("DELAY", "PRE")][3], 3)), (0.174, 0.071)))
checks.append(("year-mean delay L_att q=0.05 -> q=0.30 (TURN)", (round(q_means[("DELAY", "TURN")][0], 3), round(q_means[("DELAY", "TURN")][3], 3)), (0.165, 0.069)))
gap_at_030 = abs(q_means[("DELAY", "PRE")][3] - q_means[("DELAY_PASSENGER", "PRE")][3])
checks.append(("q=0.30 PRE gap within 0.006", round(gap_at_030, 4) < 0.006, True))

# --- E2 paired contrasts -----------------------------------------------------------
for component, label, expected_att, expected_rec in (
    ("CROSS_STATE_DEPENDENCE", "HM-HJ", (0.0006, 0.0026), (0.0853, 0.1247)),
    ("DISTRIBUTIONAL_INFORMATION", "HP-HJ", (0.4134, 0.5291), (0.8963, 0.9814)),
    ("ROLLING_HISTORY", "CJ-HJ", (0.0101, 0.5060), (0.3102, 0.9977)),
    ("MARGINAL_UNCERTAINTY", "HP-HM", (0.4095, 0.5291), (0.8040, 0.8879)),
):
    att = [e2[str(y)]["e2"]["information_value"][component]["L_att"] for y in YEARS]
    rec = [e2[str(y)]["e2"]["information_value"][component]["L_rec"] for y in YEARS]
    checks.append((f"{label} L_att span", span(att), expected_att))
    checks.append((f"{label} L_rec span", span(rec), expected_rec))
hm_share = span([e2[str(y)]["e2"]["information_value"]["CROSS_STATE_DEPENDENCE"]["stage1_reassigned_share"] for y in YEARS])
checks.append(("HM-HJ displaced share span", (round(hm_share[0] * 100, 1), round(hm_share[1] * 100, 1)), (1.3, 3.8)))
hp_share = span([e2[str(y)]["e2"]["information_value"]["DISTRIBUTIONAL_INFORMATION"]["stage1_reassigned_share"] for y in YEARS])
checks.append(("HP-HJ displaced share span %", (round(hp_share[0] * 100), round(hp_share[1] * 100)), (84, 89)))
a0_hm_raw = [e2[str(y)]["e2"]["information_value"]["CROSS_STATE_DEPENDENCE"]["A0"] for y in YEARS]
a0_hp_raw = [e2[str(y)]["e2"]["information_value"]["DISTRIBUTIONAL_INFORMATION"]["A0"] for y in YEARS]
checks.append(("HM-HJ A0 span", span(a0_hm_raw, 3), (0.581, 0.730)))
checks.append(("HP-HJ A0 span", span(a0_hp_raw, 3), (0.13, 0.241)))
checks.append(("2020 CJ L_att", round(e2["2020"]["e2"]["information_value"]["ROLLING_HISTORY"]["L_att"], 3), 0.506))
checks.append(("2020 CJ A0", round(e2["2020"]["e2"]["information_value"]["ROLLING_HISTORY"]["A0"], 3), 0.086))
checks.append(("2020 CJ L_rec", round(e2["2020"]["e2"]["information_value"]["ROLLING_HISTORY"]["L_rec"], 3), 0.998))
checks.append(("2020 CJ missed activations", e2["2020"]["e2"]["information_value"]["ROLLING_HISTORY"]["missed_activation"], 425))
checks.append(("2020 cohort", e2["2020"]["e2"]["reference_cohort_size"], 474))
ref_v = [e2[str(y)]["e2"]["information_value"]["CROSS_STATE_DEPENDENCE"]["reference_V"] for y in YEARS]
checks.append(("reference V span CU", span(ref_v, 2), (40.37, 85.13)))

# --- E3 objective layers -----------------------------------------------------------
for profile, expected in (
    ("BALANCED", (0.581, 0.730)),
    ("FLIGHT", (0.593, 0.739)),
    ("PASSENGER", (0.547, 0.664)),
    ("RESOURCE", (0.608, 0.772)),
):
    vals = [e3[str(y)]["profile_summary"][profile]["exact_target_agreement_share"] for y in YEARS]
    checks.append((f"{profile} agreement span", span(vals, 3), expected))
act_res = [e3[str(y)]["profile_summary"]["RESOURCE"]["activation_share_joint"] for y in YEARS]
zv_res = [e3[str(y)]["profile_summary"]["RESOURCE"]["zero_recoverable_value_share_joint"] for y in YEARS]
checks.append(("RESOURCE activation span", span(act_res, 3), (0.631, 0.835)))
checks.append(("RESOURCE zero-value span", span(zv_res, 3), (0.165, 0.369)))
mv_pass = [e3[str(y)]["profile_summary"]["PASSENGER"]["median_V_joint"] for y in YEARS]
mv_res = [e3[str(y)]["profile_summary"]["RESOURCE"]["median_V_joint"] for y in YEARS]
checks.append(("PASSENGER median V span", span(mv_pass), (0.0310, 0.2558)))
checks.append(("RESOURCE median V span", span(mv_res), (0.0039, 0.0751)))
du = [e3[str(y)]["profile_summary"][p]["mean_abs_target_change_min"] for y in YEARS for p in ("BALANCED", "FLIGHT", "PASSENGER", "RESOURCE")]
checks.append(("mean |du*| span min", span(du, 2), (1.84, 4.70)))
margins = [e3[str(y)]["profile_summary"][p]["median_decision_margin_joint"] for y in YEARS for p in ("BALANCED", "FLIGHT", "PASSENGER", "RESOURCE")]
checks.append(("median margin span CU", span(margins), (0.0098, 0.0214)))
bal_act = [e3[str(y)]["profile_summary"]["BALANCED"]["activation_share_joint"] for y in YEARS]
bal_zv = [e3[str(y)]["profile_summary"]["BALANCED"]["zero_recoverable_value_share_joint"] for y in YEARS]
bal_mv = [e3[str(y)]["profile_summary"]["BALANCED"]["median_V_joint"] for y in YEARS]
checks.append(("Balanced activation span %", (round(min(bal_act) * 100), round(max(bal_act) * 100)), (82, 92)))
checks.append(("Balanced zero-value span %", (round(min(bal_zv) * 100, 1), round(max(bal_zv) * 100, 1)), (8.4, 17.7)))
checks.append(("Balanced median V span", (round(bal_mv[0], 3), round(bal_mv[1], 3)), (0.018, 0.136)))
pre_act = [e3[str(y)]["profile_summary"]["BALANCED"]["per_stage"]["PRE"]["activation_share_joint"] for y in YEARS]
turn_act = [e3[str(y)]["profile_summary"]["BALANCED"]["per_stage"]["TURN"]["activation_share_joint"] for y in YEARS]
pre_zv = [e3[str(y)]["profile_summary"]["BALANCED"]["per_stage"]["PRE"]["zero_recoverable_value_share_joint"] for y in YEARS]
turn_zv = [e3[str(y)]["profile_summary"]["BALANCED"]["per_stage"]["TURN"]["zero_recoverable_value_share_joint"] for y in YEARS]
checks.append(("PRE activation span", span(pre_act, 2), (0.77, 0.88)))
checks.append(("TURN activation span", span(turn_act, 2), (0.83, 0.93)))
checks.append(("PRE zero-value span", span(pre_zv, 3), (0.115, 0.229)))
checks.append(("TURN zero-value span", span(turn_zv, 3), (0.074, 0.175)))

# --- populations, headroom ---------------------------------------------------------
checks.append(("PRE N span", (min(e1[str(y)]["nominal_q010"]["PRE"]["DELAY"]["n"] for y in YEARS),
                              max(e1[str(y)]["nominal_q010"]["PRE"]["DELAY"]["n"] for y in YEARS)), (675, 1422)))
checks.append(("TURN N span", (min(e1[str(y)]["nominal_q010"]["TURN"]["DELAY"]["n"] for y in YEARS),
                               max(e1[str(y)]["nominal_q010"]["TURN"]["DELAY"]["n"] for y in YEARS)), (3873, 4053)))
checks.append(("PRE K span", (min(e1[str(y)]["nominal_q010"]["PRE"]["DELAY"]["k"] for y in YEARS),
                              max(e1[str(y)]["nominal_q010"]["PRE"]["DELAY"]["k"] for y in YEARS)), (68, 143)))
checks.append(("TURN K span", (min(e1[str(y)]["nominal_q010"]["TURN"]["DELAY"]["k"] for y in YEARS),
                               max(e1[str(y)]["nominal_q010"]["TURN"]["DELAY"]["k"] for y in YEARS)), (388, 406)))
checks.append(("paired cohort span", (min(e2[str(y)]["e2"]["reference_cohort_size"] for y in YEARS),
                                      max(e2[str(y)]["e2"]["reference_cohort_size"] for y in YEARS)), (474, 532)))
tl = [der["headroom"][str(y)]["turnaround_lower_bound_q"] for y in YEARS]
um = [der["headroom"][str(y)]["u_max"] for y in YEARS]
checks.append(("turnaround lower bound list", [int(v) for v in tl], [40, 41, 41, 43, 49, 46]))
checks.append(("u_max list", [int(v) for v in um], [45, 40, 45, 40, 40, 45]))
regime = {
    "pre": [nominal(y, s, "DELAY", "attention_loss") for y in (2017, 2018, 2019) for s in ("PRE", "TURN")],
    "2020": [nominal(2020, "PRE", "DELAY", "attention_loss"), nominal(2020, "TURN", "DELAY", "attention_loss")],
    "recovery": [nominal(y, s, "DELAY", "attention_loss") for y in (2021, 2022) for s in ("PRE", "TURN")],
}
checks.append(("2017-19 PRE mean L_att", round(statistics.fmean([nominal(y, "PRE", "DELAY", "attention_loss") for y in (2017, 2018, 2019)]), 3), 0.133))
checks.append(("2017-19 TURN mean L_att", round(statistics.fmean([nominal(y, "TURN", "DELAY", "attention_loss") for y in (2017, 2018, 2019)]), 3), 0.129))
checks.append(("2020 means", (round(nominal(2020, "PRE", "DELAY", "attention_loss"), 3), round(nominal(2020, "TURN", "DELAY", "attention_loss"), 3)), (0.101, 0.107)))
checks.append(("2021-22 means", (round(statistics.fmean([nominal(y, s, "DELAY", "attention_loss") for y in (2021, 2022) for s in ("PRE", "TURN")]), 3)), 0.169))

# --- literals present in the text --------------------------------------------------
def in_tex(*snippets):
    return all(s in TEX for s in snippets)


checks.append(("Table 3 row 2020 present", in_tex("2020 & 675 & 4\\,053 & 68 & 406 & 4\\,728 & 474"), True))
checks.append(("Table 4 HM 2020 row present", in_tex("& HM--HJ & 0.0127 & 0.0006 [0.0000, 0.0012] & 0.631 & 0.0906 [0.0727, 0.1131]"), True))
checks.append(("Figure includes present",
               in_tex("figure_s5_1_q_boundary.pdf", "figure_s5_2_recoverability.pdf", "figure_s5_3_objectives.pdf"), True))
checks.append(("pending markers retained",
               in_tex("RESULT 5.3-B", "RESULT 5.5-B", "RESULT 5.6-B"), True))
checks.append(("supplement ladder row present", "2020 & 128--2048 & 4\\,096 & N\\_GRID\\_UPPER\\_BOUND\\_REACHED & 11 & 9" in SUP, True))

failures = [(name, got, want) for name, got, want in checks if got != want]
for name, got, want in checks:
    flag = "OK  " if got == want else "FAIL"
    print(f"{flag} {name}: got={got} want={want}")
print()
print(f"{len(checks) - len(failures)}/{len(checks)} checks passed")
if failures:
    raise SystemExit(1)
