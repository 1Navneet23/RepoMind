import ast
from typing import Optional
from data.git_fetcher import get_file_tree, get_file_content


def chunk_code(code: str) -> list:
    try:
        tree = ast.parse(code)
    except Exception as e:
        print(f"Parse error: {e}")
        return []

    chunks = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            chunk = ast.get_source_segment(code, node)
            chunks.append({
                "name":    node.name,
                "type":    type(node).__name__,
                "content": chunk,
            })
        else:
            chunk = ast.get_source_segment(code, node)
            if chunk:
                chunks.append({
                    "name":    "module_level",
                    "type":    "other",
                    "content": chunk,
                })
    return chunks


def chunk_repo(owner: str, repo: str) -> list:
    all_chunks = []
    files = get_file_tree(owner, repo)

    for file in files:
        content: Optional[str] = get_file_content(owner, repo, file["path"])

        # FIX #3: guard against None content to prevent ast.parse crash
        if content is None:
            print(f"Skipping {file['path']} — could not fetch content")
            continue

        chunks = chunk_code(content)
        for chunk in chunks:
            chunk["file"] = file["path"]
            all_chunks.append(chunk)

    return all_chunks