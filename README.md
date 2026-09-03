# 美团外卖履约经营分析

> 骑手效率、供需峰值与运力配置诊断

GitHub：<https://github.com/mh1158174866-stack/meituan-fulfillment-operations-analysis>

## 项目状态

第二阶段已验收：在第一阶段官方数据、关联和参考 KPI 复核基础上，已建立 7 个轻量 DuckDB 核心对象，固定运单状态、时间、波次修正和经营指标口径。一键脚本已通过全量重建、结构/指标校验、两次语义指纹比较和隐私扫描。正式业务结论、看板、预测模型和策略模拟不在本阶段。

## 业务问题

- 分时、分区域订单需求与可用运力是否匹配？
- 接单率、配送时长、空闲时长、跨区配送和工作负载如何共同反映骑手效率？
- 哪些区域、时段和骑手群体存在履约风险？

## 数据来源与时间边界

- 官方数据：[Meituan-INFORMS-TSL Research Challenge](https://github.com/meituan/Meituan-INFORMS-TSL-Research-Challenge)
- 挑战说明：[INFORMS TSL Data-Driven Research Challenge](https://connect.informs.org/tsl/tslresources/datachallenge)
- 参考报告：[Concordia University 2025 MSc project](https://spectrum.library.concordia.ca/id/eprint/995758/)

数据集于 2024 年公开并用于 2024—2025 年挑战；业务记录主要来自 2022 年 10 月约一周。公开时间不等于业务发生时间，项目将以平台业务时间戳重建分析日期，并单独检查原始 `dt` 的一致性。

## 许可与公开边界

数据由美团按 CC BY-NC 4.0 提供，仅用于非商业研究；未经许可不得重新分发。此仓库不包含原始数据、原始标识符、坐标明细或可还原的行为序列。复现者需从官方仓库自行下载。

致谢：本研究由美团提供数据支持。

## 项目结构

```text
data/           # raw/interim/processed 均不入 Git，仅保留占位文件
docs/           # 验收清单、质量报告、口径和阶段记录
logs/           # 本地运行日志，不入 Git
notebooks/      # 探索性分析
outputs/        # 复核后的聚合图表与表格
references/     # 公开参考资料的下载说明或本地副本
scripts/        # 下载、验收、KPI 复核和隐私扫描入口
sql/            # ODS 只读映射、DWD 明细清洗、DWS/ADS 轻量聚合
src/            # 数据契约与可测试的 Python 逻辑
```

## 第一阶段验收门槛

- 官方文件全部可读取，并记录大小、哈希、编码、字段、行数和时间范围；
- 主键候选、重复、缺失、异常值及事件时间顺序有量化记录；
- 表关联基数与覆盖率明确；
- `dt` 与业务时间戳差异明确；
- 接单率、配送时长、空闲时长和骑手分组由本项目代码独立计算；
- 与参考报告差异能够用粒度、过滤、时间节点或阈值解释；
- Git 追踪内容通过数据许可和隐私检查。

## 第一阶段已验证结果

- 官方四张表共 939,056 条数据行；全运单表为 654,343 条运单、568,546 个唯一订单、4,955 名骑手。
- 运单 ID 与波次复合主键均无重复，四张表无空值、无完全重复行。
- 派单订单全部能关联全运单表；24 个派单检查点与候选骑手检查点双向 100% 对齐；568,545 个波次订单引用全部关联成功。
- `dt` 为 2022-10-17 至 2022-10-24；按 `platform_order_time` 转为 Asia/Shanghai 日期后，652,485 条一致，1,858 条不一致，其中 1,704 条为预订单。
- 官方提示的波次起点问题被实测确认：65,904 个波次的原始 `wave_start_time` 不等于波次内最早接单时间；波次结束时间则全部一致。
- 骑手等权平均接单率为 84.74%，骑手等权平均配送时长为 27.10 分钟，均复现参考报告量级。
- 08:00—12:00 的推算供需比在 2022-10-21、22、23 日分别为 1.03、1.01、1.07，方向上复现参考报告的高峰承压结论。

专区/多区域骑手 KPI 暂未作为验收通过项：参考报告没有公开收货区域的构造规则，而官方说明 `da_id` 还受订单类型等因素影响且区域可能重叠。项目不会为了匹配参考数字而自行补造口径。

## 第二阶段核心数据对象

| 对象 | 粒度 | 实际行数 |
|---|---|---:|
| `dwd_waybill` | 运单 | 654,343 |
| `dwd_order_wave_bridge` | 波次内订单引用 | 568,545 |
| `dwd_courier_wave` | `(dt, courier_id, wave_id)` | 206,748 |
| `ads_operations_overview` | Asia/Shanghai 平台下单日 | 13 |
| `ads_hourly_supply_demand` | Asia/Shanghai 平台下单小时 | 223 |
| `dws_courier_efficiency` | 骑手全期聚合 | 4,955 |
| `ads_anomaly_diagnosis` | 异常类型 | 11 |

运单明确分为 85,797 条拒绝、568,545 条完成和 1 条已接受未完成。波次起点使用波次内最早 `grab_time` 修正，65,904 个起点差异和原值均被保留以便审计。指标公式、分母、过滤条件和有效样本量见 `docs/数据字典与指标口径.md`。

## 复现方式

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
PYTHON_BIN=.venv/bin/python scripts/run_stage1.sh
```

脚本会从美团官方仓库下载数据到 Git 忽略目录，生成本地聚合审计 JSON，运行结构/KPI 验证与 Git 隐私扫描。完整口径与差异解释见 `docs/数据质量报告.md`。

第二阶段在本地重建 DuckDB，并自动执行两次确定性比较：

```bash
PYTHON_BIN=.venv/bin/python scripts/run_stage2.sh
```

`data/processed/meituan_fulfillment.duckdb` 包含明细标识符，只供本地分析且被 Git 强制忽略。确定性指纹只保存表结构、行数和语义哈希，不保存原始值。
