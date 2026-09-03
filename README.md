# 美团外卖履约经营分析

本仓库用于构建“全链路监控与异动归因”项目。当前只完成第一阶段：数据与环境验收；不在本阶段输出经营结论、异动归因、看板、预测模型或 Agent。

## 第一阶段范围

1. 从美团官方仓库下载四张数据表到 Git 忽略目录；
2. 记录文件大小、SHA-256 和下载来源，不重新分发原始数据；
3. 用 DuckDB/Python 只读核验结构、粒度、关联、时间和业务语义；
4. 仅公开字段说明、文件规模、聚合统计、质量结论和官方下载指引；
5. 用隐私扫描和确定性复跑验证公开产物。

## 官方数据入口

- 美团官方仓库：<https://github.com/meituan/Meituan-INFORMS-TSL-Research-Challenge>
- 官方许可文本：<https://github.com/meituan/Meituan-INFORMS-TSL-Research-Challenge/blob/main/License.txt>
- CC BY-NC 4.0：<https://creativecommons.org/licenses/by-nc/4.0/>

四张业务表为：

- `all_waybill_info_meituan_0322.csv`（官方仓库提供 ZIP）；
- `courier_wave_info_meituan.csv`；
- `dispatch_rider_meituan.csv`；
- `dispatch_waybill_meituan.csv`。

原始 CSV、ZIP、官方 PDF、ID、坐标及可还原行为序列均不得提交到本仓库。

## 环境

要求 Python 3.11–3.14。依赖精确锁定在 `requirements.txt`。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

后续步骤会提供下载、审计、隐私扫描和一键验收命令。数据目录规则见 [data/README.md](data/README.md)，许可与隐私边界见 [docs/LICENSE_AND_DATA_USE.md](docs/LICENSE_AND_DATA_USE.md) 和 [docs/PRIVACY.md](docs/PRIVACY.md)。

## 下载官方数据

下载脚本固定到官方仓库提交 `1f9b4288cee5a78d1e5da007fc306bbaa662fc6d`，避免上游 `main` 后续变化破坏复现。

```bash
.venv/bin/python scripts/download_data.py
```

脚本会生成只含来源、文件规模和哈希的 `reports/DOWNLOAD_MANIFEST.md`。需要重新下载时使用 `--force`。

## 结构、粒度与关联验收

```bash
.venv/bin/python scripts/audit_data.py
```

该命令全量读取四表并生成：

- `reports/DATA_DICTIONARY.md`：字段、类型、粒度、候选键和使用边界；
- `reports/DATA_QUALITY_REPORT.md`：行数、重复、缺失、0 时间、接受/拒绝、订单/运单粒度、复合键和关联覆盖率。

## 时间与业务语义验收

```bash
.venv/bin/python scripts/audit_time_semantics.py
```

该命令按 Asia/Shanghai 解释 Unix 秒，生成 `reports/TIME_SEMANTICS_REPORT.md`，量化运营归属日、预订单日期提前、事件顺序、已接单未完成记录、`wave_start_time` 索引问题和 dispatch checkpoint 语义。本阶段不据此构建正式事实表。

## 数据署名

本项目使用美团提供的数据。若公开发表基于该数据集的研究，应按官方要求注明：

> 本研究由美团提供数据支持。

英文：`This research was supported by data provided by Meituan.`
