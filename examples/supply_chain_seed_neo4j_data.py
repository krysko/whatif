"""
在 Neo4j 中预创建 supply_chain_delay_demo 所需的业务节点（Shipment、ProductionPlan、Product）。

Neo4j 里存的是场景相关的节点类型（如 Shipment、ProductionPlan、Product），不是 DataNode。
只有在加入计算图时，才按 uuid 取出这些节点的属性，在内存中形成 DataNode 与 ComputationNode 相连。

运行前请确保 Neo4j 已启动。执行本脚本后，再运行 supply_chain_delay_demo.py 时会
按计算图从 Neo4j 拉取这些节点的属性形成数据节点。

用法:
  python examples/supply_chain_seed_neo4j_data.py

若需清空后重建: python examples/supply_chain_seed_neo4j_data.py --clear
（会删除带对应 uuid 的节点，与标签无关）
"""

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from domain.services import Neo4jGraphManager


NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789"

# uuid -> 业务节点规格（label + 属性）；加入计算图时按 uuid 取出属性形成 DataNode
SEED_SPECS = {
    "shipment_001": {
        "label": "Shipment",
        "shipment_id": "SHP-001",
        "planned_delivery_days": 100,
        "actual_delivery_days": 100,
    },
    "production_plan_001": {
        "label": "ProductionPlan",
        "plan_id": "PLAN-001",
        "planned_start_days": 102,
        "production_duration_days": 5,
    },
    "product_001": {
        "label": "Product",
        "product_id": "PROD-001",
        "name": "Widget A",
    },
}


async def clear_nodes_by_uuids(manager: Neo4jGraphManager, uuids: list):
    """按 uuid 删除节点（任意标签），便于重复运行脚本时先清后建"""
    driver = manager.data_provider._get_driver()
    if not driver:
        return
    async with driver.session() as session:
        for uid in uuids:
            await session.run(
                "MATCH (n) WHERE n.uuid = $uid DETACH DELETE n",
                uid=uid,
            )
    logger.info("Cleared nodes with uuid in %s", uuids)


async def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Pre-create business nodes (Shipment, ProductionPlan, Product) in Neo4j for supply_chain_delay_demo"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete existing nodes with these uuids (any label) before creating",
    )
    args = parser.parse_args()

    manager = Neo4jGraphManager(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    try:
        await manager.connect()
        logger.info("Connected to Neo4j")

        if args.clear:
            await clear_nodes_by_uuids(manager, list(SEED_SPECS.keys()))

        mapping = await manager.create_business_nodes(SEED_SPECS)
        logger.info("Created %s business nodes:", len(mapping))
        for node_uuid, neo4j_id in mapping.items():
            label = SEED_SPECS[node_uuid].get("label", "?")
            logger.info("  %s (%s) -> %s", node_uuid, label, neo4j_id)

        await manager.disconnect()
        logger.info("Done. Run: python examples/supply_chain_delay_demo.py")
    except Exception as e:
        logger.error("Error: %s", e)
        logger.info("Tip: Start Neo4j with: docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/123456789 neo4j")
        raise


if __name__ == "__main__":
    asyncio.run(main())
