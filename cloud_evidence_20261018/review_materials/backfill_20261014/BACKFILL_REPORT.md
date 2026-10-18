# Air Slot — cloud-result backfill (2026-10-14)

Backfill round that writes the finished cloud **Full Experiment** (six operating years,
E1--E4, 18/18 tasks PASS, finished `2026-10-14T09:31:02Z`) back into (a) the manuscript's
empirical-results layer and (b) a `paper_formal`-compatible data tree.

Everything below is derived from audited artifacts only. No quantity was recomputed from
raw data, and no value was inferred where an audited output does not exist — those places
keep an explicit `% RESULT ... pending` marker naming what is missing.

---

## 1. Sources (read-only)

Root: `D:/research/air_slot/airslot_full_execution_snapshot_20261014/artifacts/experiment/jatm_s34/full_20261013/`

| Per year | File | Role |
| --- | --- | --- |
| `e1/{y}/` | `E1_SUMMARY.json`, `E1_CHART_DATA.json`, `chunks/chunk_*.json` | Stage-I screening (4 priorities x 2 stages x q grid), per-node support |
| `e2e3/{y}/` | `E2_E3_SUMMARY.json` | paired representation contrasts (Stage-I + Stage-II), activation events |
| `e2e3/{y}/` | `EXACT_MARGINAL_AUDIT.json` | exact weighted-marginal coupling audit, per-node domain/component scores |
| `e2e3/{y}/` | `E3_OBJECTIVE_ROWS.json`, `E3_MECHANISM_DIAGNOSTICS.json` | objective x representation decisions; mechanism diagnostic |
| `e4/{y}/` | `EVAL_SUMMARY.json`, `E4_DEVELOPMENT_MANIFEST.json` | M5-b cohort-size stability battery |
| baseline | `code/explore/data2/reports/paper_formal/{y}/` | frozen M5-b baseline (reference) |

Per-file SHA-256 for all sources is recorded in
[`data_backfill/CLOUD_BACKFILL_MANIFEST.json`](data_backfill/CLOUD_BACKFILL_MANIFEST.json).
Lineage: server `ubuntu@134.175.205.112`, worktree = snapshot `583f2c12` + patch chain
`d1c72a7`/`ffa7487`, single driver `full_chain.sh`, `final_test_access_count=0` throughout.

## 2. What was backfilled

### 2.1 Manuscript (main text, `sections/05_experiment.tex`)

| Item | Status | Source |
| --- | --- | --- |
| Table 3 — annual evaluation support (PRE/TURN N, PRE/TURN K, full Stage-II eligible, paired Stage-II cohort) | filled | E1 `common_candidate_counts`/`summary_rows`; E2 `reference_cohort_size`; derived full-support counts from `e1/{y}/chunks/` |
| Figure 3 — six-year PRE/TURN screening (displaced share, `L^att` with CIs, review-budget sensitivity) | new figure | E1 `summary_rows` (`q=0.05/0.10/0.20/0.30`) |
| §5.2 prose (RESULT 5.2-A/B, INTERPRETATION 5.2) | written | E1 |
| Figure 4 — activation and recoverable-value distributions, objective-wise activation | new figure (partial scope) | E3 objective rows (Balanced/HJ) |
| §5.3 prose (RESULT 5.3-A) | written | E3 + E2 `reference_recoverable_value` |
| Table 4 — 18 paired contrast rows (Stage-I displaced share, `L^att` [CI], `A0`, `L^rec` [CI]) | filled | E2 `information_value` |
| §5.4 prose (RESULT 5.4-A/B, INTERPRETATION 5.4) incl. component-invariance mechanism | written | E2 + `EXACT_MARGINAL_AUDIT` joined with E1 chunk domain scores |
| Figure 5 — objective x Marginal/Joint | new figure | E3 objective rows |
| §5.5 prose (RESULT 5.5-A, INTERPRETATION 5.5) | written | E3 |
| §5.6 regime/stage heterogeneity (RESULT 5.6-A) | written | E1--E3 annual estimates |

