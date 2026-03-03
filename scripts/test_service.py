"""
@file_name: test_service.py
@author: Bin Liang
@date: 2026-03-03
@description: 服务集成测试脚本

在不连接 Matrix homeserver 的情况下，
验证数据库、Repository、Embedding、搜索等核心功能。

使用方法:
    python scripts/test_service.py
"""

import asyncio
import json
import sys
import os
import tempfile

# 确保能导入项目模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


async def test_database():
    """测试数据库连接和 CRUD 操作。"""
    print("\n=== 测试数据库 ===")
    from nexus_matrix.storage.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)
        await db.connect()

        # 测试插入
        await db.insert("agents", {
            "agent_id": "agt_test001",
            "agent_name": "TestAgent",
            "matrix_user_id": "@test:localhost",
            "description": "A test agent",
            "capabilities": json.dumps(["chat"]),
            "status": "active",
        })
        print("  [PASS] Insert")

        # 测试查询
        row = await db.fetch_one("SELECT * FROM agents WHERE agent_id = ?", ("agt_test001",))
        assert row is not None
        assert row["agent_name"] == "TestAgent"
        print("  [PASS] Fetch one")

        # 测试更新
        await db.update("agents", {"agent_id": "agt_test001"}, {"agent_name": "UpdatedAgent"})
        row = await db.fetch_one("SELECT * FROM agents WHERE agent_id = ?", ("agt_test001",))
        assert row["agent_name"] == "UpdatedAgent"
        print("  [PASS] Update")

        # 测试查询全部
        await db.insert("agents", {
            "agent_id": "agt_test002",
            "agent_name": "TestAgent2",
            "matrix_user_id": "@test2:localhost",
            "description": "Another test",
            "capabilities": json.dumps(["data_analysis"]),
            "status": "active",
        })
        rows = await db.fetch_all("SELECT * FROM agents WHERE status = ?", ("active",))
        assert len(rows) == 2
        print("  [PASS] Fetch all")

        # 测试删除
        count = await db.delete("agents", {"agent_id": "agt_test001"})
        assert count == 1
        print("  [PASS] Delete")

        await db.disconnect()
    print("  数据库测试全部通过!")


async def test_repositories():
    """测试 Repository 层。"""
    print("\n=== 测试 Repository ===")
    from nexus_matrix.storage.database import Database
    from nexus_matrix.storage.repositories.agent_repo import AgentRepository
    from nexus_matrix.storage.repositories.api_key_repo import ApiKeyRepository
    from nexus_matrix.utils.security import generate_api_key, hash_api_key, generate_id

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)
        await db.connect()

        agent_repo = AgentRepository(db)
        api_key_repo = ApiKeyRepository(db)

        # 创建 Agent
        profile = await agent_repo.create(
            agent_id="agt_repo01",
            agent_name="RepoTestAgent",
            matrix_user_id="@repo_test:localhost",
            description="Agent for repository testing",
            capabilities=["chat", "code_generation"],
        )
        assert profile.agent_id == "agt_repo01"
        assert profile.agent_name == "RepoTestAgent"
        print("  [PASS] Agent create")

        # 按 ID 查询
        found = await agent_repo.get_by_id("agt_repo01")
        assert found is not None
        assert found.capabilities == ["chat", "code_generation"]
        print("  [PASS] Agent get_by_id")

        # 按 Matrix ID 查询
        found = await agent_repo.get_by_matrix_user_id("@repo_test:localhost")
        assert found is not None
        print("  [PASS] Agent get_by_matrix_user_id")

        # 列表查询
        agents = await agent_repo.list_active()
        assert len(agents) == 1
        print("  [PASS] Agent list_active")

        # 更新
        updated = await agent_repo.update("agt_repo01", {
            "description": "Updated description"
        })
        assert updated.description == "Updated description"
        print("  [PASS] Agent update")

        # API Key 测试
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)
        await api_key_repo.create(
            key_id=generate_id("key"),
            api_key_hash=key_hash,
            agent_id="agt_repo01",
            matrix_user_id="@repo_test:localhost",
            access_token="test_token_123",
            device_id="TESTDEVICE",
        )
        print("  [PASS] API Key create")

        key_record = await api_key_repo.get_by_hash(key_hash)
        assert key_record is not None
        assert key_record["access_token"] == "test_token_123"
        print("  [PASS] API Key get_by_hash")

        key_record = await api_key_repo.get_by_agent_id("agt_repo01")
        assert key_record is not None
        print("  [PASS] API Key get_by_agent_id")

        await db.disconnect()
    print("  Repository 测试全部通过!")


