"""Frozen-source and reporting-only acceptance gates for Section 5."""

import ast
import csv
import io
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from exp.exp2.bootstrap import run_bootstrap
from exp.exp2.priority import rank_base_sample
from exp.exp2.protocol import COMPONENTS
from exp.shared.resampling import bootstrap_plan, episode_ids, expand_draw
from validation import materialize_section5_secondary_robustness as reporting


@pytest.fixture(scope="module")
def published():
    root = reporting.ROOT
    output = root / reporting.OUTPUT
    for name in reporting.OUTPUT_NAMES:
        assert (output / name).is_file(), f"Secondary derivation not materialized: {name}"
    return {
        "manifest": reporting.read_json(output / reporting.OUTPUT_NAMES[3]),
        "summary": reporting.read_csv(output / reporting.OUTPUT_NAMES[0]),
        "draws": reporting.read_csv(output / reporting.OUTPUT_NAMES[5]),
        "audit": reporting.read_json(output / reporting.OUTPUT_NAMES[2]),
        "output": output,
    }


def fixture_sample():
    rows = []
    for episode, delays, consequences in (
        ("A", (0.0, 5.0, 15.0), (5.0, 5.0, 2.0)),
        ("B", (5.0, 10.0, 20.0), (4.0, 1.0, 4.0)),
        ("C", (5.001, 10.001, 20.001), (1.0, 4.0, 4.0)),
    ):
        for node, (delay, consequence) in enumerate(zip(delays, consequences)):
            rows.append({
                "episode_id": episode, "original_episode_id": episode,
                "decision_node_id": f"{episode}{node}",
                "operational_stage": "PRE_IB" if node < 2 else "POST_IB_PRE_OB",
                "delay_to_mean": delay, "score_C": consequence,
                "score_F": consequence, "score_P": consequence,
                "score_R": consequence,
                **{f"Z_{component}": float(node + index + 1)
                   for index, component in enumerate(COMPONENTS)},
                **{f"{component}_native": float(node + index + 1)
                   for index, component in enumerate(COMPONENTS)},
            })
    return rank_base_sample(pd.DataFrame(rows))


def test_frozen_calipers_constants_seed_and_replicates():
    reporting.validate_constants()
    assert reporting.CALIPERS == (5.0, 10.0, 15.0)
    assert reporting.protocol.BOOTSTRAP_REPLICATES == 2000
    assert reporting.protocol.BOOTSTRAP_SEED == 20260906
    assert reporting.CAPACITIES == (0.05, 0.10, 0.20, 0.30)


@pytest.mark.parametrize("caliper", reporting.CALIPERS)
def test_frozen_backend_rebuilds_equivalent_pairs_ranks_and_balance(caliper):
    frame = fixture_sample()
    plan = np.asarray([["A", "A", "B"], ["C", "B", "B"], ["A", "A", "A"]])
    fast = run_bootstrap(frame, replicates=3, seed=20260906,
                         caliper=caliper, plan=plan)
    reference = run_bootstrap(frame, replicates=3, seed=20260906,
                              caliper=caliper, plan=plan, reference=True)
    for actual, expected in zip(fast, reference):
        assert actual["similar_delay"].keys() == expected["similar_delay"].keys()
        for key, value in expected["similar_delay"].items():
            if isinstance(value, (float, int)):
                assert actual["similar_delay"][key] == pytest.approx(
                    value, abs=1e-12, rel=0
                )
            else:
                assert actual["similar_delay"][key] == value
    expanded = rank_base_sample(expand_draw(frame, plan[0]))
    pairs = reporting.build_similar_delay_pairs(expanded, caliper=caliper)
    assert (pairs.original_episode_a != pairs.original_episode_b).all()
    assert not pairs.duplicated(["episode_a", "node_a", "episode_b", "node_b"]).any()
    assert not np.array_equal(
        expanded.consequence_rank_pct.to_numpy(),
        expand_draw(frame, plan[0]).consequence_rank_pct.to_numpy(),
    )


def test_worker_chunks_preserve_seed_plan_and_replicate_ids():
    frame = fixture_sample()
    plan = bootstrap_plan(episode_ids(frame), 4, 20260906)
    whole = reporting._bootstrap_chunk((frame, 10.0, plan, 0))
    split = reporting._bootstrap_chunk((frame, 10.0, plan[:2], 0))
    split += reporting._bootstrap_chunk((frame, 10.0, plan[2:], 2))
    assert whole == split
    assert [row["replicate"] for row in split] == list(range(4))


