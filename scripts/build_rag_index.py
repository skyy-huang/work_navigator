"""
离线构建 RAG 向量索引

用法:
  python scripts/build_rag_index.py                 # 构建全部
  python scripts/build_rag_index.py --graph-only    # 只构建图谱索引
  python scripts/build_rag_index.py --cases-only    # 只构建案例索引

首次运行会自动下载 embedding 模型 (约 95MB)，之后走本地缓存。
"""

import os
import sys
import argparse

# 让 import 能找到项目根目录
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    parser = argparse.ArgumentParser(description="构建 RAG FAISS 向量索引")
    parser.add_argument("--graph-only", action="store_true", help="只构建图谱索引")
    parser.add_argument("--cases-only", action="store_true", help="只构建案例索引")
    parser.add_argument(
        "--model", default="BAAI/bge-small-zh-v1.5",
        help="Embedding 模型名称 (默认: BAAI/bge-small-zh-v1.5)",
    )
    args = parser.parse_args()

    project_root = os.path.join(os.path.dirname(__file__), "..")
    graph_path = os.path.join(project_root, "data", "master_graph.json")
    cases_dir = os.path.join(project_root, "data", "cases")
    persist_dir = os.path.join(project_root, "storage", "rag")

    from rag.retriever import CaseRAG
    rag = CaseRAG(graph_path, cases_dir, persist_dir, model_name=args.model)

    build_both = not args.graph_only and not args.cases_only

    if build_both or args.graph_only:
        if os.path.exists(graph_path):
            print("═══ 构建图谱索引 ═══")
            rag.build_graph_index()
        else:
            print(f"[警告] 未找到 {graph_path}，跳过图谱索引")

    if build_both or args.cases_only:
        if os.path.isdir(cases_dir):
            print("═══ 构建案例索引 ═══")
            rag.build_case_index()
        else:
            print(f"[警告] 未找到 {cases_dir}，跳过案例索引")

    print(f"\n完成！索引已保存至: {persist_dir}")


if __name__ == "__main__":
    main()
