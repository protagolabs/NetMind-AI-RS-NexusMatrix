"""
@file_name: build.py
@author: Bin Liang
@date: 2026-03-03
@description: Skill 包构建脚本

将 nexus_matrix_skill 打包为 zip 文件，
供其他 AI Agent 下载和使用。

使用方法:
    python skill/build.py

输出:
    dist/nexus_matrix_skill-0.1.0.zip
"""

import os
import shutil
import zipfile
from pathlib import Path


def build_skill_zip() -> str:
    """构建 Skill zip 包。

    将 nexus_matrix_skill 目录打包为 zip，
    包含所有源代码和 README。

    Returns:
        输出文件路径。
    """
    project_root = Path(__file__).parent.parent
    skill_dir = Path(__file__).parent / "nexus_matrix_skill"
    dist_dir = project_root / "dist"
    dist_dir.mkdir(exist_ok=True)

    version = "0.1.0"
    output_name = f"nexus_matrix_skill-{version}"
    output_path = dist_dir / f"{output_name}.zip"

    # 如果已存在则删除
    if output_path.exists():
        output_path.unlink()

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 添加 skill 源代码
        for root, dirs, files in os.walk(skill_dir):
            # 跳过 __pycache__
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for file in files:
                if file.endswith(".pyc"):
                    continue
                file_path = Path(root) / file
                arcname = os.path.join(
                    output_name,
                    os.path.relpath(file_path, skill_dir.parent),
                )
                zf.write(file_path, arcname)

        # 添加项目根目录的文档文件（SKILL.md, HEARTBEAT.md 等）
        for doc_name in ("SKILL.md", "HEARTBEAT.md", "README.md"):
            doc_path = project_root / doc_name
            if doc_path.exists():
                zf.write(doc_path, f"{output_name}/{doc_name}")

        # 添加 README（如果项目根目录没有 README.md 则生成一个）
        if not (project_root / "README.md").exists():
            readme_content = _generate_readme()
            zf.writestr(f"{output_name}/README.md", readme_content)

        # 添加简单的 setup.py
        setup_content = _generate_setup(version)
        zf.writestr(f"{output_name}/setup.py", setup_content)

    print(f"Skill package built: {output_path}")
    print(f"Size: {output_path.stat().st_size / 1024:.1f} KB")
    return str(output_path)


def _generate_readme() -> str:
    """生成 Skill 包 README。"""
    return """# NexusMatrix Skill

Matrix communication skill for AI Agents.

## Quick Start

```python
from nexus_matrix_skill import NexusMatrixSkill

# Initialize
skill = NexusMatrixSkill(service_url="http://localhost:8953")

# Register your agent
result = skill.register(
    agent_name="MyAgent",
    description="A helpful AI assistant that can chat and help with tasks",
    capabilities=["chat", "task_execution"],
)
print(f"Registered! API Key: {result.api_key}")

# Create a room
room = skill.create_room(name="my-room", topic="Agent discussion")

# Send a message
skill.send_message(room.room_id, "Hello from MyAgent!")

# Receive messages
sync = skill.sync()
for msg in sync.messages:
    print(f"{msg.sender}: {msg.body}")

# Check for new messages (lightweight heartbeat)
hb = skill.heartbeat()
if hb.has_updates:
    print(f"You have {hb.total_unread} unread messages!")
    sync = skill.sync()  # Get full details
    for msg in sync.messages:
        print(f"{msg.sender}: {msg.body}")

# Search for other agents
results = skill.search_agents("data analysis agent")
for r in results:
    print(f"{r.agent.agent_name}: {r.score:.2f}")
```

## Features

- Agent registration with semantic search discovery
- Room management (create, join, leave, invite)
- Message sending and receiving
- Lightweight heartbeat for periodic message checking
- Event synchronization (long-polling)
- Agent search and recommendation
- Zero external dependencies (uses only Python stdlib)

## Requirements

- Python >= 3.9
- NexusMatrix service running and accessible

## API Reference

See the NexusMatrix API docs at `http://localhost:8953/docs`
"""


def _generate_setup(version: str) -> str:
    """生成 setup.py。"""
    return f'''from setuptools import setup, find_packages

setup(
    name="nexus_matrix_skill",
    version="{version}",
    packages=find_packages(),
    python_requires=">=3.9",
    description="Matrix communication skill for AI Agents",
    author="Bin Liang",
)
'''


if __name__ == "__main__":
    build_skill_zip()
