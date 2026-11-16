"""memory MCP 서버 — 영속 메모리 + 스킬 탐색(search_skills).
엔티티: profile(사용자 전역) / project:<이름> / artifact:<id> / frame:<세션>(세션 메모장)
"""
from __future__ import annotations
import json, os
from sciharness.mcp_servers._compat import Server as FastMCP
from sciharness import memory as M, skills_index as S

mcp = FastMCP("memory")

@mcp.tool()
def memory_search(query: str, limit: int = 8) -> str:
    """전체 메모리에서 관련 사실 검색. 작업 시작 전에 한 번 호출(저렴함)."""
    return M.format_recall(M.search(query, limit)) or "(관련 기록 없음)"

@mcp.tool()
def memory_read(entity: str) -> str:
    """엔티티 하나의 전체 행 목록. 예: 'profile', 'project:HK_DTOX'."""
    return json.dumps(M.read(entity), ensure_ascii=False, indent=1)

@mcp.tool()
def memory_write(text: str, entity: str = "project", evidence: str = "observed", category: str | None = None) -> str:
    """오래 남길 사실 1개를 저장(1~2문장). evidence: stated/observed/inferred.
    저장 금지: 파일명/버전처럼 저장소에서 다시 알 수 있는 것, 일시적 작업 상태, 민감 개인정보, 제3자 정보."""
    return M.write(text, entity, evidence, category)

@mcp.tool()
def memory_replace(mem_id: str, text: str, evidence: str | None = None) -> str:
    """기존 행 정정(중복 추가 대신 사용)."""
    return "ok" if M.replace(mem_id, text, evidence) else "not found"

@mcp.tool()
def memory_remove(mem_id: str) -> str:
    """행 삭제."""
    return "ok" if M.remove(mem_id) else "not found"

@mcp.tool()
def search_skills(query: str, k: int = 4) -> str:
    """설치된 스킬(SKILL.md) 어휘 검색. 분야 용어로 여러 번 좁게 검색할 것. 결과의 path 를 읽어 스킬을 로드."""
    hits = S.search(query, k=k, min_score=0.0)
    return json.dumps(hits, ensure_ascii=False, indent=1) if hits else "(일치 스킬 없음)"

def main():
    mcp.run(transport=os.environ.get("MCP_TRANSPORT", "stdio"))

if __name__ == "__main__":
    main()
