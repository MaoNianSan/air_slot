# Air Slot — Data Folder

**Version**: 2026-07-17  
**Status**: DATA_FOLDER_READY  
**Project Root**: `D:\research\air_slot\code\explore`

---

## 1. 定位

`data/` 文件夹只保存两类内容：

1. **不可变的官方原始数据** (`raw/`)
2. **官方许可证、使用条款、来源说明和归属信息** (`source_docs/`)

**以下处理必须放在 `pre/` 中，不得在 `data/` 中保存**：
轨迹筛选、机场流量筛选、清洗、去重、异常值处理、时间对齐、1 分钟规范化、短缺口插值、latest-admissible、METAR 对齐、training-only fallback、reference 构建、snapshot 构建、episode 构建、model-ready 数据生成。

---

## 2. 正式目录树

```text
data/
├── README.md
├── raw/                           # 不可变的官方原始文件
│   ├── opensky/
│   │   ├── flightlist/
│   │   │   └── 2022/              # 12 个月 CSV.GZ
│   │   ├── state_vectors/
│   │   │   └── 2022/
│   │   │       └── date=YYYY-MM-DD/
│   │   │           └── hour=HH/
│   │   │               └── states_YYYY-MM-DD-HH.csv.tar
│   │   └── aircraft_metadata/
│   │       └── snapshot=2022-01/  # 1 个 CSV
│   ├── metar/
│   │   └── 2022/
│   │       └── station=ICAO/      # 19 个机场 CSV
│   ├── ourairports/
│   │   └── snapshot=2021-12-31/   # airports.csv + runways.csv
│   └── eurostat/
│       └── 2022/
│           ├── passengers/        # 12 个 JSON (avia_paoa)
│           └── commercial_flights/ # 12 个 JSON (avia_tf_airpm)
└── source_docs/                   # 官方许可证、使用条款、来源说明
    ├── opensky/
    │   ├── SOURCE_NOTE.md
    │   ├── ATTRIBUTION.md
    │   ├── LICENSE.txt
    │   └── retrieval_metadata.json
    ├── metar/
    │   ├── SOURCE_NOTE.md
    │   ├── ATTRIBUTION.md
    │   └── retrieval_metadata.json
    ├── ourairports/
    │   ├── SOURCE_NOTE.md
    │   ├── ATTRIBUTION.md
    │   ├── LICENSE.txt
    │   └── retrieval_metadata.json
    ├── eurostat/
    │   ├── SOURCE_NOTE.md
    │   ├── ATTRIBUTION.md
    │   └── retrieval_metadata.json
    └── project/
        └── (Eurocontrol / A-CDM reference PDFs)
```

---

## 3. 各数据源用途

| 数据源 | 用途 | Canonical Path | 格式 | 时间覆盖 |
|--------|------|----------------|------|----------|
| OpenSky Flightlist | 航班计划和完成参考；轨迹目标选择 | `raw/opensky/flightlist/2022/` | CSV.GZ | 2022 全年 12 个月 |
| OpenSky State Vectors | ADS-B/Mode-S 原始状态观测 | `raw/opensky/state_vectors/2022/` | CSV.TAR | 23 个观测日（552 文件）+ 1 个部分日（10 文件） |
| OpenSky Aircraft Metadata | 飞机类型/注册映射 | `raw/opensky/aircraft_metadata/snapshot=2022-01/` | CSV | 2022-01 快照 |
| METAR (IEM) | 天气观测（风、能见度、云底、温度、降水） | `raw/metar/2022/` | CSV | 2022 全年 19 机场 |
| OurAirports | 机场坐标、类型、跑道 | `raw/ourairports/snapshot=2021-12-31/` | CSV | 静态快照 |
| Eurostat Passengers | 月度旅客量参考 | `raw/eurostat/2022/passengers/` | JSON | 2022 年 12 个月 |
| Eurostat Commercial Flights | 月度商业航班量参考 | `raw/eurostat/2022/commercial_flights/` | JSON | 2022 年 12 个月 |

---

## 4. 数据集详细 Schema

### OpenSky Flightlist

| 列 | 类型 | 说明 | 可空 | 连接键 |
|----|------|------|------|--------|
| icao24 | string | ICAO 24-bit 飞机地址 | NO | → state_vectors, aircraft |
| origin | string | 出发机场 ICAO | YES | → airports |
| destination | string | 到达机场 ICAO | YES | → airports |
| firstseen | datetime (UTC) | 首次 ADS-B 观测 | NO | — |
| lastseen | datetime (UTC) | 末次 ADS-B 观测 | NO | — |
| callsign | string | 航班呼号 | YES | — |

### OpenSky State Vectors

| 列 | 类型 | 单位 | 说明 | 可空 |
|----|------|------|------|------|
| time | datetime (UTC) | — | 观测时间戳 | NO |
| icao24 | string | — | ICAO 24-bit 飞机地址 | NO |
| lat | float64 | degrees | WGS-84 纬度 | YES |
| lon | float64 | degrees | WGS-84 经度 | YES |
| baroaltitude | float64 | feet | 气压高度 | YES |
| velocity | float64 | m/s | 地速 | YES |
| vertrate | float64 | ft/min | 垂直速率 | YES |
| heading | float64 | degrees | 真航向 | YES |
| onground | bool | — | 地面标志 | YES |

### OpenSky Aircraft Metadata

| 列 | 类型 | 说明 | 可空 |
|----|------|------|------|
| icao24 | string | ICAO 24-bit 飞机地址 | NO |
| typecode | string | ICAO 飞机型号代码 | YES |
| registration | string | 注册号 | YES |
| model | string | 型号 | YES |

### METAR (IEM)

