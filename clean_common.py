from __future__ import annotations


import json
import os
import shutil
from pathlib import Path
from typing import Any

class CleanBoundaryError(RuntimeError):
    pass

def inventory_target(target, *, remove_root):
    if not target.exists():
        return {"files": 0, "directories": 0, "bytes": 0}
    files = 0
    directories = 1 if remove_root else 0
    size = 0
    for entry in target.rglob("*"):
        if entry.is_symlink() or entry.is_file():
            files += 1
            if entry.is_file() and not entry.is_symlink():
                size += entry.stat().st_size
        elif entry.is_dir():
            directories += 1
    return {"files": files, "directories": directories, "bytes": size}

def find_run_states(target, all_output):
    if not target.exists():
        return []
    if all_output:
        return sorted(target.glob("*/run_state.json"))
    state = target / "run_state.json"
    return [state] if state.exists() else []

def count_residuals(target):
    if not target.exists():
        return {
            "lock_file_count": 0,
            "staging_file_count": 0,
            "partial_artifact_count": 0,
            "stale_checkpoint_count": 0,
        }
    files = [path for path in target.rglob("*") if path.is_file()]
    return {
        "lock_file_count": sum(path.suffix == ".lock" or "lock" in path.name.lower() for path in files),
        "staging_file_count": sum(
            any(part.lower() in {"staging", ".staging", "workers"} for part in path.parts)
            for path in files
        ),
        "partial_artifact_count": sum(
            path.suffix in {".tmp", ".partial"} or "partial" in path.name.lower()
            for path in files
        ),
        "stale_checkpoint_count": sum("checkpoint" in {part.lower() for part in path.parts} for path in files),
    }

def find_incomplete_mode_staging(output_root, mode):
    staging_root = output_root / ".staging"
    matches = []
    if not staging_root.is_dir():
        return matches
    for state_path in staging_root.glob("*/run_state.json"):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if state.get("mode") == mode and state.get("status") == "INCOMPLETE":
            matches.append(state_path.parent)
    return sorted(matches)

def sum_inventory(targets, *, remove_roots):
    total = {"files": 0, "directories": 0, "bytes": 0}
    for target, remove_root in zip(targets, remove_roots):
        inventory = inventory_target(target, remove_root=remove_root)
        for key in total:
            total[key] += inventory[key]
    return total

def sum_residuals(targets):
    total = {
        "lock_file_count": 0,
        "staging_file_count": 0,
        "partial_artifact_count": 0,
        "stale_checkpoint_count": 0,
    }
    for target in targets:
        residuals = count_residuals(target)
        for key in total:
            total[key] += residuals[key]
    return total

def selected_files(targets):
    files = []
    for target in targets:
        if target.is_file() or target.is_symlink():
            files.append(str(target.resolve(strict=False)))
        elif target.exists():
            files.extend(
                str(path.resolve(strict=False))
                for path in target.rglob("*")
                if path.is_file() or path.is_symlink()
            )
    return sorted(set(files))

def validate_output_id(output_id, registered_output_ids):
    value = str(output_id or "")
    candidate = Path(value)
    if (
        not value
        or candidate.is_absolute()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or ".." in candidate.parts
    ):
        raise CleanBoundaryError(f"INVALID_OUTPUT_ID:{value}")
    if value not in set(registered_output_ids):
        raise CleanBoundaryError(f"UNKNOWN_OUTPUT_ID:{value}")
    return value

def validate_target(target, *, output_root, project_root, data_root, pre_cache_root, allow_output_root):
    resolved = target.resolve(strict=False)
    output_root = output_root.resolve(strict=False)
    protected = {
        project_root.resolve(strict=False),
        data_root.resolve(strict=False),
        pre_cache_root.resolve(strict=False),
        Path(resolved.anchor).resolve(strict=False),
    }
    if not resolved.is_relative_to(output_root):
        raise CleanBoundaryError(f"TARGET_OUTSIDE_MODULE_OUTPUT:{resolved}")
    if resolved == output_root and not allow_output_root:
        raise CleanBoundaryError(f"output_root_REQUIRES_ALL_OUTPUT:{resolved}")
    if resolved in protected:
        raise CleanBoundaryError(f"PROTECTED_TARGET:{resolved}")
    if target.is_symlink():
        raise CleanBoundaryError(f"SYMLINK_TARGET_REJECTED:{target}")
    if target.exists():
        for entry in target.rglob("*"):
            if entry.is_symlink():
                destination = entry.resolve(strict=False)
                if not destination.is_relative_to(output_root):
                    raise CleanBoundaryError(f"SYMLINK_ESCAPE:{entry}->{destination}")
                raise CleanBoundaryError(f"SYMLINK_OUTPUT_REJECTED:{entry}")
    return resolved

