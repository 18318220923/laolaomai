#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp-order-agent 主执行脚本。

职责：
1. 解析用户自然语言指令，提取预算、口味、忌口、热量/份量约束、门店和取餐方式；
2. 调用 MCP 工具（菜单、优惠券、算价、营养信息）检索与验证；
3. 生成 2-4 个候选方案并排序，输出可解释推荐。

本脚本不负责下单。下单必须由用户明确确认后另行调用下单 MCP 工具。

用法：
    python main.py "预算25块，想吃带肉的，不要太撑" \
        [--budget 25] [--store_id S001] [--pickup_type 自提] \
        [--model_provider qwen] [--mcp_server mcd]

注意：MCP 工具调用通过 MCP 客户端注入。在没有 MCP Server 的本地环境中，
脚本会以 mock 模式运行，便于验证工具调用链路（数据非真实，禁止用于实际下单）。
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class ParsedIntent:
    """从自然语言解析出的点单约束。"""
    budget: Optional[float] = None
    preferences: List[str] = field(default_factory=list)   # 口味偏好：带肉/辣/清淡...
    constraints: List[str] = field(default_factory=list)   # 约束：不想太撑/低热量/忌口...
    store_id: Optional[str] = None
    pickup_type: Optional[str] = None                      # 堂食/自提/配送

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MealItem:
    name: str
    price: float
    calories: Optional[int] = None


@dataclass
class Proposal:
    """一个候选点单方案。"""
    items: List[MealItem]
    original_price: float
    discounted_price: float
    savings: float
    calories_total: Optional[int]
    reason: str
    coupon_used: Optional[str] = None
    price_confirmed: bool = False  # 是否经 MCP 算价工具验证


# ---------------------------------------------------------------------------
# 意图解析（规则版，可替换为大模型，见 references/prompt_template.md）
# ---------------------------------------------------------------------------

BUDGET_PATTERNS = [
    r"预算\s*(\d+(?:\.\d+)?)\s*[块元]",
    r"(\d+(?:\.\d+)?)\s*[块元]\s*(?:以内|以内?|以下|之内|以内)",
    r"[不超过|最多]\s*(\d+(?:\.\d+)?)\s*[块元]?",
    r"(\d+(?:\.\d+)?)\s*[块元]\s*以内",
]

PREFERENCE_KEYWORDS = {
    "带肉": ["带肉", "有肉", "吃肉", "肉"],
    "辣": ["辣", "香辣", "麻辣"],
    "不辣": ["不辣", "不要辣", "清淡"],
    "清淡": ["清淡", "不辣"],
}

CONSTRAINT_KEYWORDS = {
    "不想太撑": ["不想太撑", "别太撑", "不要太撑", "不太撑", "少吃点"],
    "低热量": ["低热量", "热量低", "减肥", "控卡", "轻食"],
    "少油": ["少油", "不油", "清爽"],
}

PICKUP_KEYWORDS = {
    "堂食": ["堂食", "在店里吃", "店里吃"],
    "自提": ["自提", "带走", "打包"],
    "配送": ["配送", "外卖", "送到", "送餐"],
}


def parse_intent(query: str) -> ParsedIntent:
    intent = ParsedIntent()
    text = query.strip()

    # 预算
    for pat in BUDGET_PATTERNS:
        m = re.search(pat, text)
        if m:
            intent.budget = float(m.group(1))
            break

    # 口味偏好
    for key, kws in PREFERENCE_KEYWORDS.items():
        if any(kw in text for kw in kws):
            if key == "清淡" and "辣" in intent.preferences:
                continue
            intent.preferences.append(key)

    # 约束条件
    for key, kws in CONSTRAINT_KEYWORDS.items():
        if any(kw in text for kw in kws):
            intent.constraints.append(key)

    # 取餐方式
    for key, kws in PICKUP_KEYWORDS.items():
        if any(kw in text for kw in kws):
            intent.pickup_type = key
            break

    return intent


# ---------------------------------------------------------------------------
# 可选：大模型意图解析（规则解析的增强，失败自动回退）
# ---------------------------------------------------------------------------
#
# 通过环境变量启用（OpenAI 兼容接口，通义千问/Kimi/DeepSeek 均提供该格式）：
#   MCP_ORDER_LLM_BASE_URL  如 https://dashscope.aliyuncs.com/compatible-mode/v1
#   MCP_ORDER_LLM_API_KEY   从环境变量读取，禁止硬编码
#   MCP_ORDER_LLM_MODEL     如 qwen-plus / moonshot-v1-8k / deepseek-chat
# 未配置时自动使用规则解析。

_LLM_INTENT_PROMPT = """你是点单意图解析器。从用户输入中提取以下字段，以纯 JSON 输出，不要输出其他内容：
- budget: 预算上限（数字，无则 null）
- preferences: 口味偏好数组，可选值["带肉","辣","不辣","清淡","咖啡","甜品","解腻","早餐"]
- constraints: 约束数组，可选值["不想太撑","低热量","少油"]
- pickup_type: 取餐方式，可选值["堂食","自提","配送"]，无则 null
无法确定的字段保持 null 或空数组，禁止猜测。

用户输入：{query}"""