| 列 | 类型 | 单位 | 说明 | 可空 |
|----|------|------|------|------|
| station | string | — | ICAO 站号 | NO |
| valid | datetime (UTC) | — | 观测有效时间 | NO |
| sknt | float64 | knots | 风速 | YES |
| gust | float64 | knots | 阵风 | YES |
| vsby | float64 | statute miles | 能见度 | YES |
| ceiling | float64 | feet AGL | 云底高 | YES |
| tmpf | float64 | °F | 气温 | YES |
| dwpf | float64 | °F | 露点 | YES |

### OurAirports

| 列 | 类型 | 单位 | 说明 | 可空 |
|----|------|------|------|------|
| ident | string | — | 机场标识符 | NO |
| latitude_deg | float64 | degrees | 纬度 | YES |
| longitude_deg | float64 | degrees | 经度 | YES |
| type | string | — | 机场类型 | YES |
| elevation_ft | float64 | feet | 标高 | YES |

### Eurostat

| 列 | 类型 | 单位 | 说明 | 可空 |
|----|------|------|------|------|
| airport | string | — | 机场 ICAO | NO |
| month | string (YYYY-MM) | — | 参考月 | NO |
| passengers | int64 | count | 旅客数 | YES |
| commercial_flights | int64 | count | 商业航班数 | YES |

---

## 5. State-Vector 文件范围

正式 Full 日期与角色的唯一真源为 `manifests/formal_72_day_manifest.csv`；
rolling fold 映射见 `manifests/formal_fold_membership.csv`。README 不复制该日期表。

- **正式文件数**: 552 个 `.csv.tar`（23 天 × 24 小时）+ 10 个 legacy（2022-02-14 hours 00-09）
- **总计**: 562 个 `.csv.tar`
- **完整观测日**: 23 天，各 24 小时
- **文件命名**: `states_YYYY-MM-DD-HH.csv.tar`
- **路径模式**: `raw/opensky/state_vectors/2022/date=YYYY-MM-DD/hour=HH/states_YYYY-MM-DD-HH.csv.tar`

### 完整观测日（23 天）

2022-01-03, 2022-01-10, 2022-01-17, 2022-02-07, 2022-02-21, 2022-02-28, 2022-03-07, 2022-03-14, 2022-03-21, 2022-03-28, 2022-04-04, 2022-04-11, 2022-04-18, 2022-04-25, 2022-05-02, 2022-05-09, 2022-05-16, 2022-05-23, 2022-05-30, 2022-06-06, 2022-06-13, 2022-06-20, 2022-06-27

### 部分观测日

- **2022-02-14**: 仅 hours 00-09（10 小时，公共 S3 bucket）。`formal_eligible = false`。缺失 hours 10-23 → `SOURCE_COVERAGE_GAP`

### 不可用日期

- **2022-09-19**、**2022-11-14**: 公共 S3 bucket 无数据 → `SOURCE_COVERAGE_GAP`

---

## 6. 关键连接键

| 键 | 连接的源 |
|----|---------|
| `icao24` | Flightlist ↔ State Vectors ↔ Aircraft Metadata |
| `station` / `ident` (ICAO) | METAR ↔ OurAirports ↔ Flightlist (destination) |
| `airport` (ICAO) | Eurostat ↔ OurAirports |

**时区**: 所有时间戳均为 **UTC**。

---

## 7. Raw 文件不可修改原则

1. `raw/` 中所有文件均为不可变的官方原始下载。
2. 不得修改内容、解压后删除原始归档、或将筛选/插值结果放入 `raw/`。
3. 所有处理必须在副本上执行。
4. `.csv.tar` 文件必须永久保留。

---

## 8. 许可证和归属

所有数据源均有官方验证的许可证：

| 来源 | 许可证 | 详情 |
|------|--------|------|
| OpenSky | OpenSky Data License (Research) | `source_docs/opensky/` — 非商业研究，禁止再分发，需匿名化 icao24 |
| METAR (IEM) | Public Domain / Open Access | `source_docs/metar/` — 无限制 |
| OurAirports | Unlicense (Public Domain) | `source_docs/ourairports/` — 无限制 |
| Eurostat | CC BY 4.0 | `source_docs/eurostat/` — 需注明来源 |

**LICENSE_UNCLEAR 项: 无。**

---

## 9. Formal、Partial 和 Source-Gap 定义

| 状态 | 含义 |
|------|------|
| `formal_eligible = true` | 23 个完整 24h 观测日 |
| `RETAINED_LEGACY_PARTIAL` | 2022-02-14 h00-09（`formal_eligible = false`） |
| `SOURCE_COVERAGE_GAP` | 2022-02-14 h10-23；2022-09-19；2022-11-14 |

---

## 10. 当前已知数据缺口

- **ERA5**: 未下载（P2，METAR 支持 M1 天气特征）
- **TAF**: 未下载（P2）
- **2022-09-19, 2022-11-14**: State-vector 不可用
- **Trino 历史访问**: 被阻止
- **681 个 derived Parquet**: 已删除。需从 raw 重新提取 trajectory + airport_flow

---

## 11. Data 与 Pre 的边界

```
data/                         pre/
  raw/ — 原始下载              读取 raw
  source_docs/ — 许可证        清洗、筛选、去重
                                时间对齐、1 分钟规范化
  不保存 derived 文件           短缺口插值、latest-admissible
  不保存 Parquet               training-only fallback
  不插值                       构建 references、snapshots、episodes
                                生成 model-ready 数据
```

**`data/` 只保存输入。`pre/` 负责所有处理。**

---

*Air Slot 数据集治理框架 · 最后更新 2026-07-17*
*raw/ 文件总数: 659 · 其中 .csv.tar: 562 · Parquet in raw/: 0*
