# 第二阶段指标字典

本字典由可执行 `metrics.metric_catalog` 生成。后续 Python、报告和 Tableau 必须读取 `metrics.daily_fulfillment`、`metrics.overall_fulfillment` 或 `metrics.checkpoint_snapshot`，不得另写平行口径。

## `avg_accept_to_fetch_seconds`

- 业务问题：接单后多久取餐。
- 粒度：订单dt/整体。
- 公式：sum(fetch-accept) / 有效订单数。
- 分子：有效时长秒数合计。
- 分母：两端时间存在且非负订单数。
- 单位：秒。
- 过滤条件：排除时间顺序异常。
- 0/NULL处理：缺失则NULL且不入分母。
- 质量标记与适用边界：已接受订单。

## `avg_attempt_count`

- 业务问题：每单平均经历多少次分配尝试。
- 粒度：订单dt/整体。
- 公式：sum(attempt_count) / order_count。
- 分子：尝试次数合计。
- 分母：订单数。
- 单位：次/订单。
- 过滤条件：订单指标层有效记录。
- 0/NULL处理：分母0则NULL。
- 质量标记与适用边界：含最终接受尝试。

## `avg_delivery_distance_coordinate_units`

- 业务问题：取送点直线距离如何变化。
- 粒度：订单dt/整体。
- 公式：匿名坐标欧氏距离均值。
- 分子：距离合计。
- 分母：坐标可计算订单数。
- 单位：匿名坐标单位。
- 过滤条件：订单指标层有效记录。
- 0/NULL处理：缺失则排除。
- 质量标记与适用边界：未知比例尺，禁止解释为公里或路网距离。

## `avg_end_to_end_seconds`

- 业务问题：下单到送达全链路多久。
- 粒度：订单dt/整体。
- 公式：sum(arrive-platform_order) / 完成订单数。
- 分子：有效时长秒数合计。
- 分母：下单和送达存在且非负订单数。
- 单位：秒。
- 过滤条件：仅完成且顺序合法订单。
- 0/NULL处理：未完成为NULL并排除分母。
- 质量标记与适用边界：预订单可跨自然日，仍归属dt。

## `avg_fetch_to_arrive_seconds`

- 业务问题：取餐后多久送达。
- 粒度：订单dt/整体。
- 公式：sum(arrive-fetch) / 完成订单数。
- 分子：有效时长秒数合计。
- 分母：取餐和送达存在且非负订单数。
- 单位：秒。
- 过滤条件：仅完成且顺序合法订单。
- 0/NULL处理：未完成为NULL并排除分母。
- 质量标记与适用边界：不静默纳入1条未完成记录。

## `avg_final_dispatch_to_accept_seconds`

- 业务问题：最终一次派单到接单耗时多久。
- 粒度：订单dt/整体。
- 公式：sum(accept-final_dispatch) / 有效订单数。
- 分子：有效时长秒数合计。
- 分母：两端时间存在且非负订单数。
- 单位：秒。
- 过滤条件：排除时间顺序异常。
- 0/NULL处理：最终派单为0则NULL且不入分母。
- 质量标记与适用边界：标准派单至接单段；不含此前拒绝等待。

## `avg_first_dispatch_to_accept_seconds`

- 业务问题：从首次派单到最终接单耗时多久。
- 粒度：订单dt/整体。
- 公式：sum(accept-first_dispatch) / 有效订单数。
- 分子：有效时长秒数合计。
- 分母：两端时间存在且非负订单数。
- 单位：秒。
- 过滤条件：排除时间顺序异常。
- 0/NULL处理：缺失则NULL且不入分母。
- 质量标记与适用边界：包含拒绝与重派等待。

## `avg_order_to_push_seconds`

- 业务问题：下单后多久进入派单池。
- 粒度：订单dt/整体。
- 公式：sum(first_push-platform_order) / 有效订单数。
- 分子：有效时长秒数合计。
- 分母：两端时间存在且非负订单数。
- 单位：秒。
- 过滤条件：排除时间顺序异常。
- 0/NULL处理：事件不存在则NULL且不入分母。
- 质量标记与适用边界：平台下单属性取最终接受waybill。

