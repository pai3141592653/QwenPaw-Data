# QwenPaw-Data 技能路由 P0 开发记录（2026-11-17）

> 目标：解决「31 个技能清单齐备，模型只读 1 个；归因/维度/报告靠临时脚本绕过」。
> 本记录只描述已落地的验证原型；正式合入 QwenPaw-Data 源码前需迁移/评审。

## 1. 现状证据

- QwenPaw `ses_Vfqfz3TM`（`ep-20260914162330-b4z8k` / `xhigh`）：
  75 次工具调用，技能只读 `bi-report-generation`；
  `bi-attribution-analysis` / `bi-dimension-drilldown` / `bi-anomaly-detection` 未读。
- 同会话追问 `按分区月份拆解…`：89 次工具调用，仍只读 `bi-report-generation`，
  维度拆解用临时 Python 脚本。
- data-analysis-agent `session-851b49719f36`：只读 `bi-analysis-chain`。

结论：`description` 发现不等于按需读取；需要 required-skill 契约。

## 2. 已实现（验证原型）

修改的是 `D:\QwenPaw\.venv\Lib\site-packages` 的运行时副本，**不是** QwenPaw-Data 仓库源码。

| 文件 | 改动 |
|---|---|
| `qwenpaw_data/host/core/orchestration/skill_router.py` | 新增：计划文本 → required/optional；从 trace 提取已读技能 |
| `qwenpaw_data/host/core/orchestration/tools.py` | `create_plan`：required 未读则拒绝建计划；`finish_plan`：required 未读则拒绝收尾 |
| `qwenpaw_data/host/core/orchestration/middleware.py` | 所有节点 done 但当前图未 finish 时，向系统提示注入 `<finish-required>` |

规则（QwenPaw 侧）：

```text
波动/归因 → bi-metric-analysis, bi-attribution-analysis,
            bi-dimension-drilldown, bi-report-generation
异常      → bi-anomaly-detection, bi-attribution-analysis, bi-report-generation
分群/漏斗/同期群/对比/因果 → 对应技能 + 报告技能
generic   → 不强制
```

备份：

```text
tools.py.bak_20261117_skillroute
middleware.py.bak_20261117_finishguard
```

## 3. 已验证

### 3.1 create_plan 门禁

会话 `ses_7mkFpzZp`（`033075`，Host 身份可见）：

```text
第一次 create_plan
→ 技能契约未满足，计划未创建
→ required = [bi-metric-analysis, bi-attribution-analysis,
              bi-dimension-drilldown, bi-report-generation]
→ 模型读取 4 份 SKILL.md
→ 重新 create_plan 成功
```

### 3.2 完整终极大考（2026-11-17 14:30）

会话 `ses_caJdEWmV`（`7DD3BF`，Host 身份可见）：

```text
required 4/4 读取（bi-metric-analysis / bi-attribution-analysis /
                  bi-dimension-drilldown / bi-report-generation）
create_plan 成功（graph_R2xddSZ7，5 个节点）
finish_plan(state="done", outcome=...) 成功：Task graph finished.
report_validation.json = PASS，numbers_checked = 9
报告：graph_R2xddSZ7/n5_report_validate/report_v1.html
```

最终答复引用的核心数字与报告一致：

```text
2月 -185.7% / 3月 +365.2% / 4月 -121.3% /
5月 +172.1% / 6月 -20.5% / 7月 +208.0%
职级30贡献 67%–94%
```

### 3.3 关键修复

第一次终极大考（`ses_CfNkhKM8`）发现两个问题：

1. `finish_plan` 未被调用；
2. `create_plan` 前读技能时，`_traces` 还没有 active graph，
   技能读取没有进入 trace，导致 `实际读取 = []`。

修复：

- `RuntimeStateManager` 新增独立的 `_skill_reads`，在 `append_to_trace`
  一开始就记录技能，不依赖 active graph；
- `skills_from_traces` 兼容：
  - Windows JSON 转义路径 `skills\\default\\<name>\\SKILL.md`；
  - QwenPaw `Skill` 工具参数 `{"skill": "<name>"}`；
- `FinishPlan` 和 `CreatePlan` 都同时读取 `_skill_reads` + `_traces`；
- `QwenPawDataHintMiddleware` 在节点全部结束但图未 finish 时注入
  `<finish-required>`。