def test_point_mismatch_fails_closed_before_bootstrap_or_writes(tmp_path):
    points = pd.DataFrame([
        {"caliper_minutes": caliper, "support_status": "SUPPORTED",
         "unique_episode_pairs": 10, "median_priority_separation": 0.2,
         "share_priority_separation_ge_030": 0.3}
        for caliper in reporting.CALIPERS
    ])
    changed = points.copy()
    changed.loc[1, "median_priority_separation"] += 1e-8
    with (
        patch.object(reporting, "preflight", return_value=reporting.AUTHORITY),
        patch.object(reporting, "protected_snapshot", return_value={}),
        patch.object(reporting, "restore_ranked_sample", return_value=pd.DataFrame()),
        patch.object(reporting, "read_csv", return_value=points),
        patch.object(reporting, "rebuild_points", return_value=changed),
        patch.object(reporting, "bootstrap_calipers") as bootstrap,
    ):
        with pytest.raises(RuntimeError, match="POINT_ESTIMATE_MISMATCH:10"):
            reporting.materialize(tmp_path)
        bootstrap.assert_not_called()
        assert not (tmp_path / reporting.OUTPUT).exists()


def test_existing_secondary_directory_is_never_overwritten(tmp_path):
    (tmp_path / reporting.OUTPUT).mkdir(parents=True)
    with patch.object(reporting, "preflight", return_value=reporting.AUTHORITY):
        with pytest.raises(RuntimeError, match="ALREADY_EXISTS_NO_OVERWRITE"):
            reporting.materialize(tmp_path)


def test_protected_file_mutation_is_rejected(tmp_path):
    directory = tmp_path / "artifacts/calibration"
    directory.mkdir(parents=True)
    source = directory / "frozen.json"
    source.write_text('{"frozen": true}', encoding="utf-8")
    with patch.object(reporting, "git", return_value=""):
        before = reporting.protected_snapshot(tmp_path)
        source.write_text('{"frozen": false}', encoding="utf-8")
        with pytest.raises(RuntimeError, match="PROTECTED_FILES_CHANGED"):
            reporting.check_unchanged(before, tmp_path)


def test_capacity_projection_is_verbatim_and_rejects_bad_grid(tmp_path):
    source = reporting.ROOT / reporting.SOURCE_PATHS["capacity"]
    projected = reporting.capacity_projection(source)
    with source.open(newline="", encoding="utf-8") as stream:
        original = list(csv.DictReader(stream))
    expected = [{key: row[key] for key in reporting.CAPACITY_COLUMNS}
                for row in original]
    assert list(csv.DictReader(io.StringIO(projected))) == expected
    bad = tmp_path / "capacity.csv"
    with bad.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=original[0])
        writer.writeheader()
        writer.writerows(original[1:])
    with pytest.raises(RuntimeError, match="CAPACITY_GRID"):
        reporting.capacity_projection(bad)


def test_no_new_scientific_execution_imports():
    tree = ast.parse(Path(reporting.__file__).read_text(encoding="utf-8"))
    modules = [node.module for node in ast.walk(tree)
               if isinstance(node, ast.ImportFrom) and node.module]
    assert not any(name.startswith(("model", "exp.exp4", "formal"))
                   for name in modules)
    assert "exp.exp2.robustness" not in modules


@pytest.mark.parametrize("caliper", reporting.CALIPERS)
def test_published_points_reconcile_all_frozen_calipers(published, caliper):
    frozen = reporting.read_csv(reporting.ROOT / reporting.SOURCE_PATHS["similar"])
    reporting.reconcile_points(published["summary"], frozen)
    actual = published["summary"].set_index("caliper_minutes").loc[caliper]
    expected = frozen.set_index("caliper_minutes").loc[caliper]
    for key in reporting.POINT_KEYS:
        assert actual[key] == pytest.approx(expected[key], abs=1e-12, rel=0)
    for key in reporting.CI_KEYS:
        assert np.isfinite(actual[key + "_ci_low"])
        assert np.isfinite(actual[key + "_ci_high"])
        assert actual[key + "_ci_low"] <= actual[key + "_ci_high"]


