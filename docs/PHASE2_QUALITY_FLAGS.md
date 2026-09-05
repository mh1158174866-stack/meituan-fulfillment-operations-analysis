# 第二阶段质量标记与指标处理

本文件是 `reports/METRIC_DICTIONARY.md` 中“质量标记与适用边界”的统一补充合同。质量问题保留原始记录和标记；仅与该问题直接相关的时长分母可排除，订单量、尝试量及质量计数不得静默减少。

| 标记 | 所在对象 | 触发规则 | 指标处理 |
|---|---|---|---|
| `has_missing_dispatch_time` | waybill、order | 原始 `dispatch_time=0` | 记录保留；入池至派单、首次/最终派单至接单为 NULL，不进入对应时长分母；固定输入共 1 条已接受订单 |
| `is_incomplete_accepted` | waybill、order | 已接受且 `arrive_time=0` | 记录保留在订单量与完成率分母；完成率分子不含；取餐至送达、全链路、超时率分母不含；固定输入共 1 条 |
| `has_event_order_error` | waybill、order | 任一相邻有效事件倒序 | 量级与状态指标保留并另计质量排除数；链路时长排除；固定输入为 0 |
| `has_cross_waybill_attribute_inconsistency` | order | 同一订单的 `dt`、预订单或下单时间版本不唯一 | 记录保留；正式订单属性取唯一最终已接受 waybill；固定输入共 61 条 |
| `has_dt_inconsistency` / `has_prebook_inconsistency` / `has_order_time_inconsistency` | waybill、order | 分项版本不唯一 | 同上，用于追溯 61 条总标记的来源 |
| `has_start_time_mismatch` | wave | 官方开始时间不等于成员最早有效接单时间 | 波次保留；持续时间只用重构开始时间；固定输入共 65,904 波 |
| `has_end_time_mismatch` | wave | 官方结束时间不等于成员最大送达时间 | 波次保留并标记；结束不一致时持续时间不得默认为可信；固定输入为 0 |
| `has_member_parse_error` | wave | `order_ids` 成员不能解析 | 波次保留；成员负载与时长指标排除并另行报告；固定输入为 0 |
| `has_member_coverage_error` | wave | 成员不能按 `dt + order_id + courier_id` 关联订单事实 | 波次保留；成员负载与时长指标排除；固定输入为 0 |
| `missing_order_snapshot` / `missing_rider_snapshot` | checkpoint | 两张 checkpoint 表任一侧缺失 | checkpoint 保留；依赖缺失侧的数量/比值为 NULL；固定输入为 0 |
| `has_onhand_parse_error` | checkpoint/rider | `courier_waybills` 成员不能解析 | checkpoint 保留；在手集合仅作质量统计，不参与供需比；固定输入为 0 |
| `courier_waybills_definition_uncertain` | checkpoint/rider | 物理字段名与官方文字口径不能唯一判定 order/waybill | 始终为真；不据此计算个体任务负载或作归因，只保留集合守恒检查 |
| `is_selected_checkpoint_not_event_log` | checkpoint | 数据只含 24 个选定时点 | 始终为真；只能描述这 24 个快照，不得解释为全天派单过程 |

所有 0 时间在事实表继续保留原始整数列，同时把对应分析时间戳转为 NULL。负的取餐延迟允许保留，因为它表示早于预计出餐时间取餐；其他链路持续时间必须非负。
