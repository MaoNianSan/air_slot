import hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path

B = Path("/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013")
REPO = Path("/data/airslot/worktree")
FULL = REPO / "artifacts/experiment/jatm_s34/full_20261013"
YEARS = [2017, 2018, 2019, 2020, 2021, 2022]

def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def task_records(tag):
    td = B / "tasks" / tag
    meta = (td / "meta").read_text(encoding="utf-8") if (td / "meta").is_file() else ""
    get = lambda k: next((l.split("=", 1)[1] for l in meta.splitlines() if l.startswith(k + "=")), "")
    tv = (td / "time_v.txt").read_text(encoding="utf-8") if (td / "time_v.txt").is_file() else ""
    wall = next((l.split(": ", 1)[1] for l in tv.splitlines() if "Elapsed (wall clock)" in l), "")
    rss = next((l.split(": ", 1)[1] for l in tv.splitlines() if "Maximum resident" in l), "")
    return {"status": (td / "status").read_text(encoding="utf-8").strip() if (td / "status").is_file() else "MISSING",
            "exit_code": (td / "exitcode").read_text(encoding="utf-8").strip() if (td / "exitcode").is_file() else "",
            "started_at": get("started_at"), "finished_at": get("finished_at"),
            "wall": wall, "peak_rss_kib": rss}

report = {"schema_version": "AIRSLOT_FULL_EXECUTION_VALIDATION_V1",
          "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
          "chain": {"started": "2026-10-13T13:40:50Z", "completed": "2026-10-14T09:31:02Z",
                    "wall": "19h50m12s", "final_test_access_count": 0},
          "experiments": {"E4": {}, "E2E3": {}, "E1": {}}}