def test_published_2000_draws_seed_plan_and_primary_ci_reconciliation(published):
    summary, draws = published["summary"], published["draws"]
    manifest = published["manifest"]
    assert manifest["bootstrap_replicates"] == 2000
    assert manifest["bootstrap_seed"] == 20260906
    assert manifest["bootstrap_cluster"] == "original_episode_id"
    assert manifest["bootstrap_ci"] == "percentile_95"
    assert summary.bootstrap_replicates.eq(2000).all()
    assert summary.bootstrap_seed.eq(20260906).all()
    assert manifest["bootstrap_replicates_completed_per_caliper"] == {
        "5.0": 2000, "10.0": 2000, "15.0": 2000,
    }
    restored = reporting.attach_intervals(
        summary, draws,
        reporting.read_csv(reporting.ROOT / reporting.SOURCE_PATHS["similar"]),
        reporting.read_csv(reporting.ROOT / reporting.SOURCE_PATHS["primary_bootstrap"]),
    )
    pd.testing.assert_frame_equal(summary, restored, check_exact=True)
    plan = bootstrap_plan(
        episode_ids(reporting.restore_ranked_sample()), 2000, 20260906
    )
    import hashlib
    expected_hash = "sha256:" + hashlib.sha256(
        reporting.json_text(plan.tolist()).encode("utf-8")
    ).hexdigest()
    assert manifest["bootstrap_draw_plan_sha256"] == expected_hash


def test_published_exp4_equals_source_fields_and_capacity_grid(published):
    path = published["output"] / reporting.OUTPUT_NAMES[1]
    assert path.read_text(encoding="utf-8") == reporting.capacity_projection(
        reporting.ROOT / reporting.SOURCE_PATHS["capacity"]
    )
    frame = reporting.read_csv(path)
    for _, group in frame.groupby("stage"):
        assert len(group) == 4
        assert set(group.q) == {0.05, 0.10, 0.20, 0.30}
    assert published["manifest"]["exp4_rerun"] is False


def test_published_audit_reads_existing_rows_without_new_score(published):
    audit = published["audit"]
    source = reporting.read_csv(reporting.ROOT / reporting.SOURCE_PATHS["robustness"])
    expected = reporting.exact_records(
        source.loc[source.robustness_id.eq("NO_F_EXECUTION")]
    )[0]
    assert audit["no_f_execution"]["row"] == expected
    assert audit["no_f_execution"]["audit_row_recomputed"] is False
    assert audit["no_f_execution"]["new_definition"] is False
    assert audit["delay_stripped_score_created"] is False
    assert audit["primary"]["row"] == reporting.exact_records(
        reporting.read_csv(reporting.ROOT / reporting.SOURCE_PATHS["primary"])
    )[0]
    assert audit["component_domain_association"]["rows"] == reporting.exact_records(
        reporting.read_csv(reporting.ROOT / reporting.SOURCE_PATHS["association"])
    )
    assert audit["preserved_source_abstentions"]
    assert all(item["status"] == "ABSTAIN_UNSUPPORTED_OR_ZERO_DENOMINATOR"
               for item in audit["preserved_source_abstentions"])


def test_published_hashes_model_calibration_parameters_and_primary_unchanged(published):
    manifest = published["manifest"]
    assert manifest["HEAD_START"] == manifest["HEAD_END"] == reporting.git(
        "rev-parse", "HEAD"
    )
    reporting.check_unchanged(manifest["protected_file_hashes"])
    assert any(path.startswith("model/") for path in manifest["protected_file_hashes"])
    assert any(path.startswith("artifacts/calibration/")
               for path in manifest["protected_file_hashes"])
    for path, value in manifest["source_artifact_hashes"].items():
        assert reporting.digest(reporting.ROOT / path) == value
    for path, value in manifest["implementation_hashes"].items():
        assert reporting.digest(reporting.ROOT / path) == value
    for name, value in manifest["output_artifact_hashes"].items():
        assert reporting.digest(published["output"] / name) == value
    for key, value in reporting.GUARDS.items():
        assert manifest[key] is value
    assert manifest["final_test_access_count_before"] == 1
    assert manifest["final_test_access_count_after"] == 1
    assert manifest["remaining_blocked_items"] == []
