# 第二阶段 A：数据层设计与质量合同验收

状态：**通过**。本报告只含 schema 约定、输入规模和测试结果，不含原始标识符、坐标或明细记录。

## 固定合同

- 官方数据提交：`1f9b4288cee5a78d1e5da007fc306bbaa662fc6d`。
- 运营归属日：`dt`；Unix 秒统一解释为 `Asia/Shanghai`。
- 事件时间为 0 表示事件不存在；预订单允许跨自然日。
- 质量问题一律保留原值并增加标记，不静默删除、填补或修正。
- 本地数据库：`data/local/phase2.duckdb`，位于 Git 忽略目录。

## 原始层守恒

| 本地表 | 行数 |
|---|---:|
| `raw.waybill` | 654,343 |
| `raw.courier_wave` | 206,748 |
| `raw.dispatch_rider` | 62,044 |
| `raw.dispatch_waybill` | 15,921 |

## 自动检查

共 6 项合同检查通过：`raw.waybill row count`、`raw.courier_wave row count`、`raw.dispatch_rider row count`、`raw.dispatch_waybill row count`、`fixed source commit`、`Asia/Shanghai timezone`。

## 后续边界

A 仅建立 raw 层、执行顺序、血缘和质量合同。订单/运单、波次/checkpoint、指标层分别在 B、C、D 建立；异动识别与归因、Tableau、经营报告、预测模型和 Agent 不在第二阶段范围内。