def parse_intent_llm(query: str, timeout: float = 10.0) -> Optional[ParsedIntent]:
    """调用 OpenAI 兼容接口解析意图。失败或未配置返回 None（调用方回退规则解析）。"""
    import os
    import urllib.request

    base_url = os.environ.get("MCP_ORDER_LLM_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("MCP_ORDER_LLM_API_KEY")
    model = os.environ.get("MCP_ORDER_LLM_MODEL")
    if not (base_url and api_key and model):
        return None

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user",
                      "content": _LLM_INTENT_PROMPT.format(query=query)}],
        "temperature": 0,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/chat/completions", data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        # 剥离可能的 markdown 代码块
        m = re.search(r"\{.*\}", content, re.S)
        parsed = json.loads(m.group(0)) if m else {}
        intent = ParsedIntent()
        if isinstance(parsed.get("budget"), (int, float)) and parsed["budget"] > 0:
            intent.budget = float(parsed["budget"])
        for v in parsed.get("preferences") or []:
            if isinstance(v, str) and v not in intent.preferences:
                intent.preferences.append(v)
        for v in parsed.get("constraints") or []:
            if isinstance(v, str) and v not in intent.constraints:
                intent.constraints.append(v)
        if parsed.get("pickup_type") in ("堂食", "自提", "配送"):
            intent.pickup_type = parsed["pickup_type"]
        return intent
    except Exception as e:
        print(f"[LLM] 意图解析失败，回退规则解析: {e}", file=sys.stderr)
        return None


def resolve_intent(query: str, use_llm: bool = True) -> ParsedIntent:
    """LLM 优先，规则兜底。"""
    if use_llm:
        intent = parse_intent_llm(query)
        if intent is not None:
            return intent
    return parse_intent(query)


# ---------------------------------------------------------------------------
# MCP 工具调用层
# ---------------------------------------------------------------------------

