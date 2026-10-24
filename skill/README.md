# mcp-order-agent 使用说明

> AI 点单管家：用自然语言说需求，自动解析预算/口味/热量约束，调用 MCP 工具查菜单、算价格、生成方案，确认后才下单。
> 版本：2026-10-24 | 适用：WorkBuddy

---

## 一、快速开始（对话中使用，推荐）

技能安装后无需配置，直接用自然语言触发：

```
帮我点麦当劳，预算25块，想吃带肉的，不要太撑，自提
```

**触发关键词**：点单、点餐、吃什么、帮我点麦当劳、帮我点瑞幸、预算点餐、优惠点餐、AI点单管家、MCP点单、菜单推荐、比价点餐

**交互流程**：
1. 你说需求（可含预算/口味/忌口/份量/取餐方式）
2. Agent 输出 2-4 个方案（含原价、实付、节省金额、热量、推荐理由）
3. 你回复「方案 N」选定
4. Agent 输出下单确认卡
5. 你回复「确认下单」→ 创建订单；**其他回复一律取消**

**全程不自动支付、不自动下单。**

---

## 二、本地脚本调试

所有脚本在 `scripts/` 目录，Python 3.10+，无第三方依赖。

### 1. 主流程 main.py

```bash
# mock 模式（无 MCP Server 时演示链路，数据非真实）
python scripts/main.py "预算25块，想吃带肉的，不要太撑" --pickup_type 自提

# 参数
python scripts/main.py "帮我点麦当劳" \
    --budget 25 \              # 预算上限
    --store_id 1400583 \       # 门店编码
    --pickup_type 自提 \        # 堂食/自提/配送
    --mcp_server mcd \         # MCP Server 标识（真实数据）
    --no-llm                   # 禁用大模型解析，强制规则解析
```

**启用大模型意图解析**（可选，规则解析为兜底）：

```bash
# 设置环境变量后自动启用（OpenAI 兼容接口）
export MCP_ORDER_LLM_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export MCP_ORDER_LLM_API_KEY="你的密钥"
export MCP_ORDER_LLM_MODEL="qwen-plus"
```

### 2. 算价校验 price_calculator.py

```bash
# 简化格式
python scripts/price_calculator.py '{"original_price":30.0,"discounted_price":25.0,"valid":true}'

# 真实 mcd-mcp 格式（单位分，自动转元）
python scripts/price_calculator.py '{"originalPrice":2900,"price":2090,"discount":810}'
```

数据不完整时退出码 2，并提示「价格需以下单页为准」。

### 3. 券可用性校验 coupon_filter.py

```bash
python scripts/coupon_filter.py '[{"id":"C1","name":"11.9元麦辣鸡腿堡",
  "valid_from":"2026-10-26 10:30","valid_to":"2026-10-30 23:59",
  "weekdays":[1,2,3,4,5],"channels":["到店专用"]}]' \
  --channel 到店 --now "2026-10-24 14:00"
```

输出三态：✅ 可用 / 🎁 可领取 / ❌ 不可用（含原因）。

### 4. 确认卡 order_confirm.py

```bash
python scripts/order_confirm.py --store "麦当劳科技园店" --pickup_type 自提 \
    --items '[{"name":"麦香鸡腿堡","qty":1,"price":18.0}]' \
    --total 18.0 --theme cute    # default / cute 两套主题
```

### 5. 下单链路 place_order.py

```bash
# 第一步：生成确认卡（不下单）
python scripts/place_order.py --store "麦当劳科技园店" \
    --items '[{"name":"麦香鸡腿堡","qty":1,"price":18.0}]' --total 18.0

# 第二步：确认（默认仍 dry-run）
python scripts/place_order.py ... --confirm "确认下单"

# 真实下单（需 MCP Server，口令必须严格等于「确认下单」）
python scripts/place_order.py ... --confirm "确认下单" --execute --mcp_server mcd
```

### 6. 外部渠道比价 deal_compare.py

```bash
python scripts/deal_compare.py \
    --mcp '{"originalPrice":2900,"price":2090,"discount":810}' \
    --external '[{"platform":"美团","title":"单人餐团购券","price":19.9,"items":"麦香鸡+中薯+中可"}]'
```

外部平台（美团/抖音等）价格只能由用户提供，一律标注「未验证，以平台下单页为准」。

---

## 三、接入真实 MCP Server

1. 参照 `references/mcp_config_example.json`，把配置写入 `~/.workbuddy/mcp.json`
2. API 密钥填 `env` 字段，**不要提交到代码仓库**
3. 打开 WorkBuddy 连接器管理页面，对新 Server 点「信任」启用
4. 接入前必读 `references/mcd_tool_map.md`（beType/orderType 矩阵、算价单位是"分"、特调 key 规则等实测坑）

---

## 四、安全红线（不可绕过）

| 红线 | 说明 |
|---|---|
| 不支付 | 绝不替用户完成支付 |
| 不自动下单 | 口令必须严格等于「确认下单」 |
| 不编造价格 | 算价工具没返回就如实说"以下单页为准" |
| 不编造外部价 | 美团/抖音等外部价格只能来自用户提供 |
| 不擅自领券 | auto-bind-coupons 需用户同意 |
| 营养仅供参考 | 不构成医疗建议 |

---

## 五、常见问题

**Q：推荐了用不了的券？**
A：券会先过 `coupon_filter.py`（日期/星期/渠道三重过滤），不可用的会注明生效时间，如「10/26 起可用」。

**Q：新品没有热量数据？**
A：官方营养库未收录时显示「热量数据缺失」，不会用近似值编造。

**Q：想换模型/换餐饮品牌？**
A：模型层改环境变量即可（qwen/kimi/deepseek/claude 均可）；餐饮品牌换一个 MCP Server 标识，`mcp_config_example.json` 有示例。

**Q：想要更有活力的风格？**
A：说「用活力红金风」，确认卡和文案自动切换红金活力风主题（`cute_theme.md`，原创设计无 IP 风险）。
