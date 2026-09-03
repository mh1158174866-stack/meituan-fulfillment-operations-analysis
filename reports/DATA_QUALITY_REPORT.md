# 数据质量报告：结构、粒度与关联

本报告由 `scripts/audit_data.py` 对四张官方表全量只读计算生成，只包含聚合统计。官方文档行数仅作为外部对照；下列“实际”数值均由本项目脚本重算。

## 1. 文件结构与候选键

| 表 | 实际行数 | 官方说明行数 | 差异 | 全行重复 | 候选键重复 | 结论 |
|---|---:|---:|---:|---:|---:|---|
| `all_waybill_info_meituan_0322.csv` | 654,343 | 654,343 | +0 | 0 | 0 | 通过 |
| `courier_wave_info_meituan.csv` | 206,748 | 206,748 | +0 | 0 | 0 | 通过 |
| `dispatch_rider_meituan.csv` | 62,044 | 62,044 | +0 | 0 | 0 | 通过 |
| `dispatch_waybill_meituan.csv` | 15,921 | 15,921 | +0 | 0 | 0 | 通过 |

说明：三张 CSV 含无业务含义的导出索引列，审计视图统一改名为 `source_row_index`；它不参与业务候选键。

## 2. 缺失与 0 时间编码

| 表 | NULL 单元格数 | 含 NULL 的字段数 |
|---|---:|---:|
| `all_waybill_info_meituan_0322.csv` | 0 | 0 |
| `courier_wave_info_meituan.csv` | 0 | 0 |
| `dispatch_rider_meituan.csv` | 0 | 0 |
| `dispatch_waybill_meituan.csv` | 0 | 0 |

官方说明规定未发生的时间用 0 而非 NULL 编码。waybill 表的全量计数如下：

| 时间字段 | 等于 0 的行数 | 占 waybill 行数 |
|---|---:|---:|
| `estimate_arrived_time` | 0 | 0.000000% |
| `dispatch_time` | 1 | 0.000153% |
| `grab_time` | 85,797 | 13.111931% |
| `fetch_time` | 85,797 | 13.111931% |
| `arrive_time` | 85,798 | 13.112083% |
| `estimate_meal_prepare_time` | 9,907 | 1.514038% |
| `order_push_time` | 0 | 0.000000% |
| `platform_order_time` | 0 | 0.000000% |

## 3. 接受/拒绝与订单/运单粒度

- 运单尝试共 654,343 行：接受 568,546 行，拒绝 85,797 行，其他或缺失标记 0 行。
- 去重订单 568,546 个；去重运单 654,343 个。
- 有多个运单的订单 57,770 个，验证了订单与运单不是同一粒度。

## 4. 表间关联覆盖率

| 关系 | 分母 | 匹配数 | 覆盖率 |
|---|---:|---:|---:|
| dispatch 订单 → waybill 订单 | 15,921 | 15,921 | 100.000000% |
| 全量订单 → dispatch 订单 | 568,546 | 15,921 | 2.800301% |
| dispatch 候选骑手 → waybill 骑手 | 4,085 | 4,085 | 100.000000% |
| 波次订单集合 → waybill 订单 | 568,545 | 568,545 | 100.000000% |

波次订单集合共拆分出 568,545 个成员，无法解析为整数的成员为 0 个。

## 5. 派单 checkpoint

- `dispatch_rider` 有 24 个去重 `(dt, dispatch_time)` checkpoint。
- `dispatch_waybill` 有 24 个去重 `(dt, dispatch_time)` checkpoint。
- 两表共有 checkpoint 为 24 个。
- 这些表是 checkpoint 输入切片；不能用其行数替代全量订单、运单或骑手规模。

## 6. `courier_waybills` 物理含义核对

- 共拆分出 125,715 个在手集合成员、49,455 个去重标识；无法解析为整数的成员为 0 个。
- 与 `waybill_id` 匹配 49,455 个（100.000000%）。
- 与 `order_id` 匹配 49,455 个（100.000000%）。
- 因官方文字称其为在手订单集合、物理字段名却为 `courier_waybills`，本阶段只记录两种覆盖率，不据此构建正式事实表。

## 7. 阶段 C 结论

- 四表均可被 DuckDB 严格、全量读取，实际行数与官方说明对照一致。
- 候选业务键、重复、NULL、0 时间、接受/拒绝、粒度和关联覆盖率已完成聚合验收。
- 时间解释、预订单日期提前、事件顺序、已接单未完成记录、wave_start_time 索引问题和 checkpoint 业务语义留到阶段 D。
