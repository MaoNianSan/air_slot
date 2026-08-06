# Isolated Fast Development Chain Audit

Audit date: 2026-08-02

DEV_FAST_CHAIN_STATUS=FAIL

## Existing chain evidence

- PRE 1-thread run `pre-fast-20260802T071319Z-fc0ea135`: PASS.
- overall_run 14-thread run `20260802_160200_fast_three_change_dev_d4aabdf0_6516ede`: engineering core PASS, publication NOT_ALLOWED.
- overall_adv 14-thread run `overall-adv-fast_three_change_dev-20260802T080421Z-a5a18264`: PASS.
- part_adv 14-thread run `part-adv-fast_three_change_dev-20260802T080502Z-510210c6`: PASS.
- Lineage records M1_PREVIOUS_LEG_V1, M3_RESPONSE_V3_EXPANDED_PROVISIONAL, 26 actions, and M4_RANKING_1235_V1_PROVISIONAL.
- Existing stale artifact count is zero in downstream validators.

## Why the required recheck failed

The workflow requires `clean --dry-run fast_three_change_dev` before rerun. The clean CLIs accept only fixed modes and cannot target `fast_three_change_dev`; using `--mode fast` would target formal fast. Therefore no destructive clean and no redundant 14-thread rerun were performed. The existing chain is engineering-valid, but the required safely isolated rerun contract is not satisfied.

Middle and full were not run. Formal baseline was not replaced.