all_pass = True
for y in YEARS:
    ys = str(y)
    # ---- E4 ----
    d4 = FULL / "e4" / ys
    st = json.loads((d4 / f"YEAR_{y}" / "E4_YEAR_STATE.json").read_text(encoding="utf-8"))
    ev = json.loads((d4 / "EVAL_SUMMARY.json").read_text(encoding="utf-8"))
    man = json.loads((d4 / "E4_DEVELOPMENT_MANIFEST.json").read_text(encoding="utf-8"))
    ckpt = sorted((d4 / ys).glob("N*/M1_N.pt"))
    fit_pass = sorted(d4.glob(f"FIT_METRICS_{y}_N*.json"))
    eval_met = sorted(d4.glob(f"EVAL_METRICS_{y}_N*.json"))
    checks = {
        "phases_complete": st.get("completed_phases") == ["headroom", "fit", "ladder", "eval"],
        "six_checkpoints": len(ckpt) == 6,
        "fit_metrics_5plus": len(fit_pass) >= 5,
        "eval_metrics_6": len(eval_met) == 6,
        "eval_decision_present": bool((ev.get("decision") or {}).get("status")),
        "terminal_is_development_complete": st.get("status") == "DEVELOPMENT_COMPLETE",
        "grid_observed_full": bool((st.get("n_grid_coverage") or {}).get("full_default_grid_observed")),
        "test_access_zero": man.get("test_access_count") == 0,
    }
    report["experiments"]["E4"][ys] = {
        "task": task_records(f"e4_full_{ys}"), "checks": checks,
        "terminal_status": st.get("status"), "completion_class": st.get("completion_class"),
        "eval_decision": (ev.get("decision") or {}).get("status"),
        "n_grid_coverage": st.get("n_grid_coverage"),
        "artifact_sha256": {"E4_YEAR_STATE": sha(d4 / f"YEAR_{y}" / "E4_YEAR_STATE.json"),
                            "EVAL_SUMMARY": sha(d4 / "EVAL_SUMMARY.json"),
                            "E4_DEVELOPMENT_MANIFEST": sha(d4 / "E4_DEVELOPMENT_MANIFEST.json")},
        "checkpoint_hashes": {p.parent.name: sha(p) for p in ckpt},
        "failed_instances_count": len((ev.get("decision") or {}).get("failed_instances") or []),
        "failed_instances_sha256": hashlib.sha256(json.dumps(sorted((ev.get("decision") or {}).get("failed_instances") or []), sort_keys=True).encode()).hexdigest(),
    }
    # ---- E2/E3 ----
    d2 = FULL / "e2e3" / ys
    s2 = json.loads((d2 / "E2_E3_SUMMARY.json").read_text(encoding="utf-8"))
    ok2 = {"status_complete": s2.get("status") == "DEVELOPMENT_COMPLETE",
           "two_pass_checkpoints": (d2 / "E2_E3_FIRST_PASS_CHECKPOINT.json").is_file() and (d2 / "E2_E3_SECOND_PASS_CHECKPOINT.json").is_file(),
           "fta_zero": (s2.get("input_contract") or {}).get("final_test_access_count") == 0}
    report["experiments"]["E2E3"][ys] = {
        "task": task_records(f"e2e3_full_{ys}"), "checks": ok2,
        "node_count": s2.get("node_count"), "chunk_count": s2.get("chunk_count"),
        "second_pass_chunk_count": s2.get("second_pass_chunk_count"),
        "artifact_sha256": {"E2_E3_SUMMARY": sha(d2 / "E2_E3_SUMMARY.json"),
                            "FIRST_PASS": sha(d2 / "E2_E3_FIRST_PASS_CHECKPOINT.json"),
                            "SECOND_PASS": sha(d2 / "E2_E3_SECOND_PASS_CHECKPOINT.json")},
    }
    # ---- E1 ----
    d1 = FULL / "e1" / ys
    s1 = json.loads((d1 / "E1_SUMMARY.json").read_text(encoding="utf-8"))
    chunks = sorted((d1 / "chunks").glob("chunk_*.json"))
    ok1 = {"status_complete": s1.get("status") == "DEVELOPMENT_COMPLETE",
           "chunk_count_64": len(chunks) == 64,
           "checkpoint_file": (d1 / "E1_CHUNK_CHECKPOINT.json").is_file(),
           "fta_zero": s1.get("final_test_access_count") == 0}
    report["experiments"]["E1"][ys] = {
        "task": task_records(f"e1_full_{ys}"), "checks": ok1,
        "node_count": s1.get("node_count"), "chunk_count": len(chunks),
        "artifact_sha256": {"E1_SUMMARY": sha(d1 / "E1_SUMMARY.json"),
                            "E1_CHUNK_CHECKPOINT": sha(d1 / "E1_CHUNK_CHECKPOINT.json")},
    }
    for exp in ("E4", "E2E3", "E1"):
        entry = report["experiments"][exp][ys]
        entry["verdict"] = "PASS" if all(entry["checks"].values()) and entry["task"]["status"] == "PASS" else "FAIL"
        if entry["verdict"] != "PASS":
            all_pass = False

report["all_pass"] = all_pass
(B / "FULL_EXECUTION_VALIDATION_REPORT.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("written FULL_EXECUTION_VALIDATION_REPORT.json | all_pass:", all_pass)
print(f"{'year':6s}{'E4':6s}{'E2E3':6s}{'E1':6s} | E4 wall/peak | E2E3 wall/peak | E1 wall/peak")
for y in YEARS:
    ys = str(y)
    r4, r2, r1 = report["experiments"]["E4"][ys], report["experiments"]["E2E3"][ys], report["experiments"]["E1"][ys]
    print(f"{ys:6s}{r4['verdict']:6s}{r2['verdict']:6s}{r1['verdict']:6s} | {r4['task']['wall']}/{r4['task']['peak_rss_kib']} | {r2['task']['wall']}/{r2['task']['peak_rss_kib']} | {r1['task']['wall']}/{r1['task']['peak_rss_kib']}")
