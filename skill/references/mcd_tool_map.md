# 麦当劳 MCP 工具地图（实测整理）

基于 2026-10-24 真实调用整理，供本技能接入与调试参考。

## beType / orderType 组合矩阵

| 场景 | beType | orderType | beCode |
|---|---|---|---|
| 到店自取 | 1 | 1 | 不传 |
| 麦乐送（外送） | 2 | 2 | 必传（来自 delivery-query-stores） |
| 得来速（车道取餐） | 5 | 1 | 必传（来自 query-nearby-stores） |
| 企业团餐 | 6 | 2 | 必传 + gmServiceCode |

## 工具速查

### query-nearby-stores
- 入参：`searchType`（1=收藏门店，2=按位置，需 city+keyword）、`beType`（1 到店 / 5 得来速）
- 返回：`storeCode`（后续所有工具必带）、`beCode`（仅 beType=5）、`reservationTimeOptions`（reservation=true 时预约时段，不得省略）
- 注意：预约时段影响可点性，today=true 标星号

### query-meals
- 入参：`storeCode`、`orderType`、`beType`（+beCode 按矩阵）
- 返回：`categories[]`（分类+餐品 code）+ `meals{}`（code→详情：name/image/currentPrice/originalPrice/discountType）
- `discountType` 值：null / 早餐卡优惠 / 促销优惠 / 麦金卡优惠 / 随单购麦金卡优惠
- `canWithOrder=true` 且 `withOrder` 存在时，优惠价必须加购随单购卡才生效，否则按原价
- 企业团餐参考搭配：20 元以下小食；20-30 汉堡+小食或饮料；30-40 汉堡+薯条/小食+饮料；40-50 汉堡+薯条+小食+饮料；50+ 丰富组合不重复小食

### query-my-coupons
- 返回用户卡包全部券，**不做门店/渠道/时段校验**
- 因此推荐前必须用 `scripts/coupon_filter.py` 按当前日期/星期/渠道过滤
- 若要"当前门店/当前订单可用的券"，改用 query-store-coupons

### query-store-coupons
- 入参同 query-meals 的矩阵规则；返回指定门店+订单类型下可用券
- 返回按 couponId 分组（同一券 ID 可有多券码），含 title/tradeDateTime/products
- 实测：无可用券时 data=[]，属正常，不要编造

### auto-bind-coupons（可领未领的券）
- 一键领取麦麦省当前所有可领券，**无需指定 couponId**
- 会改变用户账户状态 → 必须先提醒用户并获同意（"有 N 张券可领，要我帮你一键领取吗？"）
- 领取后重新走 query-my-coupons + coupon_filter 流程

### query-promotions（团餐满减/满折）
- 仅 beType=6（企业团餐）可用，需 delivery-query-stores 的 beCode
- promotionType：31-满额减，33-订单折扣；ruleCategory：30-满折，40-满减
- 工具只返回原始规则，搭配计算由 Agent 完成

### calculate-price
- 入参：`storeCode`、`orderType`、`beType`、`items[]`（productCode、quantity、可选 couponId/couponCode、modification）
- **返回金额单位是"分"**，展示时 ÷100
- 关键字段：`originalPrice`（原价）、`price`（实付）、`discount`（优惠）、`deliveryPrice`、`packingPrice`、`tablewarePrice`、`takeWayList`（可选取餐方式：eat-in 堂食 / take-in-store 外带）、`enjoyed`（已享优惠）、`enjoyable`（可享优惠，含门槛差额 balance）
- 特调（modification）key 规则：选中项用 `selectedKey`，未选中项若 `unselectedKey` 非空也必须用 `unselectedKey` 传入；含 unselectedKey 的组内所有项都要传

### list-nutrition-foods
- 返回约 160 项常见餐品的能量(kJ/kcal)/蛋白质/脂肪/碳水/钠/钙
- **新品可能缺失**（如实测的"龙焰鸡腿堡"），缺失时输出"热量数据缺失"，不得用近似值编造

### create-order（下单）
- 必须由 `scripts/place_order.py` 走口令校验后调用
- 涉地址/手机号等敏感信息时须二次确认
- 支付由麦当劳侧引导，本技能不经手

### 其他已验证工具
- `now-time-info`：服务器时间（预约/活动日历场景用）
- `query-store-coupons` / `query-promotions` / `query-meal-detail`（特调选项来源）

## 常见坑
1. 算价单位是分，展示忘除 100 会贵 100 倍
2. 券生效日期多为未来（如工作日活动券 10/26 起），不校验会推荐用不了的券
3. 新品无营养数据，属正常，需降级提示
4. beType=1 传了 beCode 会被拒绝；beType=5 不传 beCode 也会被拒