### 2.2 Supplement (`SUPPLEMENT.tex`)

* Filled the six-year support ledger (was an empty schema table) plus new audit tables:
  E1 annual screening detail, E1 review-budget sensitivity, E2 paired Stage-II support
  and activation events, objective-by-distribution support, annual cohort-size battery.
* New subsections: exact weighted-marginal coupling audit (incl. the domain-invariance
  result), recovery-headroom parameters, pending completion items.

### 2.3 Data tree (`data_backfill/`)

`paper_formal`-compatible, one directory per year, **every file prefixed
`CLOUD20261013_` so a copy cannot overwrite the frozen M5-b baseline files**:

```
data_backfill/
  SUPPORT_MATRIX_2017_2022.csv
  CLOUD_BACKFILL_MANIFEST.json           # sources + SHA-256 + conventions + known issues
  year_{2017..2022}/
    CLOUD20261013_E1_SCREENING_Q010.csv        # nominal budget, 4 priorities x 2 stages
    CLOUD20261013_E1_Q_SENSITIVITY.csv         # full q grid
    CLOUD20261013_E2_INFORMATION_VALUE.csv     # 4 paired contrasts incl. CIs and activation events
    CLOUD20261013_E2_STAGE1_ROWS_AS_STORED.csv # as-stored rows (see Defect A)
    CLOUD20261013_E3_OBJECTIVE_SUMMARY.csv     # 4 objectives
    CLOUD20261013_E3_BALANCED_BY_STAGE.csv
    CLOUD20261013_E4_LADDER_RECORD.json
    CLOUD20261013_EXTRACT.json                 # full per-year extraction record
```

To land it in the repository (not executed in this round — the target is the frozen
baseline tree, so it is left as an explicit user action):

```bash
cp -r data_backfill/year_2017/* D:/research/air_slot/code/explore/data2/reports/paper_formal/2017/
# ... and likewise for 2018--2022
```

## 3. Verification performed

| Check | Result |
| --- | --- |
| E4 cloud vs frozen `paper_formal` baseline, all six years | `failed_instances` symmetric difference **0**, identical `protocol_hash` (`sha256:18db92f0...`), identical decision `N_GRID_UPPER_BOUND_REACHED` |
| E2 reference recoverable value vs sum of E3 Balanced/HJ per-case values | exact agreement (|diff| = 0.0) in all six years |
| HJ reference cohort = Stage-I shortlist capacity | `reference_cohort_size == K_PRE + K_TURN` in all six years; no shortlist-to-cohort exclusions |
| E2 stored `reference_shortlist` vs E1 `CONSEQUENCE` shortlist | identical sets, 12/12 year-stages |
| Full-support condition on canonical candidates | `support_mass == 1.0` for 100% of canonical PRE/TURN candidates in all six years |
| Domain scores: Joint vs exact marginal coupling | Flight and Resource identical (<1e-13) in all six years; only Passenger differs (39--66% of nodes) |

## 3b. Automated citation verification

`verify_citations.py` recomputes every quantitative range cited in the backfilled
Section 5 and the supplement's headroom/ladder paragraphs from the extracted records and
compares them with the manuscript text at the precision actually cited. Current result:
**68/68 checks pass**. The checker caught two real errors in the first draft, both fixed:

* the annual TURN zero-recoverable-value range was quoted as 0.074--0.133 (a 2017 value
  used as the six-year maximum); the audited range is **0.074--0.175**;
* the review-budget convergence claim at `q = 0.30` was quoted as "within 0.005"; the
  year-mean gap is **0.0051 (PRE)** and **0.0037 (TURN)**, now stated explicitly.

## 4. Two artifact defects found (do not report these outputs as labelled)

