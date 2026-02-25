"""
WhatIfSimulator 单元测试。

使用真实的 ComputationGraphExecutor（内存数据），Neo4j 部分用 Mock 占位（run_scenario 不写回 Neo4j）。
"""
import pytest

from domain.services.computation_graph_executor import ComputationGraphExecutor
from domain.services.what_if_simulator import ScenarioRunResult, WhatIfSimulator


class _MockNeo4jManager:
    """占位，run_scenario 测试中不调用 Neo4j。"""
    pass


class TestWhatIfSimulator:
    """WhatIfSimulator 测试。"""

    @pytest.fixture
    def executor(self, sample_graph, sample_node_data_map):
        ex = ComputationGraphExecutor(sample_graph, sample_node_data_map)
        ex.execute(verbose=False)
        return ex

    @pytest.mark.asyncio
    async def test_run_scenario_restores_executor(
        self, sample_graph, sample_node_data_map
    ):
        """run_scenario 后 executor 状态与调用前一致（与 baseline 一致）。"""
        executor = ComputationGraphExecutor(sample_graph, sample_node_data_map)
        executor.execute(verbose=False)
        before = executor.get_all_data_nodes()
        simulator = WhatIfSimulator(executor, neo4j_manager=_MockNeo4jManager())
        await simulator.run_scenario(
            [("order_001", "price", 200.0)],
            title="",
        )
        after = executor.get_all_data_nodes()
        assert after["order_001"]["price"] == 100.0
        assert after["invoice_001"]["subtotal"] == 500.0
        assert after == before

    @pytest.mark.asyncio
    async def test_run_scenario_returns_baseline_scenario_diff(
        self, sample_graph, sample_node_data_map
    ):
        """run_scenario 返回的 baseline / scenario / diff 符合预期。"""
        executor = ComputationGraphExecutor(sample_graph, sample_node_data_map)
        executor.execute(verbose=False)
        simulator = WhatIfSimulator(executor, neo4j_manager=_MockNeo4jManager())
        result = await simulator.run_scenario(
            [("order_001", "price", 200.0)],
            title="",
        )
        assert isinstance(result, ScenarioRunResult)
        assert result.baseline["order_001"]["price"] == 100.0
        assert result.baseline["invoice_001"]["subtotal"] == 500.0
        assert result.scenario["order_001"]["price"] == 200.0
        assert result.scenario["invoice_001"]["subtotal"] == 1000.0
        # diff 应包含 order_001.price、invoice_001.subtotal、invoice_001.tax 等变化
        diff_props = {(d["node_id"], d["property_name"]) for d in result.diff}
        assert ("order_001", "price") in diff_props
        assert ("invoice_001", "subtotal") in diff_props
        assert ("invoice_001", "tax") in diff_props
        for d in result.diff:
            if d["node_id"] == "order_001" and d["property_name"] == "price":
                assert d["baseline_value"] == 100.0
                assert d["scenario_value"] == 200.0

    @pytest.mark.asyncio
    async def test_run_scenario_extended_result_fields(
        self, sample_graph, sample_node_data_map
    ):
        """Extended ScenarioRunResult fields are populated: overrides, outputs_per_node, affected_node_ids, success, errors."""
        executor = ComputationGraphExecutor(sample_graph, sample_node_data_map)
        executor.execute(verbose=False)
        simulator = WhatIfSimulator(executor, neo4j_manager=_MockNeo4jManager())
        result = await simulator.run_scenario(
            [("order_001", "price", 200.0), ("order_001", "quantity", 10)],
            title="",
        )
        assert result.overrides == {"order_001": {"price": 200.0, "quantity": 10}}
        assert "order_001" in result.affected_node_ids
        assert "invoice_001" in result.affected_node_ids
        assert result.outputs_per_node.get("invoice_001") is not None
        assert "subtotal" in result.outputs_per_node.get("invoice_001", {})
        assert result.success is True
        assert result.errors == []
