#!/usr/bin/env python3
"""Render an AlphaSift result and send it to a Feishu custom bot."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


def _fmt(value: object, suffix: str = "") -> str:
    if value is None or value == "":
        return "暂无"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


def build_message(result: dict[str, object]) -> str:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    picks = result.get("picks") or []
    lines = [
        f"📊 A股稳健中长期候选｜运行日期 {now:%Y-%m-%d}",
        "筛选方式：规则过滤与评分；AI 仅辅助比较和解释，不构成买卖建议。",
        f"行情源：{result.get('snapshot_source') or '未知'}（截至运行时可获得的最新行情）；扫描 {result.get('snapshot_count', 0)} 只，规则筛后 {result.get('after_filter_count', 0)} 只。",
        f"AI 排序：{'成功' if result.get('llm_ranked') else '未成功，按规则得分排序'}。",
    ]

    degradation = result.get("degradation") or []
    source_errors = result.get("source_errors") or []
    if degradation or source_errors:
        details = [str(item) for item in [*degradation, *source_errors][:3]]
        lines.append("⚠️ 数据源状态：" + "；".join(details))
    if result.get("llm_market_view"):
        lines.extend(["", f"市场观察：{result['llm_market_view']}"])
    if result.get("llm_selection_logic"):
        lines.append(f"排序说明：{result['llm_selection_logic']}")
    if result.get("llm_portfolio_risk"):
        lines.append(f"组合风险：{result['llm_portfolio_risk']}")

    if not picks:
        lines.extend(["", "今日没有满足当前规则的候选。"])
    else:
        lines.extend(["", f"候选（最多 {min(len(picks), 5)} 只；供观察，不代表买入建议）："])
        for pick in picks[:5]:
            lines.extend([
                "",
                f"{pick.get('rank', '-')}. {pick.get('name', '未知')}（{pick.get('code', '')}）｜规则分 {_fmt(pick.get('screen_score'))}｜风险 {pick.get('risk_level') or '未标注'}",
                f"价格 {_fmt(pick.get('price'))}｜当日 {_fmt(pick.get('change_pct'), '%')}｜PE {_fmt(pick.get('pe_ratio'))}｜PB {_fmt(pick.get('pb_ratio'))}｜行业 {pick.get('industry') or '未知'}",
            ])
            thesis = pick.get("llm_thesis") or pick.get("ranking_reason")
            if thesis:
                lines.append(f"入选解释：{thesis}")
            risk = pick.get("risk_summary")
            if risk:
                lines.append(f"风险提示：{risk}")
            for label, key in (("需观察", "llm_watch_items"), ("风险标签", "llm_risks")):
                items = pick.get(key) or []
                if items:
                    lines.append(f"{label}：{'、'.join(map(str, items[:3]))}")

    lines.extend([
        "",
        "注意：免费行情源可能延迟、缺失或变更；若数据降级，请先核对行情和公司公告。此工具仅供学习研究。",
    ])
    return "\n".join(lines)


def main() -> int:
    input_path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/daily-result.json")
    webhook = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook:
        raise SystemExit("FEISHU_WEBHOOK_URL 未配置")
    result = json.loads(input_path.read_text(encoding="utf-8"))
    if not result.get("snapshot_count") or not result.get("snapshot_source"):
        raise SystemExit("行情快照无有效数据，停止推送，避免发送误导性结果")
    if result.get("snapshot_source") == "last_good_cache":
        raise SystemExit("当前只能取得历史缓存行情，停止推送，避免把旧数据当作最新结果")

    content = {"msg_type": "text", "content": {"text": build_message(result)}}
    request = Request(
        webhook,
        data=json.dumps(content, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SystemExit(f"飞书推送失败：{exc}") from exc
    if body.get("code", 0) != 0:
        raise SystemExit(f"飞书返回错误：{body}")
    print(f"已推送 {len(result.get('picks') or [])} 条候选到飞书。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
