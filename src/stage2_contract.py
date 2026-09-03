"""Stage-2 data-contract constants shared by build validation scripts."""

CORE_OBJECTS = (
    "dwd_waybill",
    "dwd_order_wave_bridge",
    "dwd_courier_wave",
    "ads_operations_overview",
    "ads_hourly_supply_demand",
    "dws_courier_efficiency",
    "ads_anomaly_diagnosis",
)

EXPECTED_ROWS = {
    "dwd_waybill": 654_343,
    "dwd_order_wave_bridge": 568_545,
    "dwd_courier_wave": 206_748,
    "dws_courier_efficiency": 4_955,
    "ads_anomaly_diagnosis": 11,
}
