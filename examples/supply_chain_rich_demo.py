"""
Supply Chain Rich Demo — 扩展的供应链延迟与惩罚计算

在 supply_chain_delay_demo 基础上增强：
- 运算逻辑：有效交付日、延迟天数、实际开工、完工日、延迟影响天数、延迟惩罚金额
- 数据：Shipment 增加 buffer_days；Product 增加 promised_delivery_days、unit_price、quantity、delay_impact_days、delay_penalty

流程：内存 node_data_map -> 执行计算 -> 多组 run_scenario 对比（交付延迟、缓冲调整、承诺日变化）
不依赖 Neo4j，可直接运行。

----------------------------------------------------------------------
计算逻辑含义（业务语义）
----------------------------------------------------------------------

1. 有效交付日 (effective_delivery_days)
   - 公式：actual_delivery_days + buffer_days
   - 含义：物料实际到达日加上缓冲天数，得到「可用于排产的日期」。缓冲可表示质检、入库等所需天数，
     下游生产计划按有效交付日之后的延迟来推算实际开工日。

2. 延迟天数 (delay_days)
   - 公式：effective_delivery_days - planned_delivery_days
   - 含义：相对原计划的延迟天数（有效交付日晚于计划交付日的天数）。为正表示晚到，会顺延后续开工。

3. 实际开工日 (actual_start_days)
   - 公式：planned_start_days + delay_days
   - 含义：原计划开工日加上物料延迟天数，得到受交付影响后的实际可开工日（以「第几天」表示，如项目第 105 天）。

4. 生产完工日 (production_ready_days)
   - 公式：actual_start_days + production_duration_days
   - 含义：从实际开工日算起，经过生产周期后的完工日，即产品可交付的日期（仍以「第几天」表示）。

5. 延迟影响天数 (delay_impact_days)
   - 公式：production_ready_days - promised_delivery_days
   - 含义：完工日与承诺交付日之差。正值表示晚于承诺（延误），负值表示早于承诺。

6. 延迟惩罚金额 (delay_penalty)
   - 公式：max(0, delay_impact_days) * unit_price * quantity * 0.01
   - 含义：仅对延误（delay_impact_days > 0）计罚；按「延误天数 × 单价 × 数量 × 费率」估算惩罚成本，
     其中 0.01 为示例费率（如每日万分之百或 1% 的惩罚系数）。
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, List, Tuple

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from domain.models import (
    ComputationEngine,
    ComputationGraph,
    ComputationLevel,
    ComputationNode,
    ComputationRelationType,
    ComputationRelationship,
    InputSpec,
    OutputSpec,
)
from domain.services import (
    ComputationGraphExecutor,
    ScenarioRunResult,
    WhatIfSimulator,
)


class _MockNeo4jManager:
    """本 demo 不连接 Neo4j，仅占位。"""
    pass


# ============================================================================
# Display
# ============================================================================

def print_header(title: str, width: int = 60) -> None:
    print("=" * width)
    print(title)
    print("=" * width)
    print()


def print_diff_summary(result: ScenarioRunResult, label: str) -> None:
    print(f"  [{label}] 共 {len(result.diff)} 项变化:")
    for d in result.diff[:10]:
        print(f"    {d['node_id']}.{d['property_name']}: {d['baseline_value']} -> {d['scenario_value']}")
    if len(result.diff) > 10:
        print(f"    ... 其余 {len(result.diff) - 10} 项")


# ============================================================================
# Graph: 扩展的供应链计算图
# ============================================================================

def build_rich_supply_chain_graph() -> ComputationGraph:
    """
    构建扩展供应链计算图。各计算节点含义见本文件顶部「计算逻辑含义」说明。
    """
    # InputSpecs
    planned_delivery = InputSpec("property", "Shipment", "planned_delivery_days")
    actual_delivery = InputSpec("property", "Shipment", "actual_delivery_days")
    buffer_days_in = InputSpec("property", "Shipment", "buffer_days")
    effective_delivery = InputSpec("property", "Shipment", "effective_delivery_days")
    delay_days_in = InputSpec("property", "Shipment", "delay_days")
    planned_start = InputSpec("property", "ProductionPlan", "planned_start_days")
    actual_start_in = InputSpec("property", "ProductionPlan", "actual_start_days")
    production_duration = InputSpec("property", "ProductionPlan", "production_duration_days")
    production_ready_in = InputSpec("property", "Product", "production_ready_days")
    promised_delivery = InputSpec("property", "Product", "promised_delivery_days")
    unit_price_in = InputSpec("property", "Product", "unit_price")
    quantity_in = InputSpec("property", "Product", "quantity")
    delay_impact_in = InputSpec("property", "Product", "delay_impact_days")

    # OutputSpecs
    effective_delivery_out = OutputSpec("property", "Shipment", "effective_delivery_days")
    delay_days_out = OutputSpec("property", "Shipment", "delay_days")
    actual_start_out = OutputSpec("property", "ProductionPlan", "actual_start_days")
    production_ready_out = OutputSpec("property", "Product", "production_ready_days")
    delay_impact_out = OutputSpec("property", "Product", "delay_impact_days")
    delay_penalty_out = OutputSpec("property", "Product", "delay_penalty")

    # Computation nodes（含义见文件顶部「计算逻辑含义」）
    # 1. 有效交付日 = 实际到货日 + 缓冲天数（下游按此日推算延迟）
    calc_effective_delivery = ComputationNode(
        id="calc_effective_delivery_days",
        name="effective_delivery_days",
        level=ComputationLevel.PROPERTY,
        inputs=(actual_delivery, buffer_days_in),
        outputs=(effective_delivery_out,),
        code="actual_delivery_days + buffer_days",
        engine=ComputationEngine.PYTHON,
        priority=0,
    )
    # 2. 延迟天数 = 有效交付日 - 计划交付日（>0 表示晚到）
    calc_delay_days = ComputationNode(
        id="calc_delay_days",
        name="delay_days",
        level=ComputationLevel.PROPERTY,
        inputs=(effective_delivery, planned_delivery),
        outputs=(delay_days_out,),
        code="effective_delivery_days - planned_delivery_days",
        engine=ComputationEngine.PYTHON,
        priority=0,
    )
    # 3. 实际开工日 = 计划开工日 + 延迟天数（受物料延迟顺延）
    calc_actual_start = ComputationNode(
        id="calc_actual_start_days",
        name="actual_start_days",
        level=ComputationLevel.PROPERTY,
        inputs=(planned_start, delay_days_in),
        outputs=(actual_start_out,),
        code="planned_start_days + delay_days",
        engine=ComputationEngine.PYTHON,
        priority=0,
    )
    # 4. 生产完工日 = 实际开工日 + 生产周期（产品可交付日期）
    calc_production_ready = ComputationNode(
        id="calc_production_ready_days",
        name="production_ready_days",
        level=ComputationLevel.PROPERTY,
        inputs=(actual_start_in, production_duration),
        outputs=(production_ready_out,),
        code="actual_start_days + production_duration_days",
        engine=ComputationEngine.PYTHON,
        priority=0,
    )
    # 5. 延迟影响天数 = 完工日 - 承诺交付日（>0 表示对客户延误）
    calc_delay_impact = ComputationNode(
        id="calc_delay_impact_days",
        name="delay_impact_days",
        level=ComputationLevel.PROPERTY,
        inputs=(production_ready_in, promised_delivery),
        outputs=(delay_impact_out,),
        code="production_ready_days - promised_delivery_days",
        engine=ComputationEngine.PYTHON,
        priority=0,
    )
    # 6. 延迟惩罚 = 仅对延误部分：延误天数 × 单价 × 数量 × 费率（示例 0.01）
    calc_delay_penalty = ComputationNode(
        id="calc_delay_penalty",
        name="delay_penalty",
        level=ComputationLevel.PROPERTY,
        inputs=(delay_impact_in, unit_price_in, quantity_in),
        outputs=(delay_penalty_out,),
        code="max(0, delay_impact_days) * unit_price * quantity * 0.01",
        engine=ComputationEngine.PYTHON,
        priority=1,
    )

    # Relationships
    rels: List[ComputationRelationship] = [
        ComputationRelationship("r_actual_to_eff", "shipment_001", "calc_effective_delivery_days",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=actual_delivery),
        ComputationRelationship("r_buf_to_eff", "shipment_001", "calc_effective_delivery_days",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=buffer_days_in),
        ComputationRelationship("r_eff_to_ship", "calc_effective_delivery_days", "shipment_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=effective_delivery_out),
        ComputationRelationship("r_eff_to_delay", "shipment_001", "calc_delay_days",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=effective_delivery),
        ComputationRelationship("r_plan_to_delay", "shipment_001", "calc_delay_days",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=planned_delivery),
        ComputationRelationship("r_delay_to_ship", "calc_delay_days", "shipment_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=delay_days_out),
        ComputationRelationship("r_plan_start_to_actual", "production_plan_001", "calc_actual_start_days",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=planned_start),
        ComputationRelationship("r_delay_to_actual", "shipment_001", "calc_actual_start_days",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=delay_days_in),
        ComputationRelationship("r_actual_to_plan", "calc_actual_start_days", "production_plan_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=actual_start_out),
        ComputationRelationship("r_actual_to_ready", "production_plan_001", "calc_production_ready_days",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=actual_start_in),
        ComputationRelationship("r_dur_to_ready", "production_plan_001", "calc_production_ready_days",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=production_duration),
        ComputationRelationship("r_ready_to_prod", "calc_production_ready_days", "product_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=production_ready_out),
        ComputationRelationship("r_ready_to_impact", "product_001", "calc_delay_impact_days",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=production_ready_in),
        ComputationRelationship("r_prom_to_impact", "product_001", "calc_delay_impact_days",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=promised_delivery),
        ComputationRelationship("r_impact_to_prod", "calc_delay_impact_days", "product_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=delay_impact_out),
        ComputationRelationship("r_impact_to_penalty", "product_001", "calc_delay_penalty",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=delay_impact_in),
        ComputationRelationship("r_price_to_penalty", "product_001", "calc_delay_penalty",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=unit_price_in),
        ComputationRelationship("r_qty_to_penalty", "product_001", "calc_delay_penalty",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=quantity_in),
        ComputationRelationship("r_penalty_to_prod", "calc_delay_penalty", "product_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=delay_penalty_out),
    ]

    graph = ComputationGraph(id="supply_chain_rich")
    for node in [calc_effective_delivery, calc_delay_days, calc_actual_start,
                 calc_production_ready, calc_delay_impact, calc_delay_penalty]:
        graph = graph.add_computation_node(node)
    for r in rels:
        graph = graph.add_computation_relationship(r)
    return graph


def build_rich_node_data() -> Dict[str, Dict]:
    """
    初始数据：Shipment、ProductionPlan、Product 的输入属性。

    - Shipment: planned_delivery_days 计划交付日（第几天），actual_delivery_days 实际到货日，
      buffer_days 缓冲天数（如质检/入库）。
    - ProductionPlan: planned_start_days 计划开工日，production_duration_days 生产周期天数。
    - Product: promised_delivery_days 向客户承诺的交付日，unit_price 单价，quantity 数量（用于惩罚计算）。
    """
    return {
        "shipment_001": {
            "shipment_id": "SHIP-001",
            "planned_delivery_days": 100,
            "actual_delivery_days": 100,
            "buffer_days": 5,
        },
        "production_plan_001": {
            "plan_id": "PLAN-001",
            "planned_start_days": 100,
            "production_duration_days": 7,
        },
        "product_001": {
            "product_id": "PROD-001",
            "promised_delivery_days": 107,
            "unit_price": 100.0,
            "quantity": 1000,
        },
    }


# ============================================================================
# Main
# ============================================================================

async def main() -> None:
    print_header("Supply Chain Rich Demo — 扩展运算与数据")
    print("运算链: effective_delivery -> delay_days -> actual_start -> production_ready -> delay_impact -> delay_penalty")
    print("数据: Shipment(buffer_days), Product(promised_delivery_days, unit_price, quantity)")
    print()

    graph = build_rich_supply_chain_graph()
    node_data_map = build_rich_node_data()

    # Execute baseline
    print_header("Step 1: 基线执行")
    executor = ComputationGraphExecutor(graph, node_data_map)
    executor.execute(verbose=True)
    executor.print_node_data("基线结果")
    print()

    simulator = WhatIfSimulator(executor, neo4j_manager=_MockNeo4jManager())

    # Scenario 1: 交付延迟 10 天
    print_header("Step 2: What-If — 物料交付延迟 10 天")
    r1 = await simulator.run_scenario(
        [("shipment_001", "actual_delivery_days", 110)],
        title="交付延迟 10 天",
    )
    print_diff_summary(r1, "交付延迟 10 天")
    s1 = r1.scenario
    print(f"  关键结果: production_ready_days={s1.get('product_001', {}).get('production_ready_days')}, "
          f"delay_impact_days={s1.get('product_001', {}).get('delay_impact_days')}, "
          f"delay_penalty={s1.get('product_001', {}).get('delay_penalty')}")
    print()

    # Scenario 2: 增加缓冲天数
    print_header("Step 3: What-If — 增加缓冲 3 天")
    r2 = await simulator.run_scenario(
        [("shipment_001", "buffer_days", 8)],
        title="增加缓冲 3 天",
    )
    print_diff_summary(r2, "增加缓冲")
    print()

    # Scenario 3: 承诺交付日提前
    print_header("Step 4: What-If — 承诺交付日提前至 105 天")
    r3 = await simulator.run_scenario(
        [("product_001", "promised_delivery_days", 105)],
        title="承诺日提前",
    )
    print_diff_summary(r3, "承诺日提前")
    print(f"  关键结果: delay_impact_days={r3.scenario.get('product_001', {}).get('delay_impact_days')}, "
          f"delay_penalty={r3.scenario.get('product_001', {}).get('delay_penalty')}")
    print()

    # Scenario 4: 多属性同时变化
    print_header("Step 5: What-If — 交付延迟 + 生产周期缩短")
    r4 = await simulator.run_scenario(
        [
            ("shipment_001", "actual_delivery_days", 108),
            ("production_plan_001", "production_duration_days", 5),
        ],
        title="交付延迟 8 天 + 生产缩短 2 天",
    )
    print_diff_summary(r4, "多属性")
    print()

    print_header("Demo 完成")
    print("Executor 状态已恢复为基线，可继续执行或写回 Neo4j。")


if __name__ == "__main__":
    asyncio.run(main())
