#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成下单确认卡。

在任何下单 MCP 工具调用之前，必须先生成确认卡并获得用户明确同意。

用法（作为库）：
    from order_confirm import build_confirm_card
    card = build_confirm_card(
        store="麦当劳 深圳科技园店",
        pickup_type="自提",
        items=[{"name": "麦香鸡腿堡", "qty": 1, "price": 18.0}],
        coupon="满25减5",
        total_price=25.0,
        proposal_no=2,
    )

用法（命令行）：
    python order_confirm.py --store "麦当劳科技园店" --pickup_type 自提 \
        --items '[{"name":"麦香鸡腿堡","qty":1,"price":18.0}]' \
        --total 25.0 --coupon "满25减5"
"""

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

# 模板文件位置（技能根目录下）
TEMPLATE_PATH = None
TEMPLATE_PATH_CUTE = None
try:
    from pathlib import Path
    _assets = Path(__file__).resolve().parent.parent / "assets"
    TEMPLATE_PATH = _assets / "order_card_template.md"
    TEMPLATE_PATH_CUTE = _assets / "order_card_template_cute.md"
except NameError:
    pass


def _load_template(theme: str = "default") -> str:
    path = TEMPLATE_PATH_CUTE if theme == "cute" else TEMPLATE_PATH
    if path and path.exists():
        return path.read_text(encoding="utf-8")
    if theme == "cute":
        return (
            "🎀 ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ 🎀\n\n"
            "## 🌸 下单确认卡 {proposal_no}\n\n"
            "💗 **门店**：{store}\n"
            "🧁 **取餐方式**：{pickup_type}\n\n"
            "**🍔 商品清单**\n{items}\n\n"
            "🎀 **优惠券**：{coupon}\n"
            "💰 **实付金额**：¥{total_price}\n\n"
            "🎀 ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ ┈ 🎀\n\n"
            "> ⚠️ 确认以上信息没错的话，回复「**确认下单**」就好啦～\n"
            "> 回复其他内容视为取消，不会创建订单，也不会扣款哦。\n"
        )
    return (
        "## 🧾 下单确认卡\n"
        "- 门店：{store}\n"
        "- 取餐方式：{pickup_type}\n"
        "- 商品：{items}\n"
        "- 优惠券：{coupon}\n"
        "- 实付金额：¥{total_price}\n\n"
        "> 请回复「确认下单」以继续；回复其他内容视为取消。"
    )


def build_confirm_card(store: str, pickup_type: str,
                       items: List[Dict[str, Any]],
                       total_price: float,
                       coupon: Optional[str] = None,
                       proposal_no: Optional[int] = None,
                       note: Optional[str] = None,
                       theme: str = "default") -> str:
    """渲染下单确认卡文本。

    参数缺关键信息（门店、商品、实付金额）时抛 ValueError，禁止生成不完整确认卡。
    theme: "default" | "cute"（可爱风，见 references/cute_theme.md）
    """
    if not store:
        raise ValueError("确认卡缺少门店信息")
    if not items:
        raise ValueError("确认卡缺少商品信息")
    if total_price is None or total_price < 0:
        raise ValueError("确认卡缺少有效实付金额")

    items_text = "\n".join(
        f"  - {it.get('name', '未知商品')} × {it.get('qty', 1)} = ¥{it.get('price', 0)}"
        for it in items
    )
    card = _load_template(theme)
    if proposal_no:
        card = card.replace("{proposal_no}", str(proposal_no))
    card = card.replace("{store}", store)
    card = card.replace("{pickup_type}", pickup_type or "自提（默认）")
    card = card.replace("{items}", items_text)
    card = card.replace("{coupon}", coupon or "无")
    card = card.replace("{total_price}", f"{total_price:.2f}")
    if note:
        card = card.replace("{note}", note)
    card = card.replace("{note}", "—")
    return card


def main() -> int:
    parser = argparse.ArgumentParser(description="生成下单确认卡")
    parser.add_argument("--store", required=True)
    parser.add_argument("--pickup_type", default=None)
    parser.add_argument("--items", required=True, help="JSON 数组：[{'name','qty','price'}]")
    parser.add_argument("--total", type=float, required=True)
    parser.add_argument("--coupon", default=None)
    parser.add_argument("--proposal_no", type=int, default=None)
    parser.add_argument("--theme", default="default", choices=["default", "cute"],
                        help="确认卡主题：default 简洁版 / cute 可爱风")
    args = parser.parse_args()

    try:
        items = json.loads(args.items)
    except json.JSONDecodeError as e:
        print(f"items JSON 解析失败: {e}", file=sys.stderr)
        return 1

    try:
        print(build_confirm_card(args.store, args.pickup_type, items,
                                 args.total, args.coupon, args.proposal_no,
                                 theme=args.theme))
        return 0
    except ValueError as e:
        print(f"无法生成确认卡: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
