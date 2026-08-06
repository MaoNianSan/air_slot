# PRE GitHub Secret Audit（敏感信息审计）

> 上传审计专用（不上传 GitHub）。生成时间：2026-08-05。

## 结论

`SECRET_SCAN_STATUS=PASS`（gitleaks 未安装，使用本地正则只读扫描；`TOOL_UNAVAILABLE` 记录于下）

`LOCAL_PATH_STATUS=PASS`（2 处文档本地绝对路径已清理）

## 工具可用性

- `gitleaks`：**未安装**（未联网安装；按规则使用本地正则扫描并记录）。
- 替代手段：`git grep`（已跟踪文件）+ PowerShell 正则（未跟踪非忽略文本文件）只读扫描。

## 7.1 文件名扫描（tracked + untracked non-ignored）

扫描模式：`.env` / `credentials?` / `secret` / `tokens?` / `apikey` / `api_key` /
`private_key` / `id_rsa` / `*.pem` / `*.key` / `auth.json` / `service-account`

结果：**无命中**。

## 7.2 文本内容扫描

### 密钥模式（tracked + untracked non-ignored）

扫描：`-----BEGIN PRIVATE KEY-----` / `-----BEGIN RSA PRIVATE KEY-----` /
`github_pat_` / `ghp_` / `gho_` / `ghu_` / `ghs_` / `ghr_` / `AKIA...` / `AIza...` /
`sk-` / `Bearer ` / `password=` / `password:` / `api_key=` / `api_key:` /
`access_token` / `refresh_token` / `client_secret`

结果：**无命中**。

### 数据库连接串 / 内网 URL / 用户名 / 邮箱

- 数据库连接串（postgres|mysql|mongo|redis|jdbc|sqlite://...）：无命中。
- 内网 URL（localhost / 127.0.0.1 / 10.x / 192.168.x / 172.16-31.x）：无命中。
- 用户名（maonian / maoni）：无命中。
- 邮箱：仅 `data/source_docs/opensky/LICENSE.txt` 中出现 `contact@opensky-network.org`
  （第三方公开数据许可证文本，非秘密，属合法公开内容，保留）。

## 本地绝对路径（LOCAL_PATH_STATUS）

扫描：`D:\research\` / `C:\Users\` / `/home/` / `/Users/`

发现并**已修复** 2 处（上传文档中的绝对路径 → 中性描述）：

| 文件 | 行 | 处理 |
|---|---|---|
| `data/README.md` | 5 | `**Project Root**: D:\research\air_slot\code\explore` → "the repository root (parent of data/, pre/, etc.)" |
| `pre/README.md` | 48 | `i.e. D:\research\air_slot\code\explore` → "i.e. the parent of pre/" |

修复后复扫：无命中。测试 fixture 中未发现需替换的中性路径问题。

## Remote URL

```
origin  https://github.com/MaoNianSan/air_slot.git (fetch)
origin  https://github.com/MaoNianSan/air_slot.git (push)
```

- 无 token / 无用户名密码 / 无嵌入凭据。PASS。

## 处置规则

- 未发现任何疑似 secret → 无需阻止提交；报告未写入任何完整 secret（本报告只含文件/类型级别信息）。
- `GITHUB_UPLOAD_READY` 不受 secret 项阻塞（见 Phase 10 汇总）。