def find_active_workers(target, all_output, module_root):
    try:
        import psutil
    except ImportError:
        return []
    active = []
    for state_path in find_run_states(target, all_output):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("status") != "RUNNING":
            continue
        pid = int(state.get("process_id") or 0)
        if pid <= 0 or pid == os.getpid() or not psutil.pid_exists(pid):
            continue
        active.append({
            "pid": pid,
            "mode": str(state.get("mode") or state_path.parent.name),
            "run_id": str(state.get("run_id") or ""),
            "state_path": str(state_path),
        })
    return active

def stop_verified_workers(workers, module_root):
    import psutil

    for worker in workers:
        process = psutil.Process(worker["pid"])
        command = " ".join(process.cmdline()).lower()
        environment = process.environ()
        expected_main = str(module_root / "main.py").lower()
        owned = (
            (expected_main in command or f"{module_root.name}/main.py" in command.replace("\\", "/"))
            and worker["mode"].lower() in command
            and environment.get("AIR_SLOT_RUN_ID") == worker["run_id"]
            and environment.get("AIR_SLOT_MODULE") == module_root.name
        )
        if not owned:
            raise CleanBoundaryError(f"PROCESS_OWNERSHIP_UNVERIFIED:{worker['pid']}")
        process.terminate()
        process.wait(timeout=15)

def execute_clean(
    *,
    module_root,
    output_root,
    project_root,
    data_root,
    pre_cache_root,
    supported_modes,
    registered_output_ids,
    mode,
    output_id,
    all_output,
    dry_run,
    stop_owned_processes=False,
):
    selected_count = sum(value is not None and value is not False for value in (mode, output_id))
    if all_output:
        selected_count += 1
    if selected_count != 1:
        raise CleanBoundaryError("CLEAN_SELECTION_REQUIRES_EXACTLY_ONE_TARGET")
    if all_output:
        selected_mode = "ALL_OUTPUT"
        target = output_root
        cleanup_targets = [target]
        remove_roots = [False]
    elif output_id is not None:
        selected_mode = validate_output_id(output_id, registered_output_ids)
        target = output_root / selected_mode
        cleanup_targets = [target, *find_incomplete_mode_staging(output_root, selected_mode)]
        remove_roots = [True] * len(cleanup_targets)
    else:
        if mode not in supported_modes:
            raise CleanBoundaryError(f"INVALID_MODE:{mode}")
        selected_mode = str(mode)
        target = output_root / selected_mode
        cleanup_targets = [target, *find_incomplete_mode_staging(output_root, selected_mode)]
        remove_roots = [True] * len(cleanup_targets)

    resolved_targets = [
        validate_target(
            candidate,
            output_root=output_root,
            project_root=project_root,
            data_root=data_root,
            pre_cache_root=pre_cache_root,
            allow_output_root=all_output and candidate == output_root,
        )
        for candidate in cleanup_targets
    ]
    resolved = resolved_targets[0]
    workers = []
    for candidate in cleanup_targets:
        workers.extend(find_active_workers(candidate, all_output and candidate == output_root, module_root))
    if workers and not stop_owned_processes:
        raise CleanBoundaryError("ACTIVE_WORKERS:" + ",".join(str(row["pid"]) for row in workers))
    if workers and stop_owned_processes:
        stop_verified_workers(workers, module_root)

    inventory = sum_inventory(cleanup_targets, remove_roots=remove_roots)
    anything_exists = any(candidate.exists() for candidate in cleanup_targets)
    payload: dict[str, Any] = {
        "module": module_root.name,
        "selected_mode": selected_mode,
        "resolved_output_path": str(resolved),
        "resolved_incomplete_staging_paths": [
            str(path) for path in resolved_targets[1:]
        ],
        "files_removed": 0,
        "directories_removed": 0,
        "bytes_removed": 0,
        "files_selected": inventory["files"],
        "directories_selected": inventory["directories"],
        "bytes_selected": inventory["bytes"],
        "cache_preserved": True,
        "data_preserved": True,
        "active_worker_count": len(workers),
        "status": "NOTHING_TO_CLEAN" if not anything_exists else ("DRY_RUN" if dry_run else "CLEAN_PASS"),
    }
    if dry_run or not anything_exists:
        if dry_run:
            payload["selected_files"] = selected_files(cleanup_targets)
        payload.update(sum_residuals(cleanup_targets))
        return payload

    if all_output:
        for child in tuple(target.iterdir()):
            if child.is_symlink() or child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
    else:
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        for staging_target in cleanup_targets[1:]:
            if staging_target.exists():
                shutil.rmtree(staging_target)

    payload.update(
        files_removed=inventory["files"],
        directories_removed=inventory["directories"],
        bytes_removed=inventory["bytes"],
        active_worker_count=0,
    )
    payload.update(sum_residuals(cleanup_targets))
    if any(payload[key] for key in (
        "active_worker_count",
        "lock_file_count",
        "staging_file_count",
        "partial_artifact_count",
        "stale_checkpoint_count",
    )):
        raise RuntimeError("CLEAN_RESIDUAL_ARTIFACTS")
    return payload
