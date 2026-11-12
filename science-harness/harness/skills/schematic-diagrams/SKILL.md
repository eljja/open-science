---
name: schematic-diagrams
description: 개념도, 아키텍처 다이어그램, 공정 흐름도, 소자 단면도/밴드 다이어그램, 실험 셋업, 파이프라인 순서도 같은 schematic 그림을 만든다. 단순 블록도는 sciharness.schematic(matplotlib), 그래프형은 graphviz, 문서 내장은 mermaid, LaTeX 논문은 TikZ. 생성 후 반드시 이미지로 확인.
---

# 개념도 / 회로도 (schematic-diagrams)

## 도구 선택
| 목적 | 도구 | 이유 |
|---|---|---|
| 계층 아키텍처, 블록+화살표 ≤ 30개 | `sciharness.schematic.Diagram` | 좌표 직접 제어, 데이터 그림과 같은 글꼴/색 |
| 노드 많은 그래프, 의존성/흐름 자동 배치 | graphviz `dot` (`pip install graphviz` + 실행파일) | 자동 레이아웃 |
| Markdown/Confluence 문서 안 다이어그램 | mermaid 코드 블록 | 텍스트로 버전 관리 |
| LaTeX 논문용 벡터 도식 | TikZ (`standalone` 문서 → PDF) | 본문 글꼴과 일치 |
| 소자 단면, 밴드 다이어그램 | matplotlib 직접(사각형 층 + `fill_between`) | 물리 치수 비례 유지 |

## Diagram 사용 예
```python
from sciharness.figures import apply_figure_style
from sciharness.schematic import Diagram
apply_figure_style(lang="ko")
d = Diagram(12, 6)                                  # 좌표 단위 = 임의 격자
d.layer(4.3, 1.5, "클라이언트 계층", color="sky")
d.box("cc", 0.5, 4.5, 2.6, 0.9, "Claude Code", color="navy", sub="CLAUDE.md · hooks")
d.box("mcp", 4.7, 1.0, 2.6, 0.9, "science-kernel", color="green", sub="MCP stdio")
d.arrow("cc", "mcp", "도구 호출")
d.save("outputs/figures/fig_arch", caption="...")
```
- 박스 색은 의미별로 고정(예: 클라이언트=navy, 지시=orange, 도구=green, 저장소=gray). 같은 개념은 데이터 그림과 같은 색·같은 용어.
- 화살표 라벨은 동사구 2~4어절. 교차 화살표는 `curve=` 로 휘거나 배치를 바꾼다.
- 읽는 순서는 좌→우 또는 상→하 한 방향.

## 검증
1. `save` 의 overlaps = 0.
2. `view_image` 로 전체 + 혼잡 구역 크롭 확인: 글자가 박스를 넘지 않는가, 화살표가 박스를 관통하지 않는가, 라벨이 어느 화살표 것인지 명확한가.
3. 용어가 본문/데이터 그림과 일치하는가.

## 이미지 생성 모델 사용 시
일러스트형 개념도(세포, 장비 외형)는 이미지 생성 도구를 쓸 수 있으나, **정량 정보(치수, 수치, 축)는 절대 생성 이미지에 맡기지 않는다**. 캡션에 “생성 이미지(설명용)” 명시.
