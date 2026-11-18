"""QwenPaw-Data 侧最小技能路由（P0）。

只做两件事：
1. 由计划文本推断本轮 required 技能；
2. 从 RuntimeStateManager 的 trace 中提取实际读过的 SKILL.md 技能名。

规则保守：未命中特定任务类型时 required 为空，不阻断普通查数。
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

_RULES = (
    (
        "volatility_attribution",
        ("波动", "归因", "为什么涨", "为什么跌", "涨跌", "拖累", "拉动", "贡献", "变化原因", "环比"),
        ("bi-metric-analysis", "bi-attribution-analysis", "bi-dimension-drilldown", "bi-report-generation"),
        ("bi-anomaly-detection",),
    ),
    (
        "anomaly",
        ("异常", "离群", "突增", "突降", "异常点", "异动", "阈值"),
        ("bi-anomaly-detection", "bi-attribution-analysis", "bi-report-generation"),
        ("bi-dimension-drilldown",),
    ),
    (
        "clustering",
        ("分群", "聚类", "客群", "象限", "分层"),
        ("bi-clustering", "bi-dashboard-generation"),
        ("bi-distribution-analysis",),
    ),
    (
        "funnel",
        ("漏斗", "转化率", "转化漏斗"),
        ("bi-funnel-analysis", "bi-conversion-rate", "bi-report-generation"),
        ("bi-comparison-analysis",),
    ),
    (
        "cohort_retention",
        ("同期群", "留存", "复购", "cohort"),
        ("bi-cohort-analysis", "bi-retention-analysis", "bi-report-generation"),
        ("bi-retention-rate",),
    ),
    (
        "comparison",
        ("对比", "差异", "比较", "优劣", "一致性"),
        ("bi-comparison-analysis", "bi-report-generation"),
        ("bi-attribution-analysis",),
    ),
    (
        "causal",
        ("因果", "因果推断", "效应估计", "did", "psm", "断点", "工具变量", "面板效应"),
        ("causal-analysis-skill",),
        ("data-science-analysis",),
    ),
)

_SKILL_PATH = re.compile(r"skills/([^/]+)/([^/]+)/SKILL\.md")

# P1：过程/契约类技能。它们不负责某一种分析方法，但 QwenPaw 自己的
# SKILL.md 写明“必须/优先”加载；P0 只路由了核心方法技能，导致这些被绕过。
_ALWAYS_REQUIRED = (
    "skill-hub-guide",   # 任何数据分析前先了解技能体系
    "runtime-guide",     # 产物落盘、异常处理、质量自检的强制规范
)

# 只有计划里出现对应动作时才要求，避免把“所有任务”都变成读全部 guide。
_CONDITIONAL_REQUIRED = (
    (
        "fetch-data",
        ("取数", "sql", "execute_sql", "查询", "拉数", "查数", "数据获取", "取数据", "拉取数据", "查询数据", "全量数据"),
        "计划包含取数/SQL，需要 fetch-data 的取数纪律",
    ),
    (
        "bi-semantic-layer-guide",
        ("口径", "语义", "指标定义", "维度", "search_context", "元数据"),
        "计划包含口径/语义/维度确认，需要语义层使用规范",
    ),
    (
        "bi-causal-attribution",
        ("事件", "活动", "search_event", "外部", "原因", "因果"),
        "计划包含事件/外部证据检索，需要事件归因方法",
    ),
)

# 核心方法技能之外的“相关但可放宽”项：只提示，不阻断。
_OPTIONAL_BY_TASK = {
    "volatility_attribution": ("bi-anomaly-detection", "bi-comparison-analysis"),
    "anomaly": ("bi-adaptive-threshold",),
    "comparison": ("bi-metric-observation",),
}


def _dedupe(names: list[str]) -> list[str]:
    return list(dict.fromkeys(n for n in names if n))


def route(text: str) -> dict[str, Any]:
    blob = re.sub(r"\s+", " ", str(text or "")).lower()
    for task_type, patterns, required, optional in _RULES:
        matched = [p for p in patterns if p.lower() in blob]
        if matched:
            conditional: list[str] = []
            conditional_reasons: list[str] = []
            for name, triggers, reason in _CONDITIONAL_REQUIRED:
                if any(t.lower() in blob for t in triggers):
                    conditional.append(name)
                    conditional_reasons.append(f"{name}: {reason}")
            required_all = _dedupe(
                list(_ALWAYS_REQUIRED) + list(required) + conditional
            )
            optional_all = _dedupe(
                list(optional) + list(_OPTIONAL_BY_TASK.get(task_type, ()))
            )
            # 已经 required 的不要再出现在 optional 里。
            optional_all = [n for n in optional_all if n not in required_all]
            return {
                "task_type": task_type,
                "required": required_all,
                "optional": optional_all,
                "matched": matched,
                "required_groups": {
                    "process": list(_ALWAYS_REQUIRED),
                    "core": list(required),
                    "conditional": conditional,
                },
                "conditional_reasons": conditional_reasons,
            }
    return {
        "task_type": "generic",
        "required": [],
        "optional": [],
        "matched": [],
        "required_groups": {},
        "conditional_reasons": [],
    }


def skills_from_traces(traces: Any) -> list[str]:
    """从 trace 里找 `.../skills/<layer>/<name>/SKILL.md`，返回去重技能名。"""
    try:
        blob = json.dumps(traces, ensure_ascii=False, default=str)
        # JSON 转义后的 Windows 反斜杠（\\）先归一成 /，否则 regex 找不到 skills/...。
        blob = blob.replace("\\\\", "/")
    except Exception:
        return []
    found: list[str] = []
    for layer, name in _SKILL_PATH.findall(blob):
        # QwenPaw 常见路径是 skills/default/<name>；若没有 default，取最后一级
        skill = name if layer == "default" else name
        if skill and skill != "*" and skill not in found:
            found.append(skill)
    # QwenPaw 的 Skill 工具不一定带文件路径，参数是 {"skill": "<name>"}。
    for skill in re.findall(r'"skill"\s*:\s*"([^"]+)"', blob):
        if skill and skill != "*" and skill not in found:
            found.append(skill)
    return found

