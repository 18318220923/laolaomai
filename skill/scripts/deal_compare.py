#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""外部团购渠道比价（美团/抖音等）。

原则：外部平台（美团、抖音等）的团购券/优惠没有官方数据连接器时，
不得抓取或编造价格。由用户提供券面信息（价格、内容、有效期），
本脚本负责与 MCP 算价结果做同台对比，并标注"外部渠道，价格以平台下单页为准"。

用法：
    python deal_compare.py \
        --mcp '{"original_price":29.0,"discounted_price":20.9,"valid":true}' \
        --external '[{"platform":"美团","title":"麦当劳单人餐团购券","price":19.9,"items":"麦香鸡+中薯+中可","valid_to":"2026-11-30"}]'
"""

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from price_calculator import compute_savings, PriceDataError


def compare_deals(mcp_price: Dict[str, Any],
                  external_deals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """对比官方实付价与外部团购价。

    返回:
        {
          "official": {... 经算价工具验证 ...},
          "external": [... 各外部券标注 ...],
          "best": "official" | 外部平台名 | None,
          "notes": [...]
        }
    """
    result: Dict[str, Any] = {"official": None, "external": [], "best": None,
                              "notes": []}
    official_price: Optional[float] = None
    try:
        r = compute_savings(mcp_price)
        official_price = r["discounted_price"]
        result["official"] = {
            "source": "麦当劳官方（MCP 算价工具验证）",
            "original_price": r["original_price"],
            "price": official_price,
            "savings": r["savings"],
            "verified": True,
        }
    except PriceDataError as e:
        result["notes"].append(f"官方价格未能验证（{e}），价格需以下单页为准")

    best_price = official_price
    best_source = "official" if official_price is not None else None

    for d in external_deals:
        platform = d.get("platform", "外部平台")
        price = d.get("price")
        entry = {
            "platform": platform,
            "title": d.get("title", "未命名优惠"),
            "price": price,
            "items": d.get("items", "内容未提供"),
            "valid_to": d.get("valid_to", "有效期未提供"),
            "verified": False,  # 外部渠道一律未验证
            "disclaimer": "外部渠道，价格以平台下单页为准",
        }
        result["external"].append(entry)
        if isinstance(price, (int, float)) and price > 0:
            if best_price is None or price < best_price:
                best_price = price
                best_source = platform

    result["best"] = best_source
    if result["external"]:
        result["notes"].append("外部渠道价格由用户提供，未经官方算价工具验证，请以下单页为准")
    return result


def format_comparison(result: Dict[str, Any]) -> str:
    lines = ["## 🔍 多渠道比价\n"]
    off = result.get("official")
    if off:
        lines.append(f"**官方（已验证）**：实付 ¥{off['price']}（原价 ¥{off['original_price']}，省 ¥{off['savings']}）")
    else:
        lines.append("**官方**：价格未验证，以下单页为准")
    for e in result["external"]:
        lines.append(f"**{e['platform']}**：¥{e['price']} — {e['title']}（{e['items']}，有效期至 {e['valid_to']}）⚠️ 外部渠道，以下单页为准")
    if result.get("best"):
        lines.append(f"\n🏆 当前最低渠道：**{result['best']}**")
    for n in result.get("notes", []):
        lines.append(f"> ⚠️ {n}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="外部团购渠道比价")
    parser.add_argument("--mcp", required=True, help="MCP 算价结果 JSON")
    parser.add_argument("--external", default="[]", help="外部团购券 JSON 数组（用户提供）")
    args = parser.parse_args()

    try:
        mcp_price = json.loads(args.mcp)
        external = json.loads(args.external)
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}", file=sys.stderr)
        return 1
    if not isinstance(external, list):
        print("--external 必须是 JSON 数组", file=sys.stderr)
        return 1

    print(format_comparison(compare_deals(mcp_price, external)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
