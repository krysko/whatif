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

----------------------------------------------------------------------
依赖优先级的计算（同层多节点时，priority 小的先执行）
----------------------------------------------------------------------

7. 延迟严重程度 (delay_severity) — Shipment，priority=1
   - 公式：1 if delay_days > 10 else 0
   - 含义：延迟超过 10 天记为严重（1），否则为 0。先于 delay_notification_flag 计算。

8. 延迟通知标志 (delay_notification_flag) — Shipment
   - 公式：1 if delay_severity == 1 else 0（即由 delay_severity 决定）
   - 含义：一旦 delay_severity 为 1，则 delay_notification_flag 为 1；依赖 delay_severity，计算上必须在 calc_delay_severity 之后执行（拓扑依赖，非仅优先级）。

9. 发运风险分 (risk_score) — Shipment，priority=3
   - 公式：delay_severity + delay_notification_flag
   - 含义：汇总两个标志，需在二者都算完后执行，故 priority=3。

10. 产品风险等级 (risk_level) — Product，priority=1
    - 公式：1 if delay_impact_days > 5 else 0
    - 含义：对客户延误超过 5 天记为高风险（1）。与 delay_penalty 同层依赖 delay_impact_days，
      靠 priority 先算 risk_level 再算 delay_penalty。

11. 延迟惩罚 (delay_penalty) — Product，priority=2（见上，与 risk_level 同层）

12. 总成本 (total_cost) — Product，priority=3
    - 公式：delay_penalty + risk_level * 1000
    - 含义：惩罚金额加上风险加价（高风险固定加 1000）。必须在 delay_penalty 与 risk_level 都算完后执行。
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)
_root = Path(__file__).parent.parent
src_path = _root / "src"
sys.path.insert(0, str(src_path))
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from examples.demo_utils import MockNeo4jManager, print_header
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
    Neo4jGraphManager,
    format_scenario_result,
)

# ============================================================================
# Configuration
# ============================================================================

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789"

# ============================================================================
# Display
# ============================================================================