**Defect A — `E2_E3_SUMMARY.e2.stage1_rows` is mislabelled.**
The rows say `comparator: HISTORY_MARGINAL_EXACT`, but they are produced by the legacy
delay-vs-consequence selector: `exp/jatm_section5/attention_value.py::candidate()` defaults
to `HISTORY_JOINT`, and `select_and_evaluate()` hardwires *reference = consequence,
comparator = delay*. Their `comparator_shortlist` reproduces the E1 `DELAY` shortlist
**exactly** in all 12 year-stage settings, and their `L_att` equals the E1 delay `L^att` to
all printed digits. Consequence: these rows must not be reported as HM--HJ Stage-I results;
the valid HM--HJ Stage-I numbers are `information_value.CROSS_STATE_DEPENDENCE`
(paired common-support population). The rows are retained in the backfill tree under the
name `..._STAGE1_ROWS_AS_STORED.csv` for traceability, and the manuscript uses only the
`information_value` quantities.

**Defect B — `E3_MECHANISM_DIAGNOSTICS.json` is degenerate.**
Every row is `threshold_ablation_status = UNCHANGED` and the headroom fields carry only the
annual global parameters, because the mechanism rows are computed on the reference cohort,
which is fully supported by construction (`support_full` filter). It cannot serve as the
threshold x headroom ablation; the manuscript therefore leaves RESULT 5.5-B unfilled and
names the required run.

## 5. Pending items (unfilled by design)

1. **Coverage@K and the priority--recoverability association on the full eligible
   population `C_1`** — requires reference recoverable values outside the annual shortlists.
2. **Threshold x headroom ablation on a cohort that includes partially supported states**
   (Defect B) plus the component-level action-response ledger.
3. **Matched-capacity temporal attribution.** The run compares implemented configurations
   with identical capacity/normalization/protocol/seed differing only in the history-encoder
   mode; a parameter-capacity control remains outstanding.
4. **Within-chain rolling epochs (`C_3`)** — the six-year outputs evaluate canonical epochs only.
5. **Per-node exclusion ledger** (missing data / invalid timing / unsupported probabilistic evaluation).
6. **Cohort-size interpretation wording.** The M5-b battery terminates at the grid upper
   bound in all six years; the defensible statement is "the stability boundary was not
   reached within the evaluated grid", not "4096 is sufficient".

## 6. Deliverables produced by this round

| Path | Content |
| --- | --- |
| `paper/` | backfilled LaTeX source tree (main + supplement + 3 new figures) |
| `paper/main.pdf`, `paper/SUPPLEMENT.pdf` | compiled outputs (28 pp. / 13 pp.) |
| `paper_backfilled_20261014.zip` | source archive equivalent to the Overleaf upload zip |
| `data_backfill/` | `paper_formal`-compatible result tree + manifest (441 KB) |
| `extracted/` | machine-readable extraction records (`e1/e2/e3/e4_six_year.json`, `derived_and_checks.json`) |
| `tables/`, `figures/` | generated LaTeX table bodies and figure PDFs/PNGs |
| `numbers.md` | flat digest of every number cited in the manuscript |
| `extract_six_year.py`, `extract_derived.py`, `build_backfill.py`, `build_data_backfill.py`, `assemble_paper.py` | reproduction scripts (read-only against the snapshot) |

## 7. Headline numbers added to the manuscript

* Screening: expected delay replaces 37--53% (PRE) and 40--55% (TURN) of reference shortlist
  positions with `L^att` = 0.101--0.184 (PRE) / 0.107--0.181 (TURN); passenger exposure
  recovers part of the gap, downstream exposure essentially none (|Delta| <= 0.003).
* Representations (paired): HM--HJ displaces 1.3--3.8% of positions (`L^att` <= 0.0026) and
  `L^rec` = 0.085--0.125; HP--HJ displaces 84--89% (`L^att` = 0.41--0.53, `L^rec` = 0.90--0.98);
  the Point-minus-Marginal increment carries most of the HP--HJ gap.
* Current+Joint collapses in 2020 (`L^att` = 0.506, `A0` = 0.086, `L^rec` = 0.998, 425/474 missed activations).
* Objectives: HM--HJ target agreement 0.547--0.772 depending on emphasis; Passenger emphasis
  least stable, Resource emphasis lowest activation (0.631--0.835).