class McpClient:
    """MCP 工具调用客户端。

    实际部署时，通过 MCP 协议连接餐饮 MCP Server（菜单/优惠券/算价/营养）。
    本地无 Server 时自动进入 mock 模式，仅用于调试链路，数据不真实。
    """

    def __init__(self, mcp_server: Optional[str] = None, mock: bool = False):
        self.mcp_server = mcp_server
        self.mock = mock or mcp_server is None
        if self.mock:
            print("[MCP] 未指定 mcp_server，使用 mock 模式（数据仅供链路调试，"
                  "禁止用于实际下单）", file=sys.stderr)

    # ---- 菜单 ----
    def query_meals(self, store_id: Optional[str]) -> List[MealItem]:
        if self.mock:
            return [
                MealItem("麦香鸡腿堡", 18.0, 550),
                MealItem("板烧鸡腿堡", 21.5, 620),
                MealItem("巨无霸", 24.0, 720),
                MealItem("麦辣鸡翅(2块)", 12.0, 280),
                MealItem("蔬菜沙拉", 15.0, 120),
                MealItem("小份薯条", 11.0, 230),
                MealItem("可乐(中)", 9.0, 180),
                MealItem("零度可乐(中)", 9.0, 5),
            ]
        # 实际接入：调用 MCP 菜单工具，如 query-meals
        raise NotImplementedError("请接入餐饮 MCP Server 的菜单查询工具")

    # ---- 优惠券 ----
    def query_coupons(self, store_id: Optional[str]) -> List[Dict[str, Any]]:
        if self.mock:
            return [
                {"id": "C1", "name": "汉堡第二份半价", "min_spend": 18.0, "discount": 9.0, "applicable": ["麦香鸡腿堡"]},
                {"id": "C2", "name": "满25减5", "min_spend": 25.0, "discount": 5.0, "applicable": None},
            ]
        raise NotImplementedError("请接入餐饮 MCP Server 的优惠券查询工具")

    # ---- 算价 ----
    def calculate_price(self, items: List[MealItem], coupon: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """返回 {'original_price', 'discounted_price', 'valid'}。

        只有 valid=True 时，价格才视为"经算价工具验证"。
        """
        if self.mock:
            original = sum(i.price for i in items)
            discount = 0.0
            if coupon:
                if coupon.get("applicable") and not any(
                        i.name in coupon["applicable"] for i in items):
                    discount = 0.0
                elif original >= coupon.get("min_spend", 0):
                    discount = coupon["discount"]
            return {"original_price": round(original, 2),
                    "discounted_price": round(original - discount, 2),
                    "valid": True}
        raise NotImplementedError("请接入餐饮 MCP Server 的算价工具")

    # ---- 营养信息 ----
    def query_nutrition(self, item_name: str) -> Optional[int]:
        if self.mock:
            return None  # 已含在菜单 mock 数据中
        raise NotImplementedError("请接入餐饮 MCP Server 的营养信息工具")


# ---------------------------------------------------------------------------
# 方案生成
# ---------------------------------------------------------------------------

def build_proposals(client: McpClient, intent: ParsedIntent,
                    max_proposals: int = 4) -> List[Proposal]:
    meals = client.query_meals(intent.store_id)
    coupons = client.query_coupons(intent.store_id)

    # 简单过滤：按偏好带肉/低热量筛选候选
    meat_names = ["堡", "鸡", "肉"]
    low_cal = intent.constraints and ("低热量" in intent.constraints or "不想太撑" in intent.constraints)

    if "带肉" in intent.preferences:
        pool = [m for m in meals if any(k in m.name for k in meat_names)]
    else:
        pool = list(meals)
    if low_cal:
        pool = [m for m in meals if (m.calories or 0) <= 400] + pool[:2]
    if not pool:
        pool = meals[:3]

    proposals: List[Proposal] = []
    # 策略：单主食 / 主食+小食 / 主食+饮品 / 双主食比价
    combos = [
        pool[:1],
        pool[:1] + [m for m in meals if "薯条" in m.name][:1],
        pool[:1] + [m for m in meals if "可乐" in m.name][:1],
        pool[:2],
    ]
    for combo in combos:
        if not combo:
            continue
        best: Optional[Proposal] = None
        for coupon in [None] + coupons:
            price = client.calculate_price(combo, coupon)
            if not price.get("valid"):
                continue
            orig, disc = price["original_price"], price["discounted_price"]
            if intent.budget is not None and disc > intent.budget:
                continue
            cal = sum(i.calories or 0 for i in combo)
            savings = round(orig - disc, 2)
            reason = _reason(combo, coupon, savings, intent)
            p = Proposal(
                items=combo, original_price=orig, discounted_price=disc,
                savings=savings, calories_total=cal or None,
                coupon_used=coupon["name"] if coupon else None,
                reason=reason, price_confirmed=True,
            )
            if best is None or p.discounted_price < best.discounted_price:
                best = p
        if best:
            proposals.append(best)

    # 排序：性价比（省钱）> 价格
    proposals.sort(key=lambda p: (p.savings, -p.discounted_price), reverse=False)
    proposals = proposals[:max_proposals]

    if not proposals:
        # 预算不足或无合适商品的替代建议
        cheapest = sorted(meals, key=lambda m: m.price)[:2]
        proposals.append(Proposal(
            items=cheapest,
            original_price=sum(m.price for m in cheapest),
            discounted_price=sum(m.price for m in cheapest),
            savings=0.0,
            calories_total=sum(m.calories or 0 for m in cheapest) or None,
            reason="未找到满足全部约束的方案；以上为最便宜的替代组合。可考虑提高预算、"
                   "更换门店或放宽口味约束。",
        ))
    return proposals


def _reason(combo, coupon, savings, intent) -> str:
    parts = []
    if "带肉" in intent.preferences:
        parts.append("满足带肉偏好")
    if "低热量" in intent.constraints:
        parts.append("热量相对较低")
    if "不想太撑" in intent.constraints:
        parts.append("份量适中不易吃撑")
    if coupon:
        parts.append(f"用券「{coupon['name']}」节省 {savings} 元")
    else:
        parts.append("未使用优惠券")
    return "；".join(parts)


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

def format_proposals(proposals: List[Proposal]) -> str:
    lines = []
    for idx, p in enumerate(proposals, 1):
        items = " + ".join(i.name for i in p.items)
        cal = f"{p.calories_total} kcal" if p.calories_total else "热量信息缺失（以下单页为准）"
        lines.append(
            f"### 方案 {idx}\n"
            f"- 商品组合：{items}\n"
            f"- 原价：¥{p.original_price}\n"
            f"- 用券后价格：¥{p.discounted_price}\n"
            f"- 节省金额：¥{p.savings}\n"
            f"- 热量/份量：约 {cal}\n"
            f"- 推荐理由：{p.reason}\n"
            + (f"- ⚠️ 价格需以下单页为准\n" if not p.price_confirmed else "")
        )
    lines.append("\n> 请选择一个方案（回复方案编号），确认后将生成下单确认卡。本 Agent 不会未经确认下单。")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP 点单 Agent")
    parser.add_argument("user_query", help="用户原始自然语言需求")
    parser.add_argument("--budget", type=float, default=None, help="预算上限")
    parser.add_argument("--store_id", default=None, help="门店 ID")
    parser.add_argument("--pickup_type", default=None, choices=["堂食", "自提", "配送"])
    parser.add_argument("--model_provider", default=None,
                        choices=["qwen", "kimi", "deepseek", "claude"])
    parser.add_argument("--mcp_server", default=None, help="餐饮 MCP Server 标识")
    parser.add_argument("--no-llm", action="store_true",
                        help="禁用大模型意图解析，强制使用规则解析")
    args = parser.parse_args()

    intent = resolve_intent(args.user_query, use_llm=not args.no_llm)
    # 显式参数优先于解析结果
    if args.budget is not None:
        intent.budget = args.budget
    if args.store_id:
        intent.store_id = args.store_id
    if args.pickup_type:
        intent.pickup_type = args.pickup_type

    print("[Intent] " + json.dumps(intent.to_dict(), ensure_ascii=False))
    client = McpClient(mcp_server=args.mcp_server)
    proposals = build_proposals(client, intent)
    print(format_proposals(proposals))
    return 0


if __name__ == "__main__":
    sys.exit(main())
