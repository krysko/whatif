"""
认证与物料到货、工序完成时间计算图 Demo

业务逻辑（影响周期 = 物料可用时间）：
1. 先检查物料与采购认证供应商记录：若没有认证记录或未完成认证，影响周期要加上该物料的供应商认证周期（认证完成时间 = 认证开始时间 + 认证周期）；若已有认证则认证完成时间 = 认证开始时间。
2. 再检查是否已有采购订单：
   - 若无订单：物料可用时间 = 认证完成时间 + 采购周期。
   - 若有订单：计算订单数量 + 仓库库存。若不足需求则物料可用时间 = 认证完成时间 + 采购周期；若足够则物料可用时间 = 最早能满足需求的订单到货时间。
3. 子工序/工序完成时间：先序 startTime+工期，后序 max(物料可用时间, 前序完成时间)+工期，工序完成 = max(各子工序完成时间)。

计算图输出均为 ISO 日期时间字符串。流程：内存 node_data_map + 计算图 -> 执行 -> 同步到 Neo4j 可视化 -> 可选 What-If。
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)
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
    WhatIfSimulator,
    format_scenario_result,
)
from domain.services.neo4j_graph_manager import Neo4jGraphManager


class _MockNeo4jManager(Neo4jGraphManager):
    """本 demo 不连接 Neo4j，仅占位供 WhatIfSimulator 使用。"""
    pass


NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789"

# ============================================================================
# Display
# ============================================================================

def print_header(title: str, width: int = 60) -> None:
    logger.info("=" * width)
    logger.info(title)
    logger.info("=" * width)
    logger.info("")


# ============================================================================
# Graph: 认证 -> 物料到货 -> 子工序完成 -> 工序完成时间
# ============================================================================

def build_certifies_computation_graph() -> ComputationGraph:
    """
    构建认证/物料/工序计算图（按业务逻辑：先认证影响、再订单+库存决定物料可用时间）。
    - 认证：无记录或未完成认证则认证完成时间 = 开始时间 + 认证周期，否则 = 开始时间。
    - 物料可用：无订单或订单+库存不足则 = 认证完成 + 采购周期；否则 = 最早满足需求的订单到货时间。
    - 子工序/工序完成时间同前。输出均为 ISO 日期时间字符串。
    """
    # InputSpecs
    certification_start_time = InputSpec("property", "Certifies", "reqCertificationStartTime")
    certification_cycle = InputSpec("property", "MPart", "supplierCertificationCycleLt")
    has_certification_record = InputSpec("property", "Certifies", "hasCertificationRecord")
    is_certified = InputSpec("property", "Certifies", "isCertified")
    certification_completion_in = InputSpec("property", "Certifies", "certification_completion_time")
    purchase_cycle = InputSpec("property", "MPart", "purchaseCycleLt")
    has_purchase_orders = InputSpec("property", "MPart", "hasPurchaseOrders")
    total_order_quantity = InputSpec("property", "MPart", "totalOrderQuantity")
    warehouse_inventory = InputSpec("property", "MPart", "warehouseInventory")
    required_quantity = InputSpec("property", "MPart", "requiredQuantity")
    earliest_delivery_time = InputSpec("property", "MPart", "earliestDeliveryTime")
    material_arrival_in = InputSpec("property", "MPart", "material_arrival_time")
    work_calendar_day_001 = InputSpec("property", "AOProcedures", "workCalendarDay")
    work_calendar_day_002 = InputSpec("property", "AOProcedures", "workCalendarDay")
    op001_completion_in = InputSpec("property", "AOProcedures", "op001_completion_time")
    op002_completion_in = InputSpec("property", "AOProcedures", "op002_completion_time")
    plan_start_time = InputSpec("property", "VehicleBatch", "startTime")

    # OutputSpecs（均为 ISO 日期时间字符串）
    certification_completion_out = OutputSpec("property", "Certifies", "certification_completion_time")
    material_arrival_out = OutputSpec("property", "MPart", "material_arrival_time")
    op001_completion_out = OutputSpec("property", "AOProcedures", "op001_completion_time")
    op002_completion_out = OutputSpec("property", "AOProcedures", "op002_completion_time")
    process_completion_out = OutputSpec("property", "VehicleBatch", "process_completion_time")

    # 1. 认证完成时间：无认证记录或未完成认证则 开始时间+认证周期，否则 开始时间
    calc_certification_completion = ComputationNode(
        id="calc_certification_completion_time",
        name="certification_completion_time",
        level=ComputationLevel.PROPERTY,
        inputs=(certification_start_time, certification_cycle, has_certification_record, is_certified),
        outputs=(certification_completion_out,),
        code="(datetime.fromisoformat(reqCertificationStartTime.replace('Z','+00:00')) + timedelta(days=supplierCertificationCycleLt)).isoformat() if not ((hasCertificationRecord or False) and (isCertified or False)) else datetime.fromisoformat(reqCertificationStartTime.replace('Z','+00:00')).isoformat()",
        engine=ComputationEngine.PYTHON,
        priority=0,
    )
    # 2. 物料可用时间：无订单或订单+库存不足则 认证完成+采购周期；否则 最早满足需求的订单到货时间
    calc_material_arrival = ComputationNode(
        id="calc_material_arrival_time",
        name="material_arrival_time",
        level=ComputationLevel.PROPERTY,
        inputs=(
            certification_completion_in,
            purchase_cycle,
            has_purchase_orders,
            total_order_quantity,
            warehouse_inventory,
            required_quantity,
            earliest_delivery_time,
        ),
        outputs=(material_arrival_out,),
        code="(datetime.fromisoformat(certification_completion_time.replace('Z','+00:00')) + timedelta(days=purchaseCycleLt)).isoformat() if (not (hasPurchaseOrders or False)) or ((totalOrderQuantity or 0) + (warehouseInventory or 0)) < (requiredQuantity or 1) or not ((earliestDeliveryTime or '') and str(earliestDeliveryTime or '').strip()) else str(earliestDeliveryTime or '').strip()",
        engine=ComputationEngine.PYTHON,
        priority=0,
    )
    # 3. 子工序1完成时间（先序）：仅依赖 startTime + 工期，由计算关系显式表达，不读数据节点
    calc_op001_completion = ComputationNode(
        id="calc_op001_completion_time",
        name="op001_completion_time",
        level=ComputationLevel.PROPERTY,
        inputs=(work_calendar_day_001, plan_start_time),
        outputs=(op001_completion_out,),
        code="(datetime.fromisoformat(startTime.replace('Z','+00:00')) + timedelta(days=workCalendarDay)).isoformat()",
        engine=ComputationEngine.PYTHON,
        priority=0,
    )
    # 4. 子工序2完成时间（后序）：显式依赖物料到货与工序1完成时间 max(物料,op001)+工期，由计算关系表达
    calc_op002_completion = ComputationNode(
        id="calc_op002_completion_time",
        name="op002_completion_time",
        level=ComputationLevel.PROPERTY,
        inputs=(material_arrival_in, op001_completion_in, work_calendar_day_002),
        outputs=(op002_completion_out,),
        code="(max(datetime.fromisoformat(material_arrival_time.replace('Z','+00:00')), datetime.fromisoformat(op001_completion_time.replace('Z','+00:00'))) + timedelta(days=workCalendarDay)).isoformat()",
        engine=ComputationEngine.PYTHON,
        priority=0,
    )
    # 5. 工序完成时间 = max(子工序1完成时间, 子工序2完成时间)（日期取较晚）
    calc_process_completion = ComputationNode(
        id="calc_process_completion_time",
        name="process_completion_time",
        level=ComputationLevel.PROPERTY,
        inputs=(op001_completion_in, op002_completion_in),
        outputs=(process_completion_out,),
        code="max(datetime.fromisoformat(op001_completion_time.replace('Z','+00:00')), datetime.fromisoformat(op002_completion_time.replace('Z','+00:00'))).isoformat()",
        engine=ComputationEngine.PYTHON,
        priority=0,
    )

    # Relationships：数据节点与计算节点之间的 DEPENDS_ON / OUTPUT_TO
    rels: List[ComputationRelationship] = [
        # Certifies, MPart -> calc_certification_completion
        ComputationRelationship(
            "rel_cert_start_to_calc", "Certifies_DataNode_001", "calc_certification_completion_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=certification_start_time
        ),
        ComputationRelationship(
            "rel_cycle_to_calc", "MPart_DataNode_001", "calc_certification_completion_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=certification_cycle
        ),
        ComputationRelationship(
            "rel_has_cert_record_to_calc", "Certifies_DataNode_001", "calc_certification_completion_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=has_certification_record
        ),
        ComputationRelationship(
            "rel_is_certified_to_calc", "Certifies_DataNode_001", "calc_certification_completion_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=is_certified
        ),
        ComputationRelationship(
            "rel_calc_to_certifies", "calc_certification_completion_time", "Certifies_DataNode_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=certification_completion_out
        ),
        # Certifies, MPart -> calc_material_arrival（物料可用时间：认证完成 + 订单/库存逻辑）
        ComputationRelationship(
            "rel_cert_completion_to_material", "Certifies_DataNode_001", "calc_material_arrival_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=certification_completion_in
        ),
        ComputationRelationship(
            "rel_purchase_to_material", "MPart_DataNode_001", "calc_material_arrival_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=purchase_cycle
        ),
        ComputationRelationship(
            "rel_has_orders_to_material", "MPart_DataNode_001", "calc_material_arrival_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=has_purchase_orders
        ),
        ComputationRelationship(
            "rel_total_order_qty_to_material", "MPart_DataNode_001", "calc_material_arrival_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=total_order_quantity
        ),
        ComputationRelationship(
            "rel_warehouse_inv_to_material", "MPart_DataNode_001", "calc_material_arrival_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=warehouse_inventory
        ),
        ComputationRelationship(
            "rel_required_qty_to_material", "MPart_DataNode_001", "calc_material_arrival_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=required_quantity
        ),
        ComputationRelationship(
            "rel_earliest_delivery_to_material", "MPart_DataNode_001", "calc_material_arrival_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=earliest_delivery_time
        ),
        ComputationRelationship(
            "rel_material_to_mpart", "calc_material_arrival_time", "MPart_DataNode_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=material_arrival_out
        ),
        # AOProcedures_001, VehicleBatch -> calc_op001_completion（先序：仅 startTime + workCalendarDay）
        ComputationRelationship(
            "rel_work001_to_calc", "AOProcedures_DataNode_001", "calc_op001_completion_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=work_calendar_day_001
        ),
        ComputationRelationship(
            "rel_batch_start_to_op001", "VehicleBatch_DataNode_001", "calc_op001_completion_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=plan_start_time
        ),
        ComputationRelationship(
            "rel_op001_to_ao001", "calc_op001_completion_time", "AOProcedures_DataNode_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=op001_completion_out
        ),
        # MPart(物料到货), AOProcedures_001(工序1完成), AOProcedures_002(工期) -> calc_op002_completion（后序：显式依赖）
        ComputationRelationship(
            "rel_material_to_op002", "MPart_DataNode_001", "calc_op002_completion_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=material_arrival_in
        ),
        ComputationRelationship(
            "rel_op001_completion_to_op002", "AOProcedures_DataNode_001", "calc_op002_completion_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=op001_completion_in
        ),
        ComputationRelationship(
            "rel_work002_to_calc", "AOProcedures_DataNode_002", "calc_op002_completion_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=work_calendar_day_002
        ),
        ComputationRelationship(
            "rel_op002_to_ao002", "calc_op002_completion_time", "AOProcedures_DataNode_002",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=op002_completion_out
        ),
        # AOProcedures_001, AOProcedures_002 -> calc_process_completion
        ComputationRelationship(
            "rel_op001_to_process", "AOProcedures_DataNode_001", "calc_process_completion_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=op001_completion_in
        ),
        ComputationRelationship(
            "rel_op002_to_process", "AOProcedures_DataNode_002", "calc_process_completion_time",
            "dep", ComputationRelationType.DEPENDS_ON, "property", datasource=op002_completion_in
        ),
        ComputationRelationship(
            "rel_process_to_batch", "calc_process_completion_time", "VehicleBatch_DataNode_001",
            "out", ComputationRelationType.OUTPUT_TO, "property", data_output=process_completion_out
        ),
    ]

    graph = ComputationGraph(id="certifies")
    for node in [
        calc_certification_completion,
        calc_material_arrival,
        calc_op001_completion,
        calc_op002_completion,
        calc_process_completion,
    ]:
        graph = graph.add_computation_node(node)
    for r in rels:
        graph = graph.add_computation_relationship(r)
    return graph


# ============================================================================
# Data: 与计算逻辑对应的节点数据（含认证开始天数等输入）
# ============================================================================

def build_certifies_node_data() -> Dict[str, Dict]:
    """与计算图一致的数据节点数据；每条的 uuid 即数据节点 ID（xxx_DataNode_xxx），便于从 Neo4j 按 uuid 加载。"""
    raw = {
        "Supplier_DataNode_001": {
            "id": "S03",
            "certificationStatus": "已认证",
            "supplierAddress": "北京市海淀区",
            "supplierName": "北京科技有限公司",
            "supplierType": "工装供应商",
            "type": "Supplier",
            "uuid": "Supplier_uuid_001",
            "element_type": "NODE"
        },
        "MPart_DataNode_001": {
            "id": "火花塞",
            "materialCost": 100.0,
            "mpartCategory": "采购件",
            "mpartId": "Part0500",
            "mpartMaterial": "复合材料",
            "mpartNit": "个",
            "mpartSpecification": 305,
            "purchaseCost": 100.0,
            "purchaseCycleLt": 30,
            "sourceMethod": "Buy",
            "status": "active",
            "supplierCertificationCycleLt": 30,
            "type": "MPart",
            "uuid": "MPart_uuid_001",
            "element_type": "NODE"
        },
        "AOProcedures_DataNode_001": {
            "id": "AO_OP3001",
            "apOpCpde": "AO_OP3001",
            "opName": "汽车-工序B1",
            "stationName": "A001-工位1",
            "type": "AOProcedures",
            "workCalendarDay": 30.0,
            "uuid": "AOProcedures_uuid_001",
            "element_type": "NODE"
        },
        "AOProcedures_DataNode_002": {
            "id": "AO_OP3002",
            "apOpCpde": "AO_OP3002",
            "opName": "汽车-工序B1",
            "stationName": "A001-工位1",
            "type": "AOProcedures",
            "workCalendarDay": 13.0,
            "uuid": "AOProcedures_uuid_002",
            "element_type": "NODE"
        },
        "VehicleBatch_DataNode_001": {
            "id": "C201",
            "aoId": "AO001",
            "projectId": "0003",
            "startTime": "2026-01-24T00:00:01",
            "status": "进行中",
            "type": "VehicleBatch",
            "vehicleBatch": "20",
            "vehicleModel": "CF02",
            "uuid": "VehicleBatch_uuid_001",
            "element_type": "NODE"
        },
        "Certifies_DataNode_001": {
            "id": "0005",
            "start_id": "MPart_uuid_001",
            "end_id": "Supplier_uuid_001",
            "type": "Certifies",
            "mpartCode": "火花塞",
            "purchaseShare": "100%",
            "reqCertificationStartTime": "2025-12-21T00:00:01",
            "status": "认证中",
            "supplierCode": "S03",
            "uuid": "Certifies_uuid_001",
            "element_type": "EDGE"
        },
        "Requires_DataNode_001": {
            "id": "0005",
            "aoCode": "P40",
            "aoOpCode": "AO_OP3002",
            "start_id": "AOProcedures_uuid_002",
            "end_id": "MPart_uuid_001",
            "mPartCode": "火花塞",
            "requiredQuantity": 1,
            "type": "Requires",
            "uuid": "Requires_uuid_001",
            "element_type": "EDGE"
        },
        "MPartStatus_DataNode_001": {
            "id": "0702",
            "aoOpCode": "AO_OP3002",
            "mPartCode": "火花塞",
            "materialStatus": "未冻结",
            "process": "汽车-工序B2",
            "start_id": "VehicleBatch_uuid_001",
            "end_id": "MPart_uuid_001",
            "vehicleBatchCode": "C201",
            "type": "MPartStatus",
            "uuid": "MPartStatus_uuid_001",
            "element_type": "EDGE"
        },
        "AOProcedureStatus_DataNode_001": {
            "id": "0602",
            "aoOpCode": "AO_OP3002",
            "operationName": "汽车-工序B2",
            "vehicleBatchCode": "C201",
            "start_id": "VehicleBatch_uuid_001",
            "end_id": "AOProcedures_uuid_002",
            "type": "AOProcedureStatus",
            "uuid": "AOProcedureStatus_uuid_001",
            "element_type": "EDGE"
        },
        "AOProcedureStatus_DataNode_002": {
            "id": "0601",
            "aoOpCode": "AO_OP3001",
            "operationName": "汽车-工序B1",
            "vehicleBatchCode": "C201",
            "start_id": "VehicleBatch_uuid_001",
            "end_id": "AOProcedures_uuid_001",
            "type": "AOProcedureStatus",
            "uuid": "AOProcedureStatus_uuid_002",
            "element_type": "EDGE"
        },
        "HappensAfter_DataNode_001": {
            "id": "0005",
            "uuid": "HappensAfter_uuid_001",
            "type": "HappensAfter",
            "start_id": "AOProcedures_uuid_001",
            "end_id": "AOProcedures_uuid_002",
            "element_type": "EDGE"
        }
    }
    # 每条数据的 uuid 固定为数据节点 ID（xxx_DataNode_xxx），与 Neo4j 中按 uuid 查找一致
    return raw

def get_graph_datanode_uuids() -> Dict[str, str]:
    # DataNode和具体数据节点uuid的映射
    return {
        "AOProcedures_DataNode_001": "AOProcedures_uuid_001",
        "AOProcedures_DataNode_002": "AOProcedures_uuid_002",
        "VehicleBatch_DataNode_001": "VehicleBatch_uuid_001",
        "Certifies_DataNode_001": "Certifies_uuid_001",
        "Requires_DataNode_001": "Requires_uuid_001",
        "MPartStatus_DataNode_001": "MPartStatus_uuid_001",
        "AOProcedureStatus_DataNode_001": "AOProcedureStatus_uuid_001",
        "AOProcedureStatus_DataNode_002": "AOProcedureStatus_uuid_002",
        "HappensAfter_DataNode_001": "HappensAfter_uuid_001",
        "Supplier_DataNode_001": "Supplier_uuid_001",
        "MPart_DataNode_001": "MPart_uuid_001"
    }

# ============================================================================
# Main
# ============================================================================

async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print_header("认证与物料/工序计算图 Demo")
    logger.info("计算链: 认证完成时间 -> 物料到货时间 -> 子工序完成时间 -> 工序完成时间(max)")
    logger.info("工序依赖由计算图显式表达：先序仅 startTime+工期，后序显式依赖物料到货与先序完成")
    logger.info("")

    graph = build_certifies_computation_graph()
    neo4j_manager: Neo4jGraphManager = _MockNeo4jManager(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    node_data_map: Dict[str, Dict]

    # 优先从 Neo4j 按 get_graph_datanode_uuids 映射加载数据节点属性；失败则使用内存数据
    try:
        _manager = Neo4jGraphManager(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        await _manager.connect()
        datanode_uuids = get_graph_datanode_uuids()
        logger.info("Connected to Neo4j，按 data_node_id->neo4j_uuid 映射加载节点数据…")
        node_data_map = await _manager.load_graph_data_from_neo4j(
            graph, data_node_id_to_neo4j_uuid=datanode_uuids
        )
        neo4j_manager = _manager
        logger.info("已从 Neo4j 加载 %s 个数据节点", len(node_data_map))
    except Exception as e:
        logger.warning("从 Neo4j 加载失败，改用内存数据: %s", e)
        logger.info("提示: 先运行 python -m examples.seed_certifies_neo4j 写入 Neo4j 后再运行本 demo 可从 Neo4j 读数据。")
        node_data_map = build_certifies_node_data()

    print_header("Step 1: 基线执行")
    executor = ComputationGraphExecutor(graph, node_data_map)
    executor.execute(verbose=True)
    executor.print_node_data("基线结果")
    logger.info("")

    # 将计算图与基线结果同步到 Neo4j，便于在 Browser 中可视化（仅当已连接 Neo4j 时）
    print_header("Step 2: 同步计算图到 Neo4j（数据节点 + 计算节点 + 关系）")
    if not isinstance(neo4j_manager, _MockNeo4jManager):
        try:
            await neo4j_manager.sync_graph_to_neo4j(graph, node_data_map=executor.get_all_data_nodes())
            logger.info("Synced: %s data nodes, %s computation nodes, %s relationships",
                        len(node_data_map), len(graph.computation_nodes), len(graph.computation_relationships))
            neo4j_manager.print_visualization_instructions(graph)
            logger.info("Neo4j 已连接，可在 Neo4j Browser (http://localhost:7474) 中查看计算图。")
        finally:
            await neo4j_manager.disconnect()
            logger.info("Neo4j connection closed.")
    else:
        logger.info("未连接 Neo4j，跳过同步。启动 Neo4j 并先运行 seed_certifies_neo4j 后，本 demo 将自动从 Neo4j 读数据并同步。")
    logger.info("")

    # What-If：认证周期延长（verbose=True 打印计算过程）
    print_header("Step 3: What-If — 供应商认证周期由 30 天改为 40 天")
    simulator = WhatIfSimulator(executor, neo4j_manager=_MockNeo4jManager(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD))  # What-If 仅内存，不写 Neo4j
    result = await simulator.run_scenario(
        [("MPart_DataNode_001", "supplierCertificationCycleLt", 40)],
        title="认证周期延长 10 天",
        verbose=True,
    )
    format_scenario_result(result, label="认证周期延长", log_fn=logger.info)
    logger.info("")

    # What-If：采购周期缩短（打印计算过程）
    print_header("Step 4: What-If — 采购周期由 30 天改为 20 天")
    result2 = await simulator.run_scenario(
        [("MPart_DataNode_001", "purchaseCycleLt", 20)],
        title="采购周期缩短 10 天",
        verbose=True,
    )
    format_scenario_result(result2, label="采购周期缩短", log_fn=logger.info)
    logger.info("")

    print_header("Demo 完成")
    logger.info("认证/物料/工序计算图执行完毕，What-If 结果已输出。")


if __name__ == "__main__":
    asyncio.run(main())