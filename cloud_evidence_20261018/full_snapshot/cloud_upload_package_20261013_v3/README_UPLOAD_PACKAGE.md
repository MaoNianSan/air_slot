# Air Slot / JATM cloud upload package

- Source Git HEAD: `583f2c12d54297ce6522285b44ff8bf008587308`
- Source SHA-256: `sha256:4e8e64b6aa74b4f7be0b3c9fbb022920b3b24a50f6d0a347d35b7858554abb4d`
- Continuity contract: `JATM_F_CONTINUITY_B_V1`
- Stage-II coordinate: `JATM_STAGE2_SIGNED_T_IB_V1`
- Status: `CLOUD_UPLOAD_PACKAGE_BUILT` / `SIX_YEAR_EXECUTION_BLOCKED`
- Cloud/network transfer: not performed
- Full Development: not started
- Test/Final-Test access: 0

The source archive does not contain `.git`. After extraction to a repository root, bind its reviewed identity using:

```bash
python deploy/jatm_cloud/prepare_source_snapshot.py --root . --git-head 583f2c12d54297ce6522285b44ff8bf008587308 --source-archive-sha256 sha256:4e8e64b6aa74b4f7be0b3c9fbb022920b3b24a50f6d0a347d35b7858554abb4d
```

`inputs/DATA_TRANSFER_MANIFEST.json` is only a 439-file, 14.73 GiB data allowlist, not the data itself. Raw/model inputs and generated B reference bundles are not embedded. The companion transfer progress file disagrees with the manifest (429 vs 439 files); reconcile it before transfer. Current annual blockers are in `checks/B_CONTINUITY_INPUT_GATE.json`.

Verify `CHECKSUMS.sha256` before use. Transfer the approved annual data closure separately, then run `cloud_verify` and the B-contract input gate. No cloud execution is authorized by this package.