## 4. P1：应调技能识别与强化

P0 只要求 4 个核心方法技能；复盘 `ses_caJdEWmV` 仍发现以下过程/条件技能未读：

```text
skill-hub-guide
runtime-guide
fetch-data
bi-semantic-layer-guide
bi-causal-attribution
bi-anomaly-detection（optional）
```

P1 规则：

```text
所有非 generic 分析：
  + skill-hub-guide
  + runtime-guide

计划含 取数/SQL/execute_sql/查询：
  + fetch-data

计划含 口径/语义/指标定义/维度/search_context/元数据：
  + bi-semantic-layer-guide

计划含 事件/活动/search_event/外部/原因/因果：
  + bi-causal-attribution

波动任务 optional：
  + bi-anomaly-detection
  + bi-comparison-analysis
```

已验证路由输出（QwenPaw）：

```text
波动 + 口径 + 取数 + 事件
→ required 9 个：
  skill-hub-guide
  runtime-guide
  bi-metric-analysis
  bi-attribution-analysis
  bi-dimension-drilldown
  bi-report-generation
  fetch-data
  bi-semantic-layer-guide
  bi-causal-attribution
→ optional：bi-anomaly-detection / bi-comparison-analysis
```

P1 建图验证（会话 `ses_bbgiM3kD`，`1F8194`，Host 身份可见）：

```text
第一次 create_plan：拒绝，required 9，实际读取=[]
→ 模型读取 9 份 SKILL.md
→ 第二次 create_plan：成功（graph_QWpgbPom，5 节点）
```

9 份实际读取：

```text
skill-hub-guide
runtime-guide
bi-metric-analysis
bi-attribution-analysis
bi-dimension-drilldown
bi-report-generation
fetch-data
bi-semantic-layer-guide
bi-causal-attribution
```

该轮随后完整跑完：

```text
finish_plan(state="done", outcome=...) → Task graph finished.
report_validation.json → PASS（numbers_checked=9）
最终答复 → graph_QWpgbPom/generate_report/report.html
```

P1 终局结论：required 9/9 读取、create_plan 成功、finish_plan 成功、报告 PASS。

### 4.1 F7AB79 的两次 create_plan 失败复盘

用户重测会话 `ses_CuftWyAa`（`F7AB79`）出现 4 个错误：

```text
create_plan 第 1 次：required 8，实际读取 []         ← 没先读技能，门禁拒绝
create_plan 第 2 次：required 9，实际读取 8，缺 fetch-data
                      ← 第二次 plan 用了“全量取数”，
                        而第一次 plan 的“数据获取”没触发 fetch-data
create_plan 第 3 次：成功（graph_Sbru5Arn，6 节点）
search_context 504：context.search_pipeline 180s 超时（非技能问题）
get_dataset 400 Cannot infer domain：模型漏传 domain（非技能问题）
```

修复：

- `fetch-data` 触发词补齐：`数据获取 / 取数据 / 拉取数据 / 查询数据 / 全量数据`；
- required 重试时只增不减，首次失败也缓存，避免集合漂移；
- 不把 `search_context` / `get_dataset` 错误混入技能契约统计。

重启后新会话 `ses_khiv7j48`（`70AE23`）验证：

```text
create_plan 第 1 次：required 9，实际读取 []（拒绝）
→ 模型读取 9 个技能
create_plan 第 2 次：成功（graph_hL7Rj84K，5 节点）
```

目标达成：**从“两次失败”降到“一次失败 + 一次成功”**，且第一次 required 已包含
`fetch-data`，不再出现“第二次 plan 才新增技能”的漂移。

### 4.2 70AE23 复测审计（2026-11-17）

会话 `ses_khiv7j48`（`70AE23`）完成：

```text
9/9 required 技能读取
create_plan 只失败 1 次（首次未读，门禁拒绝）
第二次 create_plan 成功（graph_hL7Rj84K，5 节点）
finish_plan：Task graph finished.
report_validation：PASS，numbers_checked=9
```

新的 `fetch-data` 同义触发词和 required 只增不减已生效；没有再次出现
F7AB79 的“第二次缺 fetch-data”。

但审计发现仍有 6 个错误卡片：

```text
1 个 create_plan：首次未读技能的预期拒绝
5 个 update_subtask：bad escape \s / 报告缺 CSV
```