def print_scenario_result(result: ScenarioRunResult, label: str, max_diff: int = 15) -> None:
    """格式化输出 ScenarioRunResult（输入覆盖、受影响节点、关键输出、属性变化、执行状态）。"""
    format_scenario_result(result, label=label, max_diff_items=max_diff, log_fn=logger.info)


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
    delay_severity_in = InputSpec("property", "Shipment", "delay_severity")
    delay_notification_in = InputSpec("property", "Shipment", "delay_notification_flag")
    risk_level_in = InputSpec("property", "Product", "risk_level")
    delay_penalty_in = InputSpec("property", "Product", "delay_penalty")

    # OutputSpecs
    effective_delivery_out = OutputSpec("property", "Shipment", "effective_delivery_days")
    delay_days_out = OutputSpec("property", "Shipment", "delay_days")
    delay_severity_out = OutputSpec("property", "Shipment", "delay_severity")
    delay_notification_out = OutputSpec("property", "Shipment", "delay_notification_flag")
    risk_score_out = OutputSpec("property", "Shipment", "risk_score")
    actual_start_out = OutputSpec("property", "ProductionPlan", "actual_start_days")
    production_ready_out = OutputSpec("property", "Product", "production_ready_days")
    delay_impact_out = OutputSpec("property", "Product", "delay_impact_days")
    risk_level_out = OutputSpec("property", "Product", "risk_level")
    delay_penalty_out = OutputSpec("property", "Product", "delay_penalty")
    total_cost_out = OutputSpec("property", "Product", "total_cost")

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
    # 6. 延迟惩罚 = 仅对延误部分：延误天数 × 单价 × 数量 × 费率（示例 0.01）；priority=2 与 risk_level 同层
    calc_delay_penalty = ComputationNode(
        id="calc_delay_penalty",
        name="delay_penalty",
        level=ComputationLevel.PROPERTY,
        inputs=(delay_impact_in, unit_price_in, quantity_in),
        outputs=(delay_penalty_out,),
        code="max(0, delay_impact_days) * unit_price * quantity * 0.01",
        engine=ComputationEngine.PYTHON,
        priority=2,
    )
    
    # 7. 延迟通知标志：依赖 delay_severity，severity 为 1 则 notification 为 1（显式先后依赖）
    calc_delay_notification = ComputationNode(
        id="calc_delay_notification",
        name="delay_notification_flag",
        level=ComputationLevel.PROPERTY,
        inputs=(delay_severity_in,),
        outputs=(delay_notification_out,),
        code="1 if delay_severity == 1 else 0",
        engine=ComputationEngine.PYTHON,
        priority=0,
    )
    
    # 8. 延迟严重程度（>10 天为 1）；先于 delay_notification 计算
    calc_delay_severity = ComputationNode(
        id="calc_delay_severity",
        name="delay_severity",
        level=ComputationLevel.PROPERTY,
        inputs=(delay_days_in,),
        outputs=(delay_severity_out,),
        code="1 if delay_days > 10 else 0",
        engine=ComputationEngine.PYTHON,
        priority=1,
    )
    
    # 9. 发运风险分 = severity + notification；priority=3 必须在 7、8 之后
    calc_risk_score = ComputationNode(
        id="calc_risk_score",
        name="risk_score",
        level=ComputationLevel.PROPERTY,
        inputs=(delay_severity_in, delay_notification_in),
        outputs=(risk_score_out,),
        code="delay_severity + delay_notification_flag",
        engine=ComputationEngine.PYTHON,
        priority=3,
    )
    # 10. 产品风险等级（delay_impact_days>5 为 1）；与 delay_penalty 同层，priority=1
    calc_risk_level = ComputationNode(
        id="calc_risk_level",
        name="risk_level",
        level=ComputationLevel.PROPERTY,
        inputs=(delay_impact_in,),
        outputs=(risk_level_out,),
        code="1 if delay_impact_days > 5 else 0",
        engine=ComputationEngine.PYTHON,
        priority=1,
    )
    # 11. 总成本 = delay_penalty + risk_level*1000；priority=3 必须在 delay_penalty、risk_level 之后
    calc_total_cost = ComputationNode(
        id="calc_total_cost",
        name="total_cost",
        level=ComputationLevel.PROPERTY,
        inputs=(delay_penalty_in, risk_level_in),
        outputs=(total_cost_out,),
        code="delay_penalty + risk_level * 1000",
        engine=ComputationEngine.PYTHON,
        priority=3,
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
        # Shipment：delay_severity 依赖 delay_days；delay_notification 依赖 delay_severity（显式先后）
        ComputationRelationship("r_delay_to_severity", "shipment_001", "calc_delay_severity",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=delay_days_in),
        ComputationRelationship("r_severity_to_ship", "calc_delay_severity", "shipment_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=delay_severity_out),
        ComputationRelationship("r_severity_to_notif", "shipment_001", "calc_delay_notification",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=delay_severity_in),
        ComputationRelationship("r_notif_to_ship", "calc_delay_notification", "shipment_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=delay_notification_out),
        ComputationRelationship("r_severity_to_risk", "shipment_001", "calc_risk_score",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=delay_severity_in),
        ComputationRelationship("r_notif_to_risk", "shipment_001", "calc_risk_score",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=delay_notification_in),
        ComputationRelationship("r_risk_to_ship", "calc_risk_score", "shipment_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=risk_score_out),
        # 依赖优先级的 Product 节点：risk_level(1), delay_penalty(2), total_cost(3)
        ComputationRelationship("r_impact_to_risk_level", "product_001", "calc_risk_level",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=delay_impact_in),
        ComputationRelationship("r_risk_level_to_prod", "calc_risk_level", "product_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=risk_level_out),
        ComputationRelationship("r_penalty_to_total", "product_001", "calc_total_cost",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=delay_penalty_in),
        ComputationRelationship("r_risk_level_to_total", "product_001", "calc_total_cost",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=risk_level_in),
        ComputationRelationship("r_total_to_prod", "calc_total_cost", "product_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=total_cost_out),
    ]

    graph = ComputationGraph(id="supply_chain_rich")
    for node in [calc_effective_delivery, calc_delay_days, calc_actual_start,
                 calc_production_ready, calc_delay_impact, calc_delay_penalty,
                 calc_delay_severity, calc_delay_notification, calc_risk_score,
                 calc_risk_level, calc_total_cost]:
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
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print_header("Supply Chain Rich Demo — 扩展运算与数据")
    logger.info("运算链: effective_delivery -> delay_days -> actual_start -> production_ready -> delay_impact -> delay_penalty")
    logger.info("       + 依赖优先级的节点: Shipment(delay_severity, delay_notification_flag, risk_score); Product(risk_level, total_cost)")
    logger.info("数据: Shipment(buffer_days), Product(promised_delivery_days, unit_price, quantity)")
    logger.info("")

    graph = build_rich_supply_chain_graph()
    node_data_map = build_rich_node_data()

    # Execute baseline
    print_header("Step 1: 基线执行")
    executor = ComputationGraphExecutor(graph, node_data_map)
    executor.execute(verbose=True)
    executor.print_node_data("基线结果")
    logger.info("")

    # 在 Neo4j 中可视化：同步数据节点 + 计算节点 + 关系，并输出可视化 Cypher
    neo4j_manager = Neo4jGraphManager(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    await neo4j_manager.connect()
    logger.info("Connected to Neo4j")
    logger.info("")

    print_header("Step 2: 同步数据节点、计算节点、计算关系到 Neo4j（一步完成）")
    await neo4j_manager.sync_graph_to_neo4j(graph, node_data_map=node_data_map)
    logger.info("Synced: %s data nodes, %s computation nodes, %s relationships",
                len(node_data_map), len(graph.computation_nodes), len(graph.computation_relationships))
    neo4j_manager.print_visualization_instructions(graph)
    logger.info("")

    simulator = WhatIfSimulator(executor, neo4j_manager=MockNeo4jManager())

    # Scenario 0: 交付延迟 1 天
    print_header("Step 0: What-If — 交付延迟 1 天")
    r0 = await simulator.run_scenario(
        [("shipment_001", "actual_delivery_days", 101)],
        title="交付延迟 1 天",
    )
    print_scenario_result(r0, "交付延迟 1 天")
    logger.info("")

    # Scenario 1: 交付延迟 10 天
    print_header("Step 2: What-If — 物料交付延迟 10 天")
    r1 = await simulator.run_scenario(
        [("shipment_001", "actual_delivery_days", 110)],
        title="交付延迟 10 天",
    )
    print_scenario_result(r1, "交付延迟 10 天")
    s1 = r1.scenario
    p1 = s1.get('product_001', {})
    logger.info("  关键结果: production_ready_days=%s, delay_impact_days=%s, delay_penalty=%s, risk_level=%s, total_cost=%s",
                p1.get('production_ready_days'), p1.get('delay_impact_days'), p1.get('delay_penalty'),
                p1.get('risk_level'), p1.get('total_cost'))
    logger.info("")

    # Scenario 2: 增加缓冲天数
    print_header("Step 3: What-If — 增加缓冲 3 天")
    r2 = await simulator.run_scenario(
        [("shipment_001", "buffer_days", 8)],
        title="增加缓冲 3 天",
    )
    print_scenario_result(r2, "增加缓冲")
    logger.info("")

    # Scenario 3: 承诺交付日提前
    print_header("Step 4: What-If — 承诺交付日提前至 105 天")
    r3 = await simulator.run_scenario(
        [("product_001", "promised_delivery_days", 105)],
        title="承诺日提前",
    )
    print_scenario_result(r3, "承诺日提前")
    p3 = r3.scenario.get('product_001', {})
    logger.info("  关键结果: delay_impact_days=%s, delay_penalty=%s, risk_level=%s, total_cost=%s",
                p3.get('delay_impact_days'), p3.get('delay_penalty'), p3.get('risk_level'), p3.get('total_cost'))
    logger.info("")

    # Scenario 4: 多属性同时变化
    print_header("Step 5: What-If — 交付延迟 + 生产周期缩短")
    r4 = await simulator.run_scenario(
        [
            ("shipment_001", "actual_delivery_days", 108),
            ("production_plan_001", "production_duration_days", 5),
        ],
        title="交付延迟 8 天 + 生产缩短 2 天",
    )
    print_scenario_result(r4, "多属性")
    logger.info("")

    await neo4j_manager.disconnect()
    print_header("Demo 完成")
    logger.info("Executor 状态已恢复为基线。计算图 + 数据节点已写入 Neo4j，可在 Browser 中执行上述 Cypher 查看。")


if __name__ == "__main__":
    asyncio.run(main())
