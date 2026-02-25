"""
WhatIfSimulator 单元测试。

使用真实的 ComputationGraphExecutor（内存数据），Neo4j 部分用 Mock 占位（simulate 不写回 Neo4j）。
"""
import pytest

from domain.services.computation_graph_executor import ComputationGraphExecutor
from domain.services.what_if_simulator import WhatIfSimulator


class _MockNeo4jManager:
    """占位，simulate_property_change 测试中不调用 Neo4j。"""
    pass


class TestWhatIfSimulator:
    """WhatIfSimulator 测试。"""

    @pytest.fixture
    def executor(self, sample_graph, sample_node_data_map):
        ex = ComputationGraphExecutor(sample_graph, sample_node_data_map)
        ex.execute(verbose=False)
        return ex

    @pytest.mark.asyncio
    async def test_simulate_property_change_restores_original(
        self, sample_graph, sample_node_data_map
    ):
        executor = ComputationGraphExecutor(sample_graph, sample_node_data_map)
        executor.execute(verbose=False)
        simulator = WhatIfSimulator(executor, neo4j_manager=_MockNeo4jManager())
        # 模拟修改 order_001.price 为 200
        result = await simulator.simulate_property_change(
            "order_001", "price", 200.0, title="Test"
        )
        # 返回的是模拟后的全量数据节点
        assert "order_001" in result
        assert result["order_001"]["price"] == 200.0
        assert result["invoice_001"]["subtotal"] == 1000.0  # 200 * 5
        # 调用后应恢复原始值（restore in finally）
        after_restore = executor.get_all_data_nodes()
        assert after_restore["order_001"]["price"] == 100.0
        assert after_restore["invoice_001"]["subtotal"] == 500.0

    @pytest.mark.asyncio
    async def test_simulate_property_change_returns_modified_state(
        self, sample_graph, sample_node_data_map
    ):
        executor = ComputationGraphExecutor(sample_graph, sample_node_data_map)
        executor.execute(verbose=False)
        simulator = WhatIfSimulator(executor, neo4j_manager=_MockNeo4jManager())
        result = await simulator.simulate_property_change(
            "invoice_001", "tax_rate", 0.2, title="Higher tax"
        )
        assert result["invoice_001"]["tax_rate"] == 0.2
        # 重算后 tax = 500 * 0.2 = 100
        assert result["invoice_001"]["tax"] == 100.0
        # 原始 tax_rate 应被恢复
        assert executor.get_node_data("invoice_001")["tax_rate"] == 0.1
