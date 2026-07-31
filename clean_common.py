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
    mode,
    all_output,
    dry_run,
    stop_owned_processes=False,
):
    if all_output:
        selected_mode = "ALL_OUTPUT"
        target = output_root
    else:
        if mode not in supported_modes:
            raise CleanBoundaryError(f"INVALID_MODE:{mode}")
        selected_mode = str(mode)
        target = output_root / selected_mode

    resolved = validate_target(
        target,
        output_root=output_root,
        project_root=project_root,
        data_root=data_root,
        pre_cache_root=pre_cache_root,
        allow_output_root=all_output,
    )
    workers = find_active_workers(target, all_output, module_root)
    if workers and not stop_owned_processes:
        raise CleanBoundaryError("ACTIVE_WORKERS:" + ",".join(str(row["pid"]) for row in workers))
    if workers and stop_owned_processes:
        stop_verified_workers(workers, module_root)

    inventory = inventory_target(target, remove_root=not all_output)
    payload: dict[str, Any] = {
        "module": module_root.name,
        "selected_mode": selected_mode,
        "resolved_output_path": str(resolved),
        "files_removed": 0,
        "directories_removed": 0,
        "bytes_removed": 0,
        "files_selected": inventory["files"],
        "directories_selected": inventory["directories"],
        "bytes_selected": inventory["bytes"],
        "cache_preserved": True,
        "data_preserved": True,
        "active_worker_count": len(workers),
        "status": "NOTHING_TO_CLEAN" if not target.exists() else ("DRY_RUN" if dry_run else "CLEAN_PASS"),
    }
    if dry_run or not target.exists():
        payload.update(count_residuals(target))
        return payload

    if all_output:
        for child in tuple(target.iterdir()):
            if child.is_symlink() or child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
    else:
        shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)

    payload.update(
        files_removed=inventory["files"],
        directories_removed=inventory["directories"],
        bytes_removed=inventory["bytes"],
        active_worker_count=0,
    )
    payload.update(count_residuals(target))
    if any(payload[key] for key in (
        "active_worker_count",
        "lock_file_count",
        "staging_file_count",
        "partial_artifact_count",
        "stale_checkpoint_count",
    )):
        raise RuntimeError("CLEAN_RESIDUAL_ARTIFACTS")
    return payload