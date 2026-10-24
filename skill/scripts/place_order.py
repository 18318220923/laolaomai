#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下单链路：确认卡 → 口令校验 → 调用下单（默认 dry-run）。

硬性规则：
- 不传 --confirm "确认下单" 时，只输出确认卡，绝不调用下单逻辑；
- 口令不严格等于「确认下单」时视为取消；
- 默认 --dry-run，不下真实单；真实下单需额外加 --execute；
- 本脚本不经手支付，下单后只返回支付引导信息。

用法：
    # 第一步：生成确认卡（不会下单）
    python place_order.py --store "麦当劳科技园店" --pickup_type 自提 \
        --items '[{"name":"麦香鸡腿堡","qty":1,"price":18.0}]' --total 18.0

    # 第二步：用户确认后执行（默认仍 dry-run；真实下单需显式 --execute）
    python place_order.py ... --confirm "确认下单"
    python place_order.py ... --confirm "确认下单" --execute --mcp_server mcd
"""

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from order_confirm import build_confirm_card

CONFIRM_TOKEN = "确认下单"


def request_order(store: str, pickup_type: str, items: List[Dict[str, Any]],
                  total_price: float, coupon: Optional[str] = None,
                  confirm: Optional[str] = None,
                  execute: bool = False,
                  mcp_server: Optional[str] = None) -> Dict[str, Any]:
    """下单请求。返回状态字典。

    状态:
        - "pending_confirm": 未确认，仅返回确认卡文本
        - "cancelled": 口令不符，取消
        - "dry_run": 已确认但未 --execute，模拟成功
        - "submitted": 已确认且 --execute，调用 MCP 下单（未实现时需接入）
    """
    card = build_confirm_card(store, pickup_type, items, total_price, coupon)

    if confirm is None:
        return {"status": "pending_confirm", "confirm_card": card,
                "message": "请核对确认卡，回复「确认下单」以继续；其他内容视为取消。"}

    if confirm != CONFIRM_TOKEN:
        return {"status": "cancelled", "confirm_card": card,
                "message": f"口令「{confirm}」不等于「{CONFIRM_TOKEN}」，已取消，未创建订单。"}

    if not execute:
        return {"status": "dry_run", "confirm_card": card,
                "message": "已确认（dry-run 模式，未真实下单）。加 --execute 才会调用 MCP 下单工具。"}

    if not mcp_server:
        return {"status": "error", "confirm_card": card,
                "message": "--execute 需要指定 --mcp_server（餐饮 MCP Server 标识）。"}

    # 真实下单：调用 MCP create-order 工具。
    # 注意：本函数不承担支付；支付由下单工具/麦当劳侧引导完成。
    raise NotImplementedError(
        "真实下单需接入 MCP create-order 工具（含地址/手机号时须再次向用户二次确认）。")


def main() -> int:
    parser = argparse.ArgumentParser(description="下单链路（默认 dry-run）")
    parser.add_argument("--store", required=True)
    parser.add_argument("--pickup_type", default=None)
    parser.add_argument("--items", required=True, help="JSON 数组")
    parser.add_argument("--total", type=float, required=True)
    parser.add_argument("--coupon", default=None)
    parser.add_argument("--confirm", default=None, help=f"必须严格等于「{CONFIRM_TOKEN}」")
    parser.add_argument("--execute", action="store_true", help="真实下单（需配合 --mcp_server）")
    parser.add_argument("--mcp_server", default=None)
    args = parser.parse_args()

    try:
        items = json.loads(args.items)
    except json.JSONDecodeError as e:
        print(f"items JSON 解析失败: {e}", file=sys.stderr)
        return 1

    try:
        result = request_order(args.store, args.pickup_type, items, args.total,
                               args.coupon, args.confirm, args.execute,
                               args.mcp_server)
    except (ValueError, NotImplementedError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    print(result["confirm_card"])
    print(f"\n[{result['status']}] {result['message']}")
    return 0 if result["status"] != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
