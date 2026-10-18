import hashlib
import json
from pathlib import Path

from exp.jatm_s34 import e4_run, q4_year_run
from exp.jatm_s34.q4_bridge import Q4CacheView


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_q4_e4_reuses_frozen_models_and_runs_eval_only(tmp_path, monkeypatch):
    q4_root = tmp_path / "q4"
    frozen_root = tmp_path / "frozen_e4"
    calls = []
    years = (2017, 2018, 2019)
    for year in years:
        cohort = q4_root / str(year) / "cohort"
        cohort.mkdir(parents=True)
        (cohort / "Q4_COHORT_MANIFEST.json").write_text("{}", encoding="utf-8")
        year_root = frozen_root / str(year)
        (year_root / f"LADDER_PROBE_{year}.json").parent.mkdir(parents=True)
        (year_root / f"LADDER_PROBE_{year}.json").write_text(
            json.dumps({"status": "PASS", "evaluation_E": 4096}), encoding="utf-8"
        )
        headroom = year_root / str(year) / "M2_TRAIN_HEADROOM_SUMMARY.json"
        headroom.parent.mkdir(parents=True)
        headroom.write_text("{}", encoding="utf-8")
        model = headroom.parent / "N128" / "M1_N.pt"
        model.parent.mkdir(parents=True)
        model.write_bytes(f"frozen model {year}".encode())
        (model.parent / "M1_N_HASHES.json").write_text(
            json.dumps({"checkpoint_hash": _sha(model)}), encoding="utf-8"
        )

    def fake_phase(**kwargs):
        calls.append(kwargs["phase"])
        scoped = kwargs["output_root"] / f"YEAR_{kwargs['year']}"
        scoped.mkdir(parents=True, exist_ok=True)
        (scoped / "EVAL_SUMMARY.json").write_text(
            json.dumps({"years": {str(kwargs["year"]): {"eval": {"128": {}}}}}),
            encoding="utf-8",
        )

    monkeypatch.setattr(e4_run, "_run_phase", fake_phase)
    result = e4_run.run(
        repo=tmp_path,
        output_root=tmp_path / "output",
        bundle_root=tmp_path / "bundles",
        years=years,
        n_grid=(128,),
        q4_cohort_root=q4_root,
        frozen_e4_root=frozen_root,
    )
    assert calls == ["eval"] * len(years)
    assert result["split"] == "test"
    assert all(row["status"] == "TEST_COMPLETE" for row in result["years"])


def test_q4_cache_view_only_serves_test_split():
    view = Q4CacheView(["episode"], normalization={}, static_normalization={})
    assert view.partition("test") == ("episode",)
    try:
        view.partition("development")
    except ValueError as error:
        assert "Q4_CACHE_SPLIT_INVALID" in str(error)
    else:
        raise AssertionError("Q4 cache accepted a non-Test partition")


def test_q4_year_runner_freezes_once_then_runs_e1_e2e3_e4(tmp_path, monkeypatch):
    calls = []
    cohort = {
        "selected_episode_count": 4096,
        "eligible_episode_count": 4300,
        "selected_ids_sha256": "abc",
        "source_hashes": {},
        "q4_raw_rows_read": 12,
        "september_context_rows_read": 4,
        "final_test_access_count": 12,
    }
    monkeypatch.setattr(q4_year_run, "select_q4_cohort", lambda **kwargs: cohort)
    monkeypatch.setattr(q4_year_run, "iter_q4_bridges", lambda **kwargs: iter(()))

    def fake_e1(**kwargs):
        calls.append(("E1", kwargs["evaluation_split"], kwargs["final_test_access_count"]))
        assert len(list(kwargs["bridge_factory"](year=2017, n=4096, chunk_size=64))) == 0
        return {"status": "TEST_COMPLETE", "artifact_hash": "e1", "node_count": 0}

    def fake_e2(**kwargs):
        calls.append(("E2_E3", kwargs["evaluation_split"], kwargs["final_test_access_count"]))
        return {"status": "TEST_COMPLETE", "artifact_hash": "e2", "node_count": 0}

    def fake_e4(**kwargs):
        calls.append(("E4", "test", len(kwargs["years"])))
        return {"status": "TEST_COMPLETE"}

    monkeypatch.setattr(q4_year_run, "run_e1", fake_e1)
    monkeypatch.setattr(q4_year_run, "run_e2_e3", fake_e2)
    monkeypatch.setattr(q4_year_run, "run_e4", fake_e4)
    result = q4_year_run.run_year(
        repo=tmp_path, results_root=tmp_path / "results",
        frozen_e4_root=tmp_path / "frozen", bundle_root=tmp_path / "bundles",
        year=2017,
    )
    assert result["status"] == "TEST_COMPLETE"
    assert [row[0] for row in calls] == ["E1", "E2_E3", "E4"]
    assert calls[0][1:] == ("test", 4096)
    assert calls[1][1:] == ("test", 8192)
