# 第二阶段总验收

状态：**通过**。第二阶段已形成可审计的 SQL 数据层、四类事实对象、统一指标层与安全聚合对账；未进入异动识别与归因、Tableau、经营报告、预测模型或 Agent。

## 交付与关键数字

- 运单尝试事实：654,343 行；订单履约事实：568,546 行；接受 568,546，拒绝 85,797。
- 跨 waybill 属性不一致订单 61；已接单未完成 1；已接受但派单时间为 0 的订单 1；均保留质量标记且未静默修正。
- 波次事实 206,748 行；成员 568,545；官方开始时间不一致 65,904；分析时长使用重构开始时间。
- checkpoint 24 个、覆盖 8 个 `dt`；待派订单成员 15,921、候选骑手成员 62,044；仅代表选定快照。
- 指标目录 25 项；日层、整体层与 checkpoint 层均从同一 `metrics` schema 取数。
- 自动合同 71 项、逻辑数据库双重建 SHA-256 `cb11c1fd2caa857e021f2e929f87224b42ee3aec63e64f2424aba68c3a257f7a`、6 份公开报告哈希均通过确定性比较。

## 已知限制

- `courier_waybills` 字段名与官方文字定义仍有歧义，保留不确定标记，不据此作个体结论。
- dispatch 仅 24 个 checkpoint，不能当作全天逐事件日志或用于第三阶段阈值识别。
- 配送距离是匿名坐标欧氏单位，不能换算为公里或路网距离。
- 所有结果是描述性事实与指标，不作因果归因；第三阶段才可另行定义 MAD 阈值、贡献分解与案例筛选。
- 本地 Codex snapshot ref 的历史对象含官方原始文件，但不属于 `main`、Phase 1 或 Phase 2 远端分支祖先；本任务不删除该本地 ref，且只允许显式推送 Phase 2 分支，禁止 `git push --all` 或 `--mirror`。清理本地 ref/对象需另行授权。

## 复现

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/download_data.py
.venv/bin/python scripts/run_phase2.py --through E
.venv/bin/python scripts/validate_phase2.py --step E
```

原始 CSV/ZIP 和本地 DuckDB 必须留在 Git 忽略目录；发布前另以 `git diff --cached`、`scripts/privacy_scan.py` 和远端 SHA 只读核验提交范围。各步骤提交 SHA 与最终 push 结果在任务交付记录中报告。
