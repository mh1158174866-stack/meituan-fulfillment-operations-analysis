# 数据字典

本字典依据美团官方字段说明和本地 DuckDB 全量类型推断整理；不展示任何数据行、原始 ID 或坐标值。

## `all_waybill_info_meituan_0322.csv`

- 粒度：一次运单进入派单系统后的分配尝试；同一订单可对应多个运单。
- 候选键：`waybill_id`。
- 实际规模：654,343 行，24 列。

| 字段 | DuckDB 类型 | 业务含义 | 原始格式 | 使用边界 |
|---|---|---|---|---|
| `source_row_index` | `BIGINT` | 源文件导出索引 | 整数 | 仅用于检测源文件行索引完整性，无业务含义，不作为公开主键 |
| `dt` | `BIGINT` | 运营归属日 | YYYYMMDD 整数 | 源文件日期字段；时间语义在阶段 D 单独审计 |
| `order_id` | `BIGINT` | 匿名订单标识 | 整数 | 同一订单可能经历多个 waybill_id |
| `waybill_id` | `BIGINT` | 匿名运单标识 | 整数 | 订单被拒后重回派单系统会创建新运单 |
| `courier_id` | `BIGINT` | 匿名骑手标识 | 整数 | waybill 表中表示当次分配骑手；派单骑手表中表示候选骑手 |
| `da_id` | `BIGINT` | 匿名商圈标识 | 整数 | 业务区域标识 |
| `is_courier_grabbed` | `BIGINT` | 骑手是否接受运单 | 0/1 | 1 为接受，0 为拒绝 |
| `is_weekend` | `BIGINT` | 订单日期是否周末 | 0/1 | 源文件标记 |
| `estimate_arrived_time` | `BIGINT` | 承诺送达时间 | Unix 秒 | 承诺向顾客送达的时间 |
| `is_prebook` | `BIGINT` | 是否预订单 | 0/1 | 1 为预订单 |
| `poi_id` | `BIGINT` | 匿名商户标识 | 整数 | 匿名化取餐商户标识 |
| `sender_lng` | `BIGINT` | 取餐点经度 | 偏移后整数 | 高风险位置字段，仅本地使用 |
| `sender_lat` | `BIGINT` | 取餐点纬度 | 偏移后整数 | 高风险位置字段，仅本地使用 |
| `recipient_lng` | `BIGINT` | 送达点经度 | 偏移后整数 | 高风险位置字段，仅本地使用 |
| `recipient_lat` | `BIGINT` | 送达点纬度 | 偏移后整数 | 高风险位置字段，仅本地使用 |
| `grab_lng` | `BIGINT` | 分配时骑手经度 | 偏移后整数 | 高风险位置字段，仅本地使用 |
| `grab_lat` | `BIGINT` | 分配时骑手纬度 | 偏移后整数 | 高风险位置字段，仅本地使用 |
| `dispatch_time` | `BIGINT` | 派单时间或 checkpoint | Unix 秒 | 具体语义依表而异，阶段 D 单独审计 |
| `grab_time` | `BIGINT` | 运单接受时间 | Unix 秒 | 未发生时以 0 编码 |
| `fetch_time` | `BIGINT` | 取餐时间 | Unix 秒 | 未发生时以 0 编码 |
| `arrive_time` | `BIGINT` | 送达时间 | Unix 秒 | 未发生时以 0 编码 |
| `estimate_meal_prepare_time` | `BIGINT` | 预计出餐时间 | Unix 秒 | 预计餐品准备完成时间 |
| `order_push_time` | `BIGINT` | 订单进入派单系统时间 | Unix 秒 | 订单进入分配队列的时间 |
| `platform_order_time` | `BIGINT` | 平台下单时间 | Unix 秒 | 订单创建时间 |

## `courier_wave_info_meituan.csv`

- 粒度：一个骑手在一个运营日内的一次波次。
- 候选键：`dt + courier_id + wave_id`。
- 实际规模：206,748 行，6 列。