`update_subtask` 最终重试成功，finish_plan 和报告 PASS 不受影响；
这是独立于技能路由的残留问题，需要在 UI 验收前单独排查。

详细方法和 data-agent 迁移说明：

`E:\PythonWorkSpace2\data-analysis-agent\docs\interactive-data-analysis\SKILL-ROUTING-P1-应调技能识别与强化-20261117.md`

### 4.3 QwenPaw-Data 源码版完整会话（2026-11-18）

源码侧测试：

```text
host-core 定向测试：15 passed
```

源码 Engine：

```text
端口 18081
PYTHONPATH = packages/qwenpaw-data-host-core/src
QWENPAW_DATA_WORKSPACE=local
QWENPAW_DATA_PERMISSION_MODE=bypass（仅本地测试）
```

会话：

```text
ses_C8HVJq2c / 639D1C
```

结果：

```text
create_plan 第 1 次拒绝（预期：required 9，实际读取 []）
读取 9 个技能
create_plan 第 2 次成功（graph_YTE9Gutv，4 节点）
finish_plan：Task graph finished.
report_validation：PASS（numbers_checked=9）
```

这次没有出现 `update_subtask bad escape`；源码 `state.py` 的 Windows `files`
解析修复可能已经覆盖了该问题，但还需要单独回归确认。

注意：

```text
QWENPAW_DATA_PERMISSION_MODE=bypass 只用于本地测试；
生产环境应通过 Host 的权限上下文，不要默认 bypass。
```

## 5. 模型

Engine 进程环境：

```text
QWENPAW_DATA_MODEL_NAME=ep-20260914162330-b4z8k
QWENPAW_DATA_MODEL_PROVIDER=openai
QWENPAW_DATA_MODEL_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
reasoning_effort=xhigh
```

### 5.1 永久替换 Host/UI 模型（2026-11-17）

不只改 Engine env，已把 Host 的全局 active model 永久切到 endpoint：

```text
POST /api/models/ark/models
  {"id":"ep-20260914162330-b4z8k","name":"Doubao-Seed-2.1-pro"}

PUT /api/models/active
  {"provider_id":"ark","model":"ep-20260914162330-b4z8k","scope":"global"}
```

验证：

```text
GET /api/models/active
→ {"active_llm":{"provider_id":"ark","model":"ep-20260914162330-b4z8k"}}

GET /api/qwenpaw-data/model-settings
→ workspace_default / analysis / lightweight / databridge
  全部为 ep-20260914162330-b4z8k（provider=ark）

重启 Host 后再查，仍为 ep-20260914162330-b4z8k
```

持久化文件（均已备份）：

```text
C:\Users\Tianxing.Chen\.qwenpaw\apps\qwenpaw-data\config.json
C:\Users\Tianxing.Chen\.qwenpaw\apps\qwenpaw-data\models.json
C:\Users\Tianxing.Chen\.qwenpaw\apps\qwenpaw-data\engine\.secrets\models.json
```

备份后缀：`.bak_20261117_doubao`

### 5.2 切换到 Doubao-Seed-2.1-lite（2026-11-18）

用户要求把模型永久切换到：

```text
provider: ark
model:    ep-20261110164521-hms7j
name:     Doubao-Seed-2.1-lite
thinking: xhigh（最高档）
```

操作：

```text
POST /api/models/ark/models
  {"id":"ep-20261110164521-hms7j","name":"Doubao-Seed-2.1-lite"}

PUT /api/models/active
  {"provider_id":"ark","model":"ep-20261110164521-hms7j","scope":"global"}
```

验证：

```text
GET /api/models/active
→ {"active_llm":{"provider_id":"ark","model":"ep-20261110164521-hms7j"}}

GET /api/qwenpaw-data/model-settings
→ workspace_default / analysis / lightweight / databridge
  全部为 ep-20261110164521-hms7j（provider=ark）
```

Engine 18080 已重启，进程环境：

```text
QWENPAW_DATA_MODEL_NAME=ep-20261110164521-hms7j
QWENPAW_DATA_WORKSPACE=local
reasoning_effort=xhigh
```

持久化文件：

```text
C:\Users\Tianxing.Chen\.qwenpaw\apps\qwenpaw-data\config.json
C:\Users\Tianxing.Chen\.qwenpaw\apps\qwenpaw-data\models.json
C:\Users\Tianxing.Chen\.qwenpaw\apps\qwenpaw-data\engine\.secrets\models.json
```

