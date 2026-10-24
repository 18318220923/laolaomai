#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""优惠券可用性校验。

按有效期、适用时段、适用渠道校验优惠券当前是否可用，避免推荐了用不了的券。

输入 JSON（数组），每张券字段（均可为空，缺失字段视为"不限制"）：
{
  "id": "C1", "name": "11.9元麦辣鸡腿堡",
  "valid_from": "2026-10-26 10:30",   # 生效时间，格式 YYYY-MM-DD HH:MM
  "valid_to":   "2026-10-30 23:59",   # 失效时间
  "weekdays": [1,2,3,4,5],            # 适用星期（1=周一），空=不限
  "channels": ["到店专用","外送专用"],  # 适用渠道，空=不限
  "discount_price": 11.9              # 券后价（展示用）
}

用法：
    python coupon_filter.py coupons.json --channel 到店 --now "2026-10-24 14:00"
    作为库：from coupon_filter import check_coupons
"""

import argparse
import json
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

TIME_FMTS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def _parse_time(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in TIME_FMTS:
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析时间: {s!r}（支持格式: {', '.join(TIME_FMTS)}）")


def check_coupon(coupon: Dict[str, Any], now: datetime,
                 channel: Optional[str] = None) -> Dict[str, Any]:
    """校验单张券。返回 {coupon 原字段..., usable, claimable, status, reason}

    status 三态：
        - "usable":    当前可用
        - "claimable": 可领取但未领取（需在用户同意后调用 auto-bind-coupons）
        - "unusable":  不可用（含原因）
    """
    # 未领取的券单独成态，不走可用性判断
    if coupon.get("claimable") and not coupon.get("claimed"):
        return {**coupon, "usable": False, "status": "claimable",
                "reason": "可领取（需用户同意后调用 auto-bind-coupons 一键领取）"}

    reasons: List[str] = []

    vf = _parse_time(coupon.get("valid_from"))
    vt = _parse_time(coupon.get("valid_to"))
    if vf and now < vf:
        reasons.append(f"尚未生效（{coupon['valid_from']} 起可用）")
    if vt and now > vt:
        reasons.append(f"已过期（{coupon['valid_to']} 截止）")

    weekdays = coupon.get("weekdays") or []
    if weekdays and (now.isoweekday() not in weekdays):
        reasons.append("今日不在券的适用星期内")

    channels = coupon.get("channels") or []
    if channel and channels:
        if not any(channel in c or c in channel for c in channels):
            reasons.append(f"渠道不匹配（券限 {'/'.join(channels)}，当前为{channel}）")

    return {
        **coupon,
        "usable": not reasons,
        "status": "usable" if not reasons else "unusable",
        "reason": "；".join(reasons) if reasons else "当前可用",
    }


def check_coupons(coupons: List[Dict[str, Any]], now: Optional[datetime] = None,
                  channel: Optional[str] = None) -> List[Dict[str, Any]]:
    now = now or datetime.now()
    return [check_coupon(c, now, channel) for c in coupons]


def main() -> int:
    parser = argparse.ArgumentParser(description="优惠券可用性校验")
    parser.add_argument("coupons_json", help="券 JSON 数组（字符串或 @文件路径）")
    parser.add_argument("--channel", default=None, help="当前渠道，如 到店 / 外送")
    parser.add_argument("--now", default=None, help="基准时间，默认当前")
    args = parser.parse_args()

    src = args.coupons_json
    if src.startswith("@"):
        with open(src[1:], encoding="utf-8") as f:
            src = f.read()
    try:
        coupons = json.loads(src)
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}", file=sys.stderr)
        return 1
    if not isinstance(coupons, list):
        print("券数据必须是 JSON 数组", file=sys.stderr)
        return 1

    now = _parse_time(args.now) if args.now else None
    try:
        results = check_coupons(coupons, now=now, channel=args.channel)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    marks = {"usable": "✅", "claimable": "🎁", "unusable": "❌"}
    for r in results:
        print(f"{marks.get(r['status'], '?')} {r.get('name', r.get('id', '未命名券'))} — {r['reason']}")
    usable_n = sum(1 for r in results if r["usable"])
    claimable_n = sum(1 for r in results if r.get("status") == "claimable")
    print(f"\n共 {len(results)} 张券，当前可用 {usable_n} 张，可领取 {claimable_n} 张。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