| 字段 | DuckDB 类型 | 业务含义 | 原始格式 | 使用边界 |
|---|---|---|---|---|
| `dt` | `BIGINT` | 运营归属日 | YYYYMMDD 整数 | 源文件日期字段；时间语义在阶段 D 单独审计 |
| `courier_id` | `BIGINT` | 匿名骑手标识 | 整数 | waybill 表中表示当次分配骑手；派单骑手表中表示候选骑手 |
| `wave_id` | `BIGINT` | 匿名波次标识 | 整数 | 需与 dt、courier_id 组成候选复合键 |
| `wave_start_time` | `BIGINT` | 波次开始时间 | Unix 秒 | 官方定义为波次首单接受时间；阶段 D 记录索引问题 |
| `wave_end_time` | `BIGINT` | 波次结束时间 | Unix 秒 | 官方定义为波次末单送达时间 |
| `order_ids` | `VARCHAR` | 波次订单集合 | 字符串列表 | 只在本地拆分用于聚合覆盖率，不公开明细 |

## `dispatch_rider_meituan.csv`

- 粒度：一个派单 checkpoint 下的一名候选骑手。
- 候选键：`dt + dispatch_time + courier_id`。
- 实际规模：62,044 行，7 列。

| 字段 | DuckDB 类型 | 业务含义 | 原始格式 | 使用边界 |
|---|---|---|---|---|
| `source_row_index` | `BIGINT` | 源文件导出索引 | 整数 | 仅用于检测源文件行索引完整性，无业务含义，不作为公开主键 |
| `dt` | `BIGINT` | 运营归属日 | YYYYMMDD 整数 | 源文件日期字段；时间语义在阶段 D 单独审计 |
| `rider_lat` | `BIGINT` | checkpoint 骑手纬度 | 偏移后整数 | 高风险位置字段，仅本地使用 |
| `rider_lng` | `BIGINT` | checkpoint 骑手经度 | 偏移后整数 | 高风险位置字段，仅本地使用 |
| `dispatch_time` | `BIGINT` | 派单时间或 checkpoint | Unix 秒 | 具体语义依表而异，阶段 D 单独审计 |
| `courier_waybills` | `VARCHAR` | checkpoint 骑手在手任务集合 | 字符串列表 | 物理字段名与官方描述存在口径差异，阶段 C 比较关联覆盖率 |
| `courier_id` | `BIGINT` | 匿名骑手标识 | 整数 | waybill 表中表示当次分配骑手；派单骑手表中表示候选骑手 |

## `dispatch_waybill_meituan.csv`

- 粒度：一个派单 checkpoint 下的一张待分配订单。
- 候选键：`dt + dispatch_time + order_id`。
- 实际规模：15,921 行，4 列。

| 字段 | DuckDB 类型 | 业务含义 | 原始格式 | 使用边界 |
|---|---|---|---|---|
| `source_row_index` | `BIGINT` | 源文件导出索引 | 整数 | 仅用于检测源文件行索引完整性，无业务含义，不作为公开主键 |
| `dt` | `BIGINT` | 运营归属日 | YYYYMMDD 整数 | 源文件日期字段；时间语义在阶段 D 单独审计 |
| `dispatch_time` | `BIGINT` | 派单时间或 checkpoint | Unix 秒 | 具体语义依表而异，阶段 D 单独审计 |
| `order_id` | `BIGINT` | 匿名订单标识 | 整数 | 同一订单可能经历多个 waybill_id |

## 关系与口径提示

- `order_id` 是订单粒度；`waybill_id` 是分配尝试粒度，一张订单可对应多张运单。
- 波次表不能只用 `wave_id` 作为全局键，应使用 `dt + courier_id + wave_id` 候选复合键。
- 两张 dispatch 表描述派单 checkpoint 的输入切片，不应直接当作全量订单或骑手事实表。
- `courier_waybills` 的物理字段名与官方“在手订单集合”描述并不完全一致；只在覆盖率审计中比较两种可能关联，不在本阶段强行定口径。
- 所有 Unix 时间均在阶段 D 按 Asia/Shanghai 解释并检查事件顺序。
