# 第二阶段自动测试与确定性报告

状态：**通过**。`scripts/run_phase2.py --through E` 从固定原始输入连续完整重建两次，A–D 合同、E 跟踪范围合同、逻辑数据库指纹和公开报告哈希均一致后才写入本报告。

## 环境

- Python：`3.14.3`
- DuckDB：`1.5.5`
- 时区：`Asia/Shanghai`
- 官方数据提交：`1f9b4288cee5a78d1e5da007fc306bbaa662fc6d`

## 合同检查

- A–D：67 项；E：4 项；累计：71 项，全部通过。
- E 检查：`complete 20-table inventory`、`database and raw inputs ignored`、`no forbidden data artifacts tracked`、`complete ordered SQL inventory`。
- 隐私扫描器自测和最终公开候选文件扫描由同一入口在报告写入后执行；入口成功退出即表示通过。

## 两次完整重建指纹

- 逻辑数据库 SHA-256：`cb11c1fd2caa857e021f2e929f87224b42ee3aec63e64f2424aba68c3a257f7a`。
- 逻辑表共 20 张：`fact` 6 张、`meta` 1 张、`metrics` 4 张、`raw` 4 张、`stg` 5 张。
- 逻辑指纹覆盖每张表的列名/类型/可空性、行数、全列行哈希异或及保留重复次数的行哈希和，再对规范化清单计算 SHA-256。
- DuckDB 物理文件包含存储布局元数据，等价重建的字节哈希不承诺稳定，因此不把物理文件 SHA 当作数据确定性证据。

| 公开报告 | 两次一致的 SHA-256 |
|---|---|
| `PHASE2_STEP_A_ACCEPTANCE.md` | `616706aa1f36a5538c03faa907952bd59180db2b89bc705d777f242b0250be8d` |
| `PHASE2_STEP_B_ACCEPTANCE.md` | `deccc20faf606aebedd73d1216a585992b9c58eb0323480fb08fd508f4fda741` |
| `PHASE2_STEP_C_ACCEPTANCE.md` | `6ae953e49dc29dda88b2f328bcac412e68a7e81bc363ee6d17549eef551c5426` |
| `PHASE2_STEP_D_ACCEPTANCE.md` | `1b4dc536ae6b4e4301eb1bd4cd657209acd617e1f7355f298ff2b8c995d1cc66` |
| `METRIC_DICTIONARY.md` | `a88855d9afcff36a72a6c6114992ec6df466f6f0a46b19ea595bed7a3bf8a939` |
| `METRIC_RECONCILIATION.md` | `69a962d7a79bf90e94722875ef99e0c7894d474d09a22c6bbb7cf5b3e64de987` |

## 测试范围

已覆盖结构、主键/复合键唯一性、行数与成员守恒、接受/拒绝、关联覆盖、0 时间、事件顺序、持续时间非负、61 个属性冲突、1 个未完成记录、65,904 个波次开始偏差、24 个 checkpoint 对齐、指标分子分母恒等式、比率边界、隐私规则和 Git 跟踪范围。
