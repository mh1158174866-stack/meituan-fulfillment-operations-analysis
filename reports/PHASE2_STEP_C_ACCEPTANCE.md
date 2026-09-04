# 第二阶段 C：骑手波次与派单 checkpoint 事实验收

状态：**通过**。以下只公开聚合规模、覆盖和质量标记，不公开骑手、订单、波次或在手任务明细。

## 波次事实

- `fact_courier_wave`：206,748 行，`dt + courier_id + wave_id` 复合键唯一。
- 波次成员 568,545 个，解析与订单关联覆盖均为 100%。
- 官方开始时间与成员最早有效接单时间不一致 65,904 波；分析用开始时间全部采用重构值。
- 官方结束时间与成员最大送达时间全部一致；基于重构开始时间的负持续时间为 0。
- 每波成员数范围：1–59。

## checkpoint 事实

- 24 个 `dt + dispatch_time` checkpoint，覆盖 8 个运营归属日；订单侧与骑手侧全部对齐。
- 每 checkpoint 待派订单 591–733，候选骑手 2,482–2,680。
- 待派订单总成员 15,921，候选骑手总成员 62,044；候选集合的复合键均唯一。
- `courier_waybills` 拆分成员可同时匹配 waybill/order 标识域，物理字段名与文字定义不能消除歧义；事实层统一保留 `courier_waybills_definition_uncertain=true`。
- checkpoint 仅为 24 个选定时点快照，`is_selected_checkpoint_not_event_log=true`；不得外推为全天逐事件派单日志。

## 自动检查

C 新增 19 项合同检查，全部通过；覆盖波次复合键、成员守恒/关联、开始/结束时间、持续时间、checkpoint 对齐、成员计数和集合键唯一性。
