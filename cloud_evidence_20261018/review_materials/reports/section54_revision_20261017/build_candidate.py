from pathlib import Path
import json, csv, statistics

# Archived generator: candidate withdrawn after zero-event review.
raise SystemExit('Candidate withdrawn from main-text recommendation; preserve review note and existing outputs.')

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parents[1] / 'backfill_20261014/extracted/e2_six_year.json'
data = json.loads(SOURCE.read_text(encoding='utf-8'))
contrasts = [('HM–HJ', 'CROSS_STATE_DEPENDENCE'), ('HP–HJ', 'DISTRIBUTIONAL_INFORMATION')]
keys = ['missed_activation', 'false_activation', 'under_recovery', 'over_recovery']
rows = []
for year, entry in sorted(data.items()):
    e = entry['e2']
    n = e['reference_cohort_size']
    for name, component in contrasts:
        v = e['information_value'][component]
        counts = [v[k] for k in keys]
        assert all(isinstance(x, int) and x >= 0 for x in counts)
        assert abs(sum(counts)/n - (1-v['A0'])) < 1e-6
        rows.append(dict(year=year, contrast=name, N=n, **{k:v[k] for k in keys}, **{k+'_pct':100*v[k]/n for k in keys}))
with (ROOT/'table_5_5_activation_direction_annual.csv').open('w', newline='', encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
annual = '\n'.join('| '+ ' | '.join([r['year'], r['contrast']] + [f"{r[k+'_pct']:.1f}%" for k in keys])+' |' for r in rows)
summary=[]
for name,_ in contrasts:
    cells=[]
    for k in keys:
        a=[r[k+'_pct'] for r in rows if r['contrast']==name]
        cells.append(f'{statistics.mean(a):.1f}%（{min(a):.1f}%–{max(a):.1f}%）')
    summary.append('| '+name+' | '+' | '.join(cells)+' |')
text = r'''# 5.4 替换候选：恢复启动与目标方向

候选状态：供中文结构共识使用。建议将原 M5-b 状态表移至补充材料，正文 5.4 使用现有 E2 输出中的动作分类。这是同一实验的进一步分解，不是新增的独立实验；正式 TeX 尚未回填。

### 5.4 表示差异体现为恢复启动变化，还是启动后的目标调整？

5.2 的动作一致率反映了不同表示下的目标差异，但尚不能区分差异发生在是否启动恢复，还是双方均启动后的目标选择。为此，表 5.5 在每年的固定 HJ 参考队列中，将非一致动作分为四类：HJ 启动而比较表示不启动、比较表示启动而 HJ 不启动，以及双方均启动时比较表示的目标低于或高于 HJ。各类比例均以完整年度 HJ 参考队列为分母。

HM–HJ 的差异主要集中于双方均启动后的目标选择。六年等权平均中，HJ 启动而 HM 不启动占全队列 1.8%，HM 启动而 HJ 不启动占 1.7%；双方均启动时，HM 目标低于 HJ 的比例为 6.4%，高于 HJ 的比例为 26.1%。后者在六个年度中均高于前者。结合 5.2 中一个 5 分钟档位内的较高一致率，HM–HJ 比较同时呈现出两个特征：动作差异多数较小，且在双方均启动的对象中，目标较高的情形更为常见。表 5.5 不交叉区分动作差异大小，因此不能进一步断言目标较高的对象主要相差一个档位。

HP–HJ 则呈现不同的差异构成：HJ 启动而 HP 不启动占全队列的年度比例为 69.2%–81.8%，六年等权平均为 74.6%；双方均启动且 HP 目标较低的比例年均为 7.9%。六个年度均未观察到 HP 单独启动或双方启动时 HP 目标高于 HJ 的情形。因此，HP–HJ 较低的一致率主要伴随恢复启动选择的差异，而 HM–HJ 的差异更多表现为启动后的目标调整。

这些结果说明，评估信息表示的决策影响时，应同时考察是否启动与启动后的目标方向。两种表示即使都降低了动作完全一致率，也可能对应不同的决策变化。这里的分类均以 HJ 为比较参照，不能将 HJ 的选择视为实际运行中的正确答案，也不能将较高的恢复目标直接解释为资源浪费。各类比例是描述性队列统计，并非以正例或负例为分母的条件误报率、漏报率。

### 表 5.5　固定 HJ 参考队列中的恢复启动与目标方向差异

| 年份 | 比较表示–HJ | 仅 HJ 启动 | 仅比较表示启动 | 双方启动：比较目标较低 | 双方启动：比较目标较高 |
|---|---|---:|---:|---:|---:|
ANNUAL_TABLE

注：HM、HP 分别为比较表示，HJ 为参考表示。仅 HJ 启动指 $u^*_{HJ}>0,u^*_{comp}=0$；仅比较表示启动指 $u^*_{HJ}=0,u^*_{comp}>0$；后两列均限定双方 $u^*>0$，再比较目标大小。四类互斥，合计为非完全一致比例，因显示舍入可能与 $1-A_0$ 略有差异。分母为当年完整 HJ 参考队列：2017—2022 年依次为 521、523、515、474、523、532。表中未报告置信区间；逐年事件数和队列分母置于补充材料。所有列采用相同的队列分母，不将后两列误读为双方均启动对象中的条件比例。

独立的样本量检查覆盖 $N=128,256,512,1024,2048,4096$。六个年度在所测网格内均未识别稳定样本量边界，因而上述年度结果不能据此获得样本量充分性的保证。逐年检查状态、未通过判据及协议边界见补充材料。

---

## 方案说明（不属于正文）

原表最后一列六行完全相同，应合并为一句限制说明；网格也无年度变化。失败项数量只有 11–12 的变化，不直接衡量管理决策影响。新表最后一列给出比较目标较高的队列比例，能与前一列对照方向，信息量更大。HP 的零值完整保留，不能只挑有差异的单元。

概览：六年等权平均（年度范围，非 CI）。正式正文使用上方逐年表，不同时放置两张重复表。

| 比较 | 仅 HJ 启动 | 仅比较表示启动 | 双方启动：比较目标较低 | 双方启动：比较目标较高 |
|---|---:|---:|---:|---:|
SUMMARY_TABLE

与现有结构衔接：5.2 回答差异有多大，5.3 回答预设目标如何关联到差异，5.4 分解默认目标下的动作差异方向。5.4 是 E2 的解释性延伸，不能计作一组新实验，也不能声称证明了因果机制。Supplement 保留逐年 n/N 和 M5-b 状态，不重复铺陈正文百分比表；原 5.4 的样本量限制仍在本候选末段明确报告。若采用此方案，需同步修改 Section 5 导言、结尾和 Supplement 引用。

数据与定义：年度值来自 backfill_20261014/extracted/e2_six_year.json 的 e2.information_value 中 CROSS_STATE_DEPENDENCE 与 DISTRIBUTIONAL_INFORMATION；定义核对自 review_v64_20261014/snapshot_code/model/M4/evaluation.py 的事件分类。12 个年度—比较单元的四类计数之和，均与输出 A0 对应的非一致对象比例吻合（允许 A0 六位小数舍入）。CSV 保存全部计数、分母和未舍入百分比。

另检查了 q4_extension_package_20261015 中的 M5-b 原始指标。2017 年 N4096 记录 results 为空，状态为 NOT_IDENTIFIABLE_AT_THIS_N；六年 N2048 记录含与 N4096 的比较，但 l_att@combined 约 0.496–0.515、l_rec 约 0.424–0.579，相关判据均未通过。这些记录不能支持正向收敛结论；其嵌套队列比较口径也不等同于 E2 的表示比较，未将其混入本表。原状态表应作为完整限制披露保留，不能用新表替代对稳定性问题的说明。
'''
(ROOT/'section54_replacement_candidate_cn.md').write_text(text.replace('ANNUAL_TABLE',annual).replace('SUMMARY_TABLE','\n'.join(summary)),encoding='utf-8')
print('Wrote candidate and annual CSV; 12 event partitions reconciled with A0.')

if __name__ == '__main__':
    pass