## `avg_orders_per_wave`

- 业务问题：每波平均承载多少订单。
- 粒度：波次dt/整体。
- 公式：sum(member_count) / wave_count。
- 分子：波次成员数合计。
- 分母：有效波次数。
- 单位：订单/波。
- 过滤条件：成员解析与关联完整。
- 0/NULL处理：分母0则NULL。
- 质量标记与适用边界：成员数是订单负载代理。

## `avg_pickup_delay_seconds`

- 业务问题：取餐相对预计出餐晚多久。
- 粒度：订单dt/整体。
- 公式：sum(fetch-estimated_meal_ready) / 有效订单数。
- 分子：取餐延迟秒数合计。
- 分母：预计出餐非0且取餐存在订单数。
- 单位：秒。
- 过滤条件：预计出餐时间非0。
- 0/NULL处理：负值保留表示提前；缺失排除。
- 质量标记与适用边界：不是商户因果责任判断。

## `avg_push_to_first_dispatch_seconds`

- 业务问题：入池后多久首次派单。
- 粒度：订单dt/整体。
- 公式：sum(first_dispatch-first_push) / 有效订单数。
- 分子：有效时长秒数合计。
- 分母：两端时间存在且非负订单数。
- 单位：秒。
- 过滤条件：排除时间顺序异常。
- 0/NULL处理：0派单时间转NULL且不入分母。
- 质量标记与适用边界：首次派单取该订单最早非0 dispatch_time。

## `avg_redispatch_count`

- 业务问题：每单平均重派多少次。
- 粒度：订单dt/整体。
- 公式：sum(attempt_count-1) / order_count。
- 分子：重派次数合计。
- 分母：订单数。
- 单位：次/订单。
- 过滤条件：订单指标层有效记录。
- 0/NULL处理：分母0则NULL。
- 质量标记与适用边界：首次尝试不算重派。

## `avg_wave_duration_seconds`

- 业务问题：骑手波次平均持续多久。
- 粒度：波次dt/整体。
- 公式：sum(official_end-reconstructed_start) / 有效波次数。
- 分子：合法波次时长秒数合计。
- 分母：成员完整且时长非负波次数。
- 单位：秒。
- 过滤条件：成员解析与关联完整。
- 0/NULL处理：非法或缺失时长排除。
- 质量标记与适用边界：开始时间必须使用成员最早有效grab_time重构。

## `buffer_8m_late_rate`

- 业务问题：加入8分钟缓冲后仍超时多少。
- 粒度：订单dt/整体。
- 公式：arrive>estimate_arrived+480完成订单数 / 完成订单数。
- 分子：缓冲超时完成订单数。
- 分母：完成订单数。
- 单位：比例。
- 过滤条件：仅完成订单。
- 0/NULL处理：未完成排除；分母0则NULL。
- 质量标记与适用边界：8分钟为显式业务缓冲，不替代严格口径。

## `checkpoint_candidate_courier_count`

- 业务问题：选定checkpoint候选骑手有多少。
- 粒度：dt+dispatch_time。
- 公式：count(checkpoint rider members)。
- 分子：候选骑手成员数。
- 分母：不适用。
- 单位：骑手。
- 过滤条件：骑手侧快照存在。
- 0/NULL处理：缺侧则NULL并标记。
- 质量标记与适用边界：仅24个checkpoint；不公开成员。

## `checkpoint_candidate_couriers_per_pending_order`

- 业务问题：checkpoint候选骑手订单比是多少。
- 粒度：dt+dispatch_time。
- 公式：candidate_courier_count / pending_order_count。
- 分子：候选骑手数。
- 分母：待派订单数。
- 单位：骑手/订单。
- 过滤条件：两侧快照均存在。
- 0/NULL处理：待派订单为0则NULL。
- 质量标记与适用边界：按中文字段顺序定义的候选骑手订单比；仅描述24个选定快照。

## `checkpoint_pending_order_count`

