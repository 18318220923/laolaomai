# 捞捞麦 · AI 点单管家

> 致力于解决中国宝宝吃饭问题
> 说人话就能点单，不确认不下单。

![捞捞麦封面](捞捞麦_封面.png)

**在线演示：https://laolaomai-order-agent.app.workbuddy.host/?sharecode=6XQ3RHVWWK**

---

## 一句话介绍

听得懂人话的 AI 点单管家：你说「预算25块、想吃肉、别太撑」，它帮你查菜单、比优惠、算实付，确认前绝不下单。

## 解决什么问题

- **选择困难**：菜单上百个单品，翻完一遍十分钟过去了
- **优惠黑洞**：卡包里的券什么时候能用、哪家店能用，全靠自己试
- **健康焦虑**：想控制热量，但没人告诉你这顿到底多少大卡

根本症结：**大模型懂人话但拿不到实时数据，APP 有数据但不懂人话，两边是断的。** 捞捞麦用 MCP 协议把两边接上。

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 自然语言意图解析 | 从一句话里提取预算、口味、忌口、份量、门店、取餐方式 |
| 真实菜单检索 | 通过餐饮 MCP Server 拉取门店实时可售商品与价格 |
| 优惠券三态校验 | 可用 / 可领未领 / 不可用（含原因：未生效、已过期、渠道不匹配） |
| 真实算价验证 | 优惠金额只采用算价工具返回值，绝不自行推算 |
| 营养估算 | 命中官方营养数据时输出热量，缺失时如实标注"暂无数据" |
| 多渠道比价 | 官方实付价 vs 美团/抖音等外部券同台对比，外部价一律标注未验证 |
| 双主题输出 | 简洁版 / 可爱风（原创设计，不含第三方 IP 素材） |

## 快速开始

### 方式一：在 WorkBuddy 对话中使用

把 `skill/` 目录复制到你的用户级技能目录（Windows：`C:\Users\<你>\.workbuddy\skills\`），然后在对话里直接说：

```
帮我点麦当劳，预算25块，想吃带肉的，不要太撑，自提
```

### 方式二：命令行调试

```bash
# 主流程（未指定 --mcp_server 时为 mock 模式，仅验证链路）
python skill/scripts/main.py "预算25块，想吃带肉的，不要太撑" --pickup_type 自提

# 算价结果校验 + 节省金额计算
python skill/scripts/price_calculator.py '{"productOriginalPrice":2900,"productPrice":2090,"discount":810}'

# 优惠券可用性校验（有效期 / 星期 / 渠道）
python skill/scripts/coupon_filter.py '[{"id":"C1","name":"11.9元麦辣鸡腿堡","valid_from":"2026-10-26 10:30","valid_to":"2026-10-30 23:59"}]' --channel 到店

# 下单链路（默认 dry-run，不会真下单）
python skill/scripts/place_order.py --store "麦当劳华立学院店" --pickup_type 自提 \
    --items '[{"name":"龙焰鸡腿堡","qty":1,"price":15.9}]' --total 15.9 --confirm "确认下单"
```

### 方式三：在线体验（无需安装）

打开上面的在线链接，第三屏「评委亲自体验」可直接与真实大模型对话。

## 目录结构

```
laolaomai-repo/
├── skill/                          # WorkBuddy 技能本体（可打包分发）
│   ├── SKILL.md                    # 技能定义：触发词 / 参数 / 8 步工作流 / 安全约束
│   ├── README.md                   # 技能使用说明
│   ├── scripts/
│   │   ├── main.py                 # 主流程：意图解析 → MCP 调用 → 生成方案
│   │   ├── price_calculator.py     # 算价适配（分→元，双格式，数据完整性校验）
│   │   ├── coupon_filter.py        # 券三态校验
│   │   ├── deal_compare.py         # 外部渠道比价
│   │   ├── order_confirm.py        # 下单确认卡（default / cute 双主题）
│   │   └── place_order.py          # 下单链路：口令校验 + dry-run
│   ├── references/
│   │   ├── mcp_config_example.json # MCP Server 配置示例（不含真实密钥）
│   │   ├── prompt_template.md      # 系统提示词模板
│   │   ├── mcd_tool_map.md         # 麦当劳 MCP 实测工具地图（接入前必读）
│   │   └── cute_theme.md           # 可爱风主题指南
│   └── assets/
│       ├── order_card_template.md
│       └── order_card_template_cute.md
├── site/                           # 作品展示网站（含真实大模型对话演示）
│   ├── index.html
│   ├── cover.png
│   ├── data/menu.json              # 麦当劳官方接口真实菜单快照
│   └── mcp-order-agent.zip
├── 作品说明.md                      # 完整作品说明文档
├── 捞捞麦_封面.png                  # 封面图
└── mcp-order-agent.zip              # 技能安装包
```

## 安全设计（不是口号，是代码）

| 红线 | 落地方式 |
| --- | --- |
| 不替用户支付 | 代码中不存在任何支付接口调用 |
| 未确认不下单 | `place_order.py` 口令必须严格等于「确认下单」，否则视为取消 |
| 不编造价格 | 算价字段缺失时抛 `PriceDataError` 并提示"价格需以下单页为准" |
| 不自动领券 | `auto-bind-coupons` 会改变账户状态，必须先获用户同意 |
| 不外泄密钥 | 全部密钥走环境变量，配置示例文件中无真实密钥 |
| 营养非医嘱 | 输出一律标注"仅供参考，不构成医疗建议" |

## 开源扩展

- **模型层可替换**：`main.py` 支持通义千问 / Kimi / DeepSeek / Claude 等 OpenAI 兼容接口，密钥仅从环境变量读取，未配置时自动退回规则解析
- **餐饮 MCP Server 可替换**：`references/mcp_config_example.json` 提供配置骨架，替换 command / args / env 即可接入其他餐饮接口
- **提示词可替换**：`references/prompt_template.md` 是系统提示词模板，改它就能改 Agent 的性格

## 许可

MIT License
