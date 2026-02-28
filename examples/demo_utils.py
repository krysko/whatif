"""
Examples 公共工具：打印标题、按 uuid 清理 Neo4j 节点、Mock Neo4j 管理器。

- print_header: 统一控制台分节标题。
- clear_nodes_by_uuids: 按 uuid 删除 Neo4j 节点（任意标签），便于 seed 脚本 --clear 后重建。
- MockNeo4jManager: 占位对象，不连接 Neo4j，用于 WhatIfSimulator 等仅内存计算场景。
"""

import logging
from typing import Any, List

logger = logging.getLogger(__name__)


def print_header(title: str, width: int = 60) -> None:
    """在日志中输出分节标题（等宽分隔线 + 标题）。"""
    logger.info("=" * width)
    logger.info(title)
    logger.info("=" * width)
    logger.info("")


async def clear_nodes_by_uuids(manager: Any, uuids: List[str]) -> None:
    """
    按 uuid 删除 Neo4j 中的节点（任意标签），便于重复运行 seed 脚本时先清后建。
    manager 需为 Neo4jGraphManager 实例（已 connect），内部通过 data_provider._get_driver() 执行 Cypher。
    """
    data_provider = getattr(manager, "data_provider", None)
    if data_provider is None:
        return
    get_driver = getattr(data_provider, "_get_driver", None)
    driver = get_driver() if get_driver else None
    if not driver:
        return
    async with driver.session() as session:
        for uid in uuids:
            await session.run(
                "MATCH (n) WHERE n.uuid = $uid DETACH DELETE n",
                uid=uid,
            )
    logger.info("Cleared nodes with uuid in %s", uuids)


class MockNeo4jManager:
    """
    占位用 Neo4j 管理器：不连接 Neo4j，不执行任何持久化。
    用于 WhatIfSimulator(neo4j_manager=...) 等仅内存计算的 demo 场景。
    """
