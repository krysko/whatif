"""
将 certifies 计算图所需的数据写入 Neo4j。

- 仅对「实体」建点：无 start_id/end_id 的条目建为节点，uuid = xxx_DataNode_xxx。
- 对「关系型」条目（含 start_id/end_id）：只建边不建点；(start)-[REL_TYPE]->(end)，
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

# 保证可导入 examples.certifies_demo（其内部会补 src 路径）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from neo4j import AsyncGraphDatabase

from examples.certifies_demo import (
    NEO4J_URI,
    NEO4J_PASSWORD,
    NEO4J_USER,
    build_certifies_node_data,
)

logger = logging.getLogger(__name__)


async def seed() -> None:
    node_data = build_certifies_node_data()
    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        async with driver.session() as session:
            # 1. 只建「实体」节点：无 start_id/end_id 的才建点
            for data_node_id, props in node_data.items():
                if props.get("start_id") is not None and props.get("end_id") is not None:
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
                await session.run(query, uuid=data_node_id, props=props)
                logger.info("MERGE node %s (%s)", data_node_id, label)

            # 2. 「关系型」只建边：有 start_id/end_id 的建 (start)-[TYPE]->(end)，属性（含 uuid）放在边上
            for data_node_id, props in node_data.items():
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
                await session.run(
                    query,
                    start_id=start_id,
                    end_id=end_id,
                    rel_uuid=data_node_id,
                    rel_props=rel_props,
                )
                logger.info("MERGE rel (%s)-[:%s]->(%s) uuid=%s", start_id, rel_type, end_id, data_node_id)

        logger.info("已写入实体节点与关系到 Neo4j（关系型仅建边不建点）")
    finally:
        await driver.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(seed())


if __name__ == "__main__":
    main()
