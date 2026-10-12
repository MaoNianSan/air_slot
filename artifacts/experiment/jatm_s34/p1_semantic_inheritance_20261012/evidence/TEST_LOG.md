# 定向验证记录

- 工作分支：`v2/paper-primary`；执行时 HEAD `6e9c40069daf6aab73bca014868187a596240d1d`，工作区含已有P1候选改动。该候选代码随后按精确路径提交为 `6b5c85e0ee6b7e2a4fa4bac1770766251f73919f`，文件内容未改变。
- 命令：`python -m pytest -q tests/contract/test_jatm_p1_closure.py tests/contract/test_jatm_p0_acceptance.py`
- 实际输出：`26 passed in 4.74s`，exit 0。
- 命令：`python -m compileall -q exp/jatm_s34 model/M2 model/M3 model/M4`，exit 0，无错误输出。
- 已有真实Development对账：`tmp/p1_cached_acceptance_probe.json`，`tmp/p1_policy_cached_acceptance_probe.json`，均只读复核；算法与旧tail缓存身份见文件中`source`。当前`policy_sensitivity.py`的canonical-LF哈希与policy probe中的算法哈希相同。
- 当前年度缺口文件逐项存在性复核：21/21仍缺；Linux/CUDA未执行。没有访问Test/Final-Test、连接云端或启动年度任务。

上述是代码正确性与小样本数值证据，不能证明A/B运营定义、全年科学统计或六年执行已完成。
