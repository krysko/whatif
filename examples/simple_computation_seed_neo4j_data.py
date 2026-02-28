"""
在 Neo4j 中预创建 simple_computation_chain 所需的业务节点（Order、Invoice）。

Neo4j 里存的是场景相关的节点类型（如 Order、Invoice），不是 DataNode。
只有在加入计算图时，才按 uuid 取出这些节点的属性，在内存中形成 DataNode 与 ComputationNode 相连。

运行前请确保 Neo4j 已启动。执行本脚本后，再运行 simple_computation_chain.py 时会
按计算图从 Neo4j 拉取这些节点的属性形成数据节点。

用法:
  python examples/seed_neo4j_data.py

若需清空后重建: python examples/seed_neo4j_data.py --clear
（会删除带对应 uuid 的节点，与标签无关）
"""

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_root = Path(__file__).parent.parent
src_path = _root / "src"
sys.path.insert(0, str(src_path))
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from examples.demo_utils import clear_nodes_by_uuids
from domain.services import Neo4jGraphManager


NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789"

# uuid -> 业务节点规格（label + 属性）；加入计算图时按 uuid 取出属性形成 DataNode
SEED_SPECS = {
    "order_001": {
        "label": "Order",
        "order_id": "ORD-001",
        "customer": "Acme Corp",
        "price": 100.0,
        "quantity": 5,
    },
    "invoice_001": {
        "label": "Invoice",
        "invoice_id": "INV-001",
        "customer": "Acme Corp",
        "tax_rate": 0.1,
    },
}


async def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Pre-create business nodes (Order, Invoice) in Neo4j for simple_computation_chain"
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
        logger.info("Done. Run: python examples/simple_computation_chain.py")
    except Exception as e:
        logger.error("Error: %s", e)
        logger.info("Tip: Start Neo4j with: docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/123456789 neo4j")
        raise


if __name__ == "__main__":
    asyncio.run(main())
