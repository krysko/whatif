"""
将 certifies 计算图所需的数据写入 Neo4j。

- 仅对 element_type=NODE 的条目建点：MERGE (n:Label {uuid}) 并写入属性。
- 对 element_type=EDGE 的条目建边不建点：MERGE (start)-[REL_TYPE {uuid}]->(end)，
  关系类型为 type（如 CERTIFIES、REQUIRES），关系上带 uuid 及该条目的全部属性，
  便于 load 时按 uuid 从边上取属性。

用法（在项目根目录）:
  python -m examples.seed_certifies_neo4j

需先启动 Neo4j，例如:
  docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/123456789 neo4j
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict

# 保证可导入 examples.certifies_demo（其内部会补 src 路径）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from neo4j import AsyncGraphDatabase

from examples.certifies_demo import (
    NEO4J_URI,
    NEO4J_PASSWORD,
    NEO4J_USER,
)

logger = logging.getLogger(__name__)

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

async def seed() -> None:
    node_data = build_certifies_node_data()
    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        async with driver.session() as session:
            # 1. 建「实体」节点：element_type=NODE
            for data_node_id, props in node_data.items():
                if props.get("element_type") != "NODE":
                    continue
                label = props.get("type")
                if not label:
                    logger.warning("跳过无 type 的节点: %s", data_node_id)
                    continue
                query = (
                    f"MERGE (n:{label} {{uuid: $uuid}}) "
                    "ON CREATE SET n = $props "
                    "ON MATCH SET n += $props"
                )
                node_uuid = props.get("uuid", data_node_id)
                await session.run(query, uuid=node_uuid, props=props)
                logger.info("MERGE node %s (%s)", node_uuid, label)

            # 2. 「关系型」只建边：element_type=EDGE；(start)-[TYPE]->(end)，属性（含 uuid）放在边上
            for data_node_id, props in node_data.items():
                if props.get("element_type") != "EDGE":
                    continue
                start_id = props.get("start_id")
                end_id = props.get("end_id")
                if not start_id or not end_id:
                    continue
                rel_type = props.get("type")
                if not rel_type:
                    continue
                rel_props = {k: v for k, v in props.items() if k not in ("start_id", "end_id")}
                query = (
                    "MATCH (a {uuid: $start_id}) "
                    "MATCH (b {uuid: $end_id}) "
                    f"MERGE (a)-[r:{rel_type} {{uuid: $rel_uuid}}]->(b) "
                    "ON CREATE SET r = $rel_props "
                    "ON MATCH SET r += $rel_props"
                )
                rel_uuid = props.get("uuid", data_node_id)
                await session.run(
                    query,
                    start_id=start_id,
                    end_id=end_id,
                    rel_uuid=rel_uuid,
                    rel_props=rel_props,
                )
                logger.info("MERGE rel (%s)-[:%s]->(%s) uuid=%s", start_id, rel_type, end_id, rel_uuid)

        logger.info("已写入实体节点与关系到 Neo4j（关系型仅建边不建点）")
    finally:
        await driver.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(seed())


if __name__ == "__main__":
    main()
