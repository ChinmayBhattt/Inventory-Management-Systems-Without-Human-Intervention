import math
from typing import Dict, Tuple


def calculate_safety_stock(
    service_level_z: float,
    sigma_demand: float,
    lead_time_days: int
) -> int:
    """
    Safety Stock (SS) = Z * sigma_demand * sqrt(lead_time)
    Protects against demand uncertainty during the supplier replenishment lead time.
    """
    if service_level_z <= 0 or sigma_demand <= 0 or lead_time_days <= 0:
        return 0
    ss = service_level_z * sigma_demand * math.sqrt(lead_time_days)
    return int(math.ceil(ss))


def calculate_reorder_point(
    avg_daily_demand: float,
    lead_time_days: int,
    safety_stock: int
) -> int:
    """
    Reorder Point (ROP) = (avg_daily_demand * lead_time) + safety_stock
    Threshold inventory level that triggers an automated replenishment order.
    """
    lead_demand = max(0.0, avg_daily_demand) * max(0, lead_time_days)
    rop = lead_demand + max(0, safety_stock)
    return int(math.ceil(rop))


def calculate_economic_order_quantity(
    annual_demand: float,
    fixed_order_cost: float,
    unit_cost: float,
    holding_cost_annual_pct: float
) -> int:
    """
    Economic Order Quantity (EOQ) = sqrt((2 * D * S) / H)
    Where:
      D = Annual Demand (units/year)
      S = Fixed Order Setup Cost ($/order)
      H = Annual Holding Cost ($/unit/year) = holding_cost_annual_pct * unit_cost
    """
    if annual_demand <= 0 or fixed_order_cost <= 0 or unit_cost <= 0 or holding_cost_annual_pct <= 0:
        return 1

    h = holding_cost_annual_pct * unit_cost
    if h <= 0:
        return 1

    eoq = math.sqrt((2.0 * annual_demand * fixed_order_cost) / h)
    return max(1, int(round(eoq)))


def evaluate_replenishment_trigger(
    on_hand: int,
    on_order: int,
    reserved: int,
    reorder_point: int,
    economic_order_quantity: int,
    moq: int = 1
) -> Tuple[bool, int, int]:
    """
    Evaluates whether replenishment is triggered:
    Effective Stock = on_hand + on_order - reserved
    Trigger Condition: Effective Stock <= ROP
    Recommended Order Qty = max(EOQ, ROP - Effective Stock), bounded by MOQ.
    Returns: (is_triggered, effective_stock, recommended_order_qty)
    """
    effective_stock = on_hand + on_order - reserved
    is_triggered = effective_stock <= reorder_point

    if not is_triggered:
        return False, effective_stock, 0

    deficit = reorder_point - effective_stock
    target_qty = max(economic_order_quantity, deficit)
    # Respect Minimum Order Quantity (MOQ)
    order_qty = max(target_qty, moq)
    return True, effective_stock, order_qty

