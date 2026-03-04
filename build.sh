#!/usr/bin/env bash
# 一键打包 NexusMatrix Skill zip
# 输出: dist/nexus_matrix_skill-0.1.0.zip

set -e
cd "$(dirname "$0")"
python skill/build.py
