
        # Cloud Full Readiness (Read Only)

        ```text
        CLOUD_READY=true
        CLOUD_START_STAGE=PRE acceptance_23d
        PURPOSE=EVIDENCE_EXPANSION_AND_FINAL_EVALUATION
        FULL_RECOMMENDED=false
        RUN_STARTED=false
        ```

        PRE acceptance_23d and PRE full artifacts are distinct. PRE Fast is valid only for Fast and must not be supplied to an acceptance_23d/full run. The 23-anchor-day engineering gate starts at `pre/main.py acceptance_23d`.

        ## Resources and workers

        - Start with `--n-jobs 2`; use at most 4 initially and never `-1`.
        - Run PRE, overall_run, overall_adv and part_adv sequentially.
        - Provision at least 250 GB volume, leaving at least 100 GB free after syncing data and cache.
        - Minimum memory is 32 GB; 64 GB is recommended.
        - Current data are 85,406,294,155 bytes; PRE cache is 952,629,606 bytes.
        - The current workstation has only 158,362,693,632 free bytes and is not the long-run target.

        ## Clean order

        Inspect with `--dry-run`, then clean only `acceptance_23d` in this order: `part_adv`, `overall_adv`, `overall_run`, `pre`. Stop for unknown workers, locks, staging, partial artifacts or stale checkpoints.

        ## Commands (not executed)

        ```powershell
        python -u pre/main.py acceptance_23d --progress normal --n-jobs 2
python -u pre/main.py validate acceptance_23d --progress normal --n-jobs 2
python -u overall_run/main.py acceptance_23d --progress normal --n-jobs 2
python -u overall_run/main.py validate acceptance_23d --progress normal --n-jobs 2
python -u overall_adv/main.py acceptance_23d --progress normal --n-jobs 2
python -u overall_adv/main.py validate --mode acceptance_23d --progress normal --n-jobs 2
python -u part_adv/main.py acceptance_23d --progress normal --n-jobs 2
python -u part_adv/main.py validate --mode acceptance_23d --progress normal --n-jobs 2
        ```

        ## Checkpoint and recovery

        overall_run supports an explicit staging resume path. Advantage modules support hash-valid resume. Resume is prohibited when input, scientific config, target contract, task partition or output hashes differ. Clean and restart only the failed mode when resume validation fails.

        ## Boundaries

        This run is only for `EVIDENCE_EXPANSION_AND_FINAL_EVALUATION`. It is not parameter selection, retuning or threshold optimization. Formal 72-day Full and Precision remain unauthorized. No command in this report was executed.