- 业务问题：选定checkpoint待派订单有多少。
- 粒度：dt+dispatch_time。
- 公式：count(checkpoint order members)。
- 分子：待派订单成员数。
- 分母：不适用。
- 单位：订单。
- 过滤条件：订单侧快照存在。
- 0/NULL处理：缺侧则NULL并标记。
- 质量标记与适用边界：仅24个checkpoint，不能代表全天日志。

## `checkpoint_pending_orders_per_candidate_courier`

- 业务问题：checkpoint每名候选骑手对应多少待派订单。
- 粒度：dt+dispatch_time。
- 公式：pending_order_count / candidate_courier_count。
- 分子：待派订单数。
- 分母：候选骑手数。
- 单位：订单/骑手。
- 过滤条件：两侧快照均存在。
- 0/NULL处理：候选骑手为0则NULL。
- 质量标记与适用边界：courier_waybills定义仍不确定；比值仅描述选定快照。

## `completion_rate`

- 业务问题：已接受订单中有多少完成送达。
- 粒度：订单dt/整体。
- 公式：completed_order_count / order_count。
- 分子：arrive_time非0订单数。
- 分母：已接受订单数。
- 单位：比例。
- 过滤条件：订单事实。
- 0/NULL处理：arrive_time=0记未完成；分母0则NULL。
- 质量标记与适用边界：1条未完成保留在分母，不进入完成时长。

## `first_attempt_success_rate`

- 业务问题：订单能否在第一次尝试即被接受。
- 粒度：订单dt/整体。
- 公式：attempt_count=1订单数 / 订单数。
- 分子：仅1次尝试订单数。
- 分母：订单数。
- 单位：比例。
- 过滤条件：订单指标层有效记录。
- 0/NULL处理：分母0则NULL。
- 质量标记与适用边界：第一次尝试由dispatch_time排序确定。

## `first_dispatch_success_rate`

- 业务问题：首次派单是否成功。
- 粒度：订单dt/整体。
- 公式：首次waybill被接受订单数 / 订单数。
- 分子：仅1次尝试订单数。
- 分母：订单数。
- 单位：比例。
- 过滤条件：订单指标层有效记录。
- 0/NULL处理：分母0则NULL。
- 质量标记与适用边界：当前数据以waybill表示派单尝试，因此与first_attempt_success_rate恒等。

## `order_count`

- 业务问题：运营日履约需求规模是多少。
- 粒度：dt/整体。
- 公式：count(order)。
- 分子：订单行数。
- 分母：不适用。
- 单位：订单。
- 过滤条件：订单事实；时间顺序质量标记为真时不入指标层。
- 0/NULL处理：无行则为0。
- 质量标记与适用边界：dt为运营归属日；不代表自然下单日。

## `p90_wave_load_orders`

- 业务问题：高负载波次的订单数水平是多少。
- 粒度：波次dt。
- 公式：member_count的P90。
- 分子：不适用。
- 分母：有效波次分布。
- 单位：订单/波。
- 过滤条件：成员解析与关联完整。
- 0/NULL处理：无波次则NULL。
- 质量标记与适用边界：描述性负载，不是异常阈值。

## `strict_late_rate`

- 业务问题：实际送达是否超过承诺时刻。
- 粒度：订单dt/整体。
- 公式：arrive>estimate_arrived完成订单数 / 完成订单数。
- 分子：严格超时完成订单数。
- 分母：完成订单数。
- 单位：比例。
- 过滤条件：仅完成订单。
- 0/NULL处理：未完成排除；分母0则NULL。
- 质量标记与适用边界：不对承诺时刻加缓冲。

## `waybill_acceptance_rate`

- 业务问题：派出的waybill有多少被接受。
- 粒度：waybill dt/整体。
- 公式：accepted_waybill_count / waybill_attempt_count。
- 分子：接受waybill数。
- 分母：全部waybill尝试数。
- 单位：比例。
- 过滤条件：排除时间顺序异常尝试。
- 0/NULL处理：分母0则NULL。
- 质量标记与适用边界：尝试粒度，不等于订单完成率。