async def test_embedding_and_search():
    """测试 Embedding 和语义搜索。"""
    print("\n=== 测试 Embedding & Search ===")
    from nexus_matrix.utils.embedding import EmbeddingService
    from nexus_matrix.storage.database import Database
    from nexus_matrix.storage.repositories.agent_repo import AgentRepository
    from nexus_matrix.registry.search_service import SearchService
    from nexus_matrix.models.registry import AgentSearchRequest
    import numpy as np

    from nexus_matrix.config import get_settings
    settings = get_settings()
    embedding_service = EmbeddingService(api_key=settings.openai_api_key)

    # 测试单文本编码
    vec = embedding_service.encode("Hello, I am a data analysis agent")
    assert vec.shape[0] > 0  # OpenAI text-embedding-3-small 输出 1536 维
    assert abs(np.linalg.norm(vec) - 1.0) < 0.01  # 已归一化
    print(f"  [PASS] Single text encode (dim={vec.shape[0]})")

    # 测试批量编码
    texts = ["chat bot", "data analyst", "code generator"]
    vecs = embedding_service.encode_batch(texts)
    assert vecs.shape[0] == 3
    print(f"  [PASS] Batch encode ({vecs.shape})")

    # 测试相似度
    sim = EmbeddingService.cosine_similarity(vecs[0], vecs[1])
    assert 0 <= sim <= 1
    print(f"  [PASS] Cosine similarity: chat_bot vs data_analyst = {sim:.4f}")

    # 测试序列化
    as_bytes = embedding_service.to_bytes(vec)
    recovered = embedding_service.from_bytes(as_bytes)
    assert np.allclose(vec, recovered)
    print("  [PASS] Serialize/deserialize embedding")

    # 测试语义搜索
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)
        await db.connect()

        agent_repo = AgentRepository(db)
        search_service = SearchService(agent_repo, embedding_service)

        # 创建测试 Agent
        test_agents = [
            ("agt_s1", "ChatMaster", "An AI agent specialized in conversational chat and customer support", ["chat"]),
            ("agt_s2", "DataWizard", "Expert agent for data analysis, visualization, and statistical modeling", ["data_analysis"]),
            ("agt_s3", "CodeGenius", "Code generation and review agent supporting Python, JavaScript, and Go", ["code_generation"]),
            ("agt_s4", "TranslateBot", "Multi-language translation agent supporting 50+ languages", ["translation"]),
            ("agt_s5", "SummaryPro", "Document summarization and key point extraction agent", ["summarization"]),
        ]

        for agent_id, name, desc, caps in test_agents:
            text = f"{name} | {desc} | Capabilities: {', '.join(caps)}"
            emb = embedding_service.encode(text)
            await agent_repo.create(
                agent_id=agent_id,
                agent_name=name,
                matrix_user_id=f"@{name.lower()}:localhost",
                description=desc,
                capabilities=caps,
                embedding=embedding_service.to_bytes(emb),
            )

        print(f"  [PASS] Created {len(test_agents)} test agents")

        # 搜索测试
        results = await search_service.search(AgentSearchRequest(
            query="I need help analyzing data and creating charts",
            limit=3,
        ))
        assert len(results) > 0
        # DataWizard 应该排最前
        print(f"  [PASS] Search 'data analysis': top result = {results[0].agent.agent_name} (score={results[0].score:.4f})")
        assert results[0].agent.agent_name == "DataWizard"

        results = await search_service.search(AgentSearchRequest(
            query="translate English to Chinese",
            limit=3,
        ))
        assert len(results) > 0
        print(f"  [PASS] Search 'translation': top result = {results[0].agent.agent_name} (score={results[0].score:.4f})")

        # 按能力过滤
        results = await search_service.search(AgentSearchRequest(
            query="help me with programming",
            capabilities=["code_generation"],
            limit=3,
        ))
        for r in results:
            assert "code_generation" in r.agent.capabilities
        print(f"  [PASS] Search with capability filter: {len(results)} results")

        # 推荐相似 Agent
        similar = await search_service.recommend_similar("agt_s1", limit=3)
        assert len(similar) > 0
        print(f"  [PASS] Similar agents to ChatMaster: {[s.agent.agent_name for s in similar]}")

        await db.disconnect()
    print("  Embedding & Search 测试全部通过!")


