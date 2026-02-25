"""
Neo4jDataProvider 使用 mock_data 的单元测试（不连接真实 Neo4j）。
"""
import pytest

from domain.services.computation_executor import Neo4jDataProvider


@pytest.fixture
def mock_provider():
    """使用 mock_data 的 provider，不连接 Neo4j。"""
    return Neo4jDataProvider(mock_data={
        "order_001": {"type": "Order", "uuid": "order_001", "price": 100.0, "quantity": 5},
        "invoice_001": {"type": "Invoice", "uuid": "invoice_001", "tax_rate": 0.1},
    })


class TestNeo4jDataProviderMock:
    """Neo4jDataProvider mock 模式测试。"""

    @pytest.mark.asyncio
    async def test_get_node_data(self, mock_provider):
        data = await mock_provider.get_node_data("order_001")
        assert data is not None
        assert data.get("price") == 100.0
        assert data.get("uuid") == "order_001"
        assert await mock_provider.get_node_data("nonexistent") is None

    @pytest.mark.asyncio
    async def test_set_node_properties(self, mock_provider):
        ok = await mock_provider.set_node_properties("order_001", {"price": 200.0})
        assert ok is True
        data = await mock_provider.get_node_data("order_001")
        assert data.get("price") == 200.0

    @pytest.mark.asyncio
    async def test_create_node(self, mock_provider):
        node_id = await mock_provider.create_node("Order", {"uuid": "new_1", "price": 50.0})
        assert node_id is not None
        # mock 返回 uuid4，数据应已写入 _mock_data
        assert len(mock_provider.mock_data) >= 3

    @pytest.mark.asyncio
    async def test_get_data_node_by_uuid(self, mock_provider):
        result = await mock_provider.get_data_node_by_uuid("order_001")
        # 实现可能返回 (node_id, props) 或 props；mock 当前返回 (node_id, props)
        assert result is not None
        if isinstance(result, tuple):
            _, props = result
        else:
            props = result
        assert props.get("price") == 100.0

    @pytest.mark.asyncio
    async def test_merge_data_node(self, mock_provider):
        uid = await mock_provider.merge_data_node(
            "invoice_001", {"uuid": "invoice_001", "tax_rate": 0.15, "subtotal": 500.0}
        )
        assert uid == "invoice_001"
        key = "datanode_invoice_001"
        assert key in mock_provider.mock_data
        assert mock_provider.mock_data[key]["tax_rate"] == 0.15
        assert mock_provider.mock_data[key]["subtotal"] == 500.0

    @pytest.mark.asyncio
    async def test_close(self, mock_provider):
        await mock_provider.close()
        # mock 下 close 不应抛错
        assert True
