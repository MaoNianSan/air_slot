# Exp1 Development-only interpretation

在同一 Data2 Development cohort（1769 nodes）和冻结 M1_V2_GRU_H32 条件下，history-conditioned state 的 CRPS 和 Brier 略低于 current-state-only，calibration gap 也略有改善；MAE 基本持平但略高。该结果支持“历史条件化会改变状态表示”这一工程/Development 观察，但不构成 Final Test 或 paper-full 证据。

相对 current-state-only：CRPS 改善 0.1391 min，Brier 改善 0.0010，calibration gap 改善 0.0055；MAE 变化 0.0074 min。

解释边界：这些是 Development-only predictive/state metrics；未生成 M2/M3/M4 downstream decision evidence，不能解释为动作因果效果、真实货币损失或最终恢复策略最优性。