备份后缀：`.bak_20261118_pro`

注意：源码 Engine 18081 这次重启没有起来（uvicorn 无监听日志），
当前只有 18080 运行时使用 lite；源码 Engine 需要稍后重建启动。

### 5.3 Doubao-Seed-2.1-lite 实测（2026-11-18）

#### 运行时 Engine 18080

```text
session: ses_TGeSnT3t / B0B9A4
model: ep-20261110164521-hms7j
```

结果：

```text
required 9 个技能读取
create_plan 第一次拒绝（预期）
第二次 create_plan 成功（graph_L4RvFuEP，6 节点）
finish_plan：Task graph finished.
report_validation：PASS（numbers_checked=9）
```

问题：

```text
update_subtask 仍出现 3 次 bad escape \s
另有 1 次 Read 调用失败
create_plan 1 次预期拒绝
```

#### 源码 Engine 18081

```text
session: ses_YXUKQ4nw / A78175
model: ep-20261110164521-hms7j
workspace: local
permission: bypass（仅测试）
```

结果：

```text
required 9 个技能读取
create_plan 第一次拒绝（预期）
第二次 create_plan 成功（graph_YBFTujRT，5 节点）
finish_plan：Task graph finished.
report_validation：PASS（numbers_checked=9）
```

错误：

```text
create_plan 1 次预期拒绝
Read 调用失败 1 次
update_subtask bad escape：0 次
```

源码版这轮没有复现 update_subtask 错误；仍需要定向回归，不能直接断言
源码已经修掉。

### 5.4 update_subtask bad escape 已定位并修复

根因不是 JSON 解析，而是：

```python
html = cdn_pattern.sub("<script>" + source + "</script>", html)
```

`re.sub` 的 **replacement 字符串** 会把 `\s` 当成转义；
ECharts 内联源码里含有 `\s`，于是报：

```text
bad escape \s at position 20211 (line 10, column 12690)
```

修复：

```python
html = cdn_pattern.sub(
    lambda _m: "<script>" + source + "</script>",
    html,
)
```

已修改运行时：

```text
D:\QwenPaw\.venv\Lib\site-packages\qwenpaw_data\host\core\orchestration\state.py
```

备份：

```text
state.py.bak_20261118_cdnsub
```

直接复现验证：

```text
UpdateSubtask(node6, done, files=[report.html, clean_winsorized_data.csv,
  dimension_contribution.csv, sections.json])
→ Node 'node6' marked as done. Recorded 4 file(s).
→ 不再报 bad escape \s
```

源码 `state.py` 没有这段 `cdn_pattern.sub`，所以源码版没有该 bug；
运行时 site-packages 才有。

### 5.5 修复后 Lite 干净复测（2026-11-18）

```text
session: ses_YVCMaMMu
display: 958458
model: ep-20261110164521-hms7j
engine: 18080（已加载 re.sub 修复）
```

结果：

```text
update_subtask bad escape：0 ✅
finish_plan：Task graph finished. ✅
report_validation：PASS ✅
```

仍有 5 个错误，但都不是基础设施错误：

```text
create_plan 1 次：预期技能门禁拒绝
create_plan 1 次：模型引用不存在的 dep 'ctx'
finish_plan 3 次：报告尚未校验，模型过早收尾
```

这 5 个属于模型规划/收尾顺序问题，不是 `bad escape` 或权限问题；
后续可通过更强 prompt 约束，但不阻塞当前机制。

## 6. 待办

1. ~~用 Host 身份新建会话，跑完整终极大考，确认模型在最终答复前调用 `finish_plan`~~（`ses_caJdEWmV` 已通过）；
2. 用 Host 身份新建会话，验证 P1 的 9 个 required 技能全部读取、create_plan/finish_plan 通过；
3. 把上述三个文件迁回 `D:\QwenPaw-Data\packages\...` 源码，并用 openspec 立项；
4. 补测试：`skill_router` 纯函数、create_plan 拒绝、finish_plan 拒绝；
5. 与 data-analysis-agent 的 `add-skill-router-required-skills` 对齐契约；
6. 评估 UI 模型切换（Host 默认模型仍是旧 doubao）。
