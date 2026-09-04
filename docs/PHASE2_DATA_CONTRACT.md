# 第二阶段数据合同

## 对象与粒度

| 对象 | 固定粒度与候选键 | 主要来源 | 时间字段 | 必须保留的质量标记 | 禁止公开字段 |
|---|---|---|---|---|---|
| `fact_waybill_attempt` | 一行一个 `waybill_id` | `raw.waybill` | 入池、派单、接单、取餐、送达 | 尝试顺序、接受/拒绝、0 时间与顺序异常 | 订单/运单/骑手/商户/商圈标识、坐标、逐单时间线 |
| `fact_order_fulfillment` | 一行一个 `order_id` | `fact_waybill_attempt` | 首次入池、首次派单、最终接单及完整链路 | 跨 waybill 属性不一致、未完成、时间异常 | 同上 |
| `fact_courier_wave` | `dt + courier_id + wave_id` | `raw.courier_wave`、已接受运单 | 官方/重构波次开始、结束 | 开始时间不一致、成员关联、`courier_waybills` 口径不确定 | 骑手/波次/订单标识、成员列表、逐骑手序列 |
| `fact_dispatch_checkpoint` | `dt + dispatch_time` | 两张 dispatch 表 | checkpoint 时间 | 两侧集合对齐、有限覆盖边界 | 候选骑手、待派订单、在手任务明细与坐标 |

## 继承口径

- `dt` 是运营归属日，不以自然下单日替代。
- Unix 秒以 `Asia/Shanghai` 解释；时长统一用秒存储，展示时再换算分钟。
- 0 时间转为分析用 `NULL`，同时保留原始值或明确的缺失标记；0 表示事件未发生。
- 预订单允许提前下单和跨自然日，不作为脏数据删除。
- 同一订单跨 waybill 的属性冲突按最终已接受 waybill 取订单属性，并保留冲突标记。
- 不完整、关联失败、时间倒置或定义不确定均不得静默删除或填补。

## 自动合同

`scripts/validate_phase2.py` 以失败即停止方式逐步扩展。A 固定输入规模、官方提交和时区；B–D 分别增加事实唯一性/守恒、波次与 checkpoint 对齐、指标恒等式；E 统一运行结构、隐私、Git 跟踪范围和两次确定性重建检查。
