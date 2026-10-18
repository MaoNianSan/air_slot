# 2019 B CU 修复差异与测试报告（第三轮任务 B）

- 本地提交：`ffa74876bf3c4dfa7031da06e59bf91a0f2899ef`（v2/paper-primary，2026-10-13 15:16 +0800）
- 云端补丁：`/data/airslot/patches/20261013_bcu2019_context_fix.patch`
  sha256 `1d3ba5d32b243773201eb924aa1a3aca6fe1443ead60af6184d872b03a02fdbb`
- 快照身份未变：仍为 `583f2c12` + 补丁链（`8cc7a1b7`/d1c72a7 → `1d3ba5d3`/ffa7487）

## 变更全文（功能性）

1. `model/PRE/reference/data2_m2_train_fit.py`
   - `fit_train_references(...)` 新增可选参数 `dataset_instance_id: str | None = None`；
     `reference_dataset_id = dataset_instance_id or ("data2_2019" if year == 2019 else "data2_2017_2022")`。
   - turnaround / downstream_exposure 继续接收 `reference_dataset_id`（路由本身不变）。
   - passenger：`stream_passenger_routes(..., dataset_instance_id=dataset_instance_id)`；
     `build_data2_passenger_reference(..., dataset_instance_id=reference_dataset_id)`。
   - `stream_passenger_routes(...)` 新增可选参数 `dataset_instance_id`（缺省 None → 保持年基旧行为）。
2. `data2/scripts/build_year_references.py`
   - 构建器调用改为 `fit_train_references(..., dataset_instance_id=INSTANCE_ID)`。

**未改动**：taxi 分支（2019→v5 冻结件、其余年份重拟合）、任何数据筛选、七项 consequence、
F_continuity 公式、归一化/序列化定义、参考规则注册表、Legacy 调用方（`model/M2/cu/registry.py`
不传新参数 → 完全保持原行为）。

## 行为矩阵（修复后）

| 调用方 | rows 身份 | dataset_instance_id 入参 | turnaround/exposure/passenger 期望 | taxi 来源 |
|---|---|---|---|---|
| Legacy registry（M2 V4 物化） | data2_2019 | 无 → 默认 | data2_2019（不变） | 2019→v5 冻结件；其余→按年 PM 旧行为…（该路径仅 2019） |
| Year-local 构建器（B/D4 束） | data2_2017_2022 | `INSTANCE_ID` | data2_2017_2022（2019 冲突消除） | 2019→v5 冻结件（保持）；其余年份重拟合（保持） |

## 测试证据

- 本地焦点批次：**24 passed**（新 `tests/m2/test_bcu_2019_construction_context.py` 11 项 +
  round-1 回归 + `test_freeze_registry` + `test_jatm_continuity_b_v1`）。
- 本地扩展批次：**155 passed**（`tests/m2` 全目录 + passenger/exposure 单元 + `contract/test_g0_unit_trace`）。
- 云端部署树回归：**21 passed**（同焦点批次在已打补丁的 `/data/airslot/worktree` 上运行）。
- 新增测试覆盖（对应用户五项要求）：
  1. Year-local 2019 身份合同（路由断言 + 120 行真实行契约端到端，含旧代码必崩的构造）；
  2. Legacy 2019 兼容（无参数→data2_2019，stream 默认 None，taxi 不重拟合）；
  3. 2017/2018/2020–2022 身份不变性（参数化 5 年份）+ 显式上下文覆盖默认；
  4. 六参考/七分量表面（ontology=7 + fit 级 4 键 + continuity_b 输出=6+1=7 键）；
  5. 2019 taxi 来源与时间范围（v5 冻结件 fit 窗口 `2019-01..2019-06` 逐字钉住；2018 走重拟合）。
- 附带修复：`test_freeze_registry` 的 builder stub 签名自 3f27f6e（10-11）起陈旧失效，本批次修正。

## 云端核验记录

- 部署前哈希 == 前身：`data2_m2_train_fit.py` 6fa95b22…、`build_year_references.py` b593a3f7…、
  `test_freeze_registry.py` b84ea311…；
- 部署后哈希 == 提交 blob：28e8067c… / 20f4bc90… / f7f5bf23… / a6216f33…（逐项一致）；
- `patch -p1` 干跑通过后应用；`py_compile` 全部 OK；服务端签名检查通过。

## 范围合规自检

不改估计量/公式/筛选/分区/模型结构 ✓；不替换 2019 taxi 来源 ✓；不访问 Final-Test ✓；
不重算任何已 PASS 产物 ✓；Legacy 与其他年份行为不变 ✓；修复属"Legacy 与 Year-local 调用上下文未区分"的限定工程修复 ✓。
