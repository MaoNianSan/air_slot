# ROUND2_MANUSCRIPT_M1_REPRESENTATION_NOTE — 写作 impact memo

- 日期: 2026-08-19
- 性质: 写作建议 memo；不修改 manuscript tex。

## 1. 现状

Manuscript Section 3 joint factorization 若只条件于 `h_{i,t}`，会比 Section 4
empirical representation 窄。当前实现与论文声称的 cross-stage information sharing /
state dependence 对应的是:

```
chi_{i,t} = (h_{i,t}, r_fast_{i,t}, c_static_{i,t})
```

- `h_{i,t}` = GRU(full admissible causal history)
- `r_fast_{i,t}` = current/local-change/short-term-AR representation（决策节点最后
  causal row 的 deterministic block；不是 LightGBM hidden state）
- `c_static_{i,t}` = separately retained static/reference context（PRE 发布）

STATE_AWARE: `chi = [h, r_fast, c_static]`；FAST: `[r_fast, c_static]`。

## 2. 建议

后续 manuscript 改为概念上:

```
p(T_IB, D_OB, D_TX | chi)
```

以及条件分解 `T_IB_A00 -> D_OB -> D_TX`，其中 D_TX 的 formal parent 是 D_OB，
`R_IB = max(0, T_IB_A00 - t)`，`D_TO = D_OB + D_TX`（derived，无独立 head）。

## 3. 与 factual replay 的关系

同一 operational event 的 FACTUAL_REPLAY_EVIDENCE 角色在 decision time 合法可见时
收缩对应 stochastic component（PRE_IB -> POST_IB -> POST_OB -> COMPLETED），
论文可用 "information appears -> state contraction -> downstream distribution changes"
作为 cross-stage information sharing 的实证定位（
`test_cross_stage_information_updates_state_without_future_leakage`）。
