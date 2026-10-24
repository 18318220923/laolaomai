#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""根据 MCP 算价结果计算节省金额。

只信任 MCP 算价工具返回的数据：
- 数据不完整（缺 original_price / discounted_price / valid）时返回错误，
  调用方必须如实提示"价格需以下单页为准"，不得自行编造价格或优惠。

用法（作为库）：
    from price_calculator import compute_savings
    result = compute_savings({"original_price": 30.0, "discounted_price": 25.0, "valid": True})

用法（命令行）：
    python price_calculator.py '{"original_price": 30.0, "discounted_price": 25.0, "valid": true}'
"""

import json
import sys
from typing import Any, Dict, Optional

def _normalize(price_result: Dict[str, Any]) -> Dict[str, Any]:
    """兼容两种算价返回格式，统一为：
    {original_price, discounted_price, unit:"元", valid, extras}

    格式1（简化/技能内部）: original_price / discounted_price（单位：元）
    格式2（真实 mcd-mcp）: originalPrice / price / discount（单位：分），
      含 takeWayList、enjoyed、enjoyable 等字段。
    """
    # 真实 mcd-mcp 格式：字段名为驼峰，单位分
    if "price" in price_result and "originalPrice" in price_result:
        def fen(key: str) -> Optional[float]:
            v = price_result.get(key)
            return round(v / 100, 2) if isinstance(v, (int, float)) else None
        extras = {}
        take_ways = [t.get("title") for t in price_result.get("takeWayList") or []
                     if isinstance(t, dict)]
        if take_ways:
            extras["take_ways"] = take_ways
        for k in ("enjoyed", "enjoyable"):
            if isinstance(price_result.get(k), dict):
                extras[k] = price_result[k]
        return {
            "original_price": fen("originalPrice"),
            "discounted_price": fen("price"),
            "delivery_price": fen("deliveryPrice"),
            "packing_price": fen("packingPrice"),
            "valid": True,  # mcd-mcp 成功返回即视为已验证
            "extras": extras,
        }
    # 简化格式
    out = dict(price_result)
    out.setdefault("extras", {})
    return out


REQUIRED_FIELDS = ("original_price", "discounted_price")


class PriceDataError(Exception):
    """MCP 算价数据不完整或无效。"""


def compute_savings(price_result: Dict[str, Any]) -> Dict[str, Any]:
    """校验 MCP 算价结果并计算节省金额。

    返回:
        {"original_price", "discounted_price", "savings", "confirmed"}

    Raises:
        PriceDataError: 数据不完整或算价工具未通过校验。
    """
    if not isinstance(price_result, dict):
        raise PriceDataError("算价结果必须是字典")

    price_result = _normalize(price_result)

    missing = [f for f in REQUIRED_FIELDS if price_result.get(f) is None]
    if missing:
        raise PriceDataError(f"算价数据缺少字段: {', '.join(missing)}")

    if not price_result.get("valid", False):
        raise PriceDataError("算价工具返回 valid=false，价格未经核实")

    try:
        original = float(price_result["original_price"])
        discounted = float(price_result["discounted_price"])
    except (TypeError, ValueError):
        raise PriceDataError("价格字段无法解析为数字")

    if original < 0 or discounted < 0:
        raise PriceDataError("价格不能为负数")
    if discounted > original:
        raise PriceDataError("用券后价格高于原价，数据异常，需人工核实")

    return {
        "original_price": round(original, 2),
        "discounted_price": round(discounted, 2),
        "savings": round(original - discounted, 2),
        "delivery_price": price_result.get("delivery_price"),
        "packing_price": price_result.get("packing_price"),
        "extras": price_result.get("extras", {}),
        "confirmed": True,
    }


def summarize(price_result: Dict[str, Any],
              coupon_name: Optional[str] = None) -> str:
    """输出人类可读的价格摘要；数据异常时返回降级提示。"""
    try:
        r = compute_savings(price_result)
    except PriceDataError as e:
        return f"⚠️ 价格信息不完整（{e}），价格需以下单页为准。"
    coupon = f"（用券：{coupon_name}）" if coupon_name else ""
    return (f"原价 ¥{r['original_price']}{coupon}，"
            f"用券后 ¥{r['discounted_price']}，节省 ¥{r['savings']}。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    try:
        data = json.loads(sys.argv[1])
        print(json.dumps(compute_savings(data), ensure_ascii=False, indent=2))
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}", file=sys.stderr)
        sys.exit(1)
    except PriceDataError as e:
        print(f"⚠️ {e}（价格需以下单页为准）", file=sys.stderr)
        sys.exit(2)