async def test_security():
    """测试安全工具。"""
    print("\n=== 测试安全工具 ===")
    from nexus_matrix.utils.security import generate_api_key, hash_api_key, generate_id

    # API Key 格式
    key = generate_api_key()
    assert key.startswith("nxm_")
    assert len(key) == 36  # "nxm_" + 32
    print(f"  [PASS] API Key format: {key[:20]}...")

    # 哈希一致性
    hash1 = hash_api_key(key)
    hash2 = hash_api_key(key)
    assert hash1 == hash2
    print("  [PASS] Hash consistency")

    # 不同 Key 哈希不同
    key2 = generate_api_key()
    assert hash_api_key(key) != hash_api_key(key2)
    print("  [PASS] Hash uniqueness")

    # ID 生成
    id1 = generate_id("agt")
    assert id1.startswith("agt_")
    assert len(id1) == 12  # "agt_" + 8
    print(f"  [PASS] ID generation: {id1}")

    print("  安全工具测试全部通过!")


async def test_fastapi_app():
    """测试 FastAPI 应用创建。"""
    print("\n=== 测试 FastAPI 应用 ===")
    from nexus_matrix.app import create_app

    app = create_app()
    assert app.title == "NexusMatrix"
    assert app.version == "0.1.0"

    routes = [r.path for r in app.routes]
    assert "/health" in routes
    assert "/api/v1/auth/register" in routes
    assert "/api/v1/rooms/create" in routes
    assert "/api/v1/messages/send" in routes
    assert "/api/v1/sync" in routes
    assert "/api/v1/registry/register" in routes
    assert "/api/v1/registry/search" in routes
    print(f"  [PASS] App created with {len(routes)} routes")

    print("  FastAPI 应用测试通过!")


async def test_skill_build():
    """测试 Skill 包构建。"""
    print("\n=== 测试 Skill 包构建 ===")
    import subprocess
    result = subprocess.run(
        [sys.executable, "skill/build.py"],
        capture_output=True, text=True,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    assert result.returncode == 0, f"Build failed: {result.stderr}"
    print(f"  {result.stdout.strip()}")

    # 验证 zip 内容
    import zipfile
    zip_path = os.path.join(os.path.dirname(__file__), "..", "dist", "nexus_matrix_skill-0.1.0.zip")
    assert os.path.exists(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert any("skill.py" in n for n in names)
        assert any("client.py" in n for n in names)
        assert any("models.py" in n for n in names)
        assert any("README.md" in n for n in names)
        print(f"  [PASS] Zip contains {len(names)} files")

    print("  Skill 包构建测试通过!")


async def main():
    """运行所有测试。"""
    print("=" * 60)
    print("NexusMatrix 集成测试")
    print("=" * 60)

    try:
        await test_security()
        await test_database()
        await test_repositories()
        await test_embedding_and_search()
        await test_fastapi_app()
        await test_skill_build()

        print("\n" + "=" * 60)
        print("所有测试通过!")
        print("=" * 60)
    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
