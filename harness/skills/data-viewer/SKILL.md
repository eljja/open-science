---
name: data-viewer
description: 원자료/결과 수치를 브라우저에서 탐색하는 단일 HTML 데이터 뷰어(정렬, 열 필터, 검색, 통계, CSV 내보내기)를 만든다. 보고서와 별도로 원시 숫자를 공유하거나 Confluence 첨부로 올릴 때. 오프라인 동작, 외부 라이브러리 없음.
---

# 인터랙티브 데이터 뷰어 (data-viewer)

```python
from sciharness.viewer import build_viewer
build_viewer({"결과 요약": df_summary, "원자료": "data/raw.csv"},
             "outputs/interactive/data_viewer.html", title="<프로젝트> 데이터 뷰어",
             notes={"원자료": "단위: nm, eV. 출처: ..."})
```
- 데이터셋마다 note 에 단위/출처/진본성(측정·계산·설명용)을 적는다.
- 10만 행 이상이면 요약본만 넣고 전체는 CSV 로 별도 제공(HTML 용량).
- Plotly 등 차트 탐색기가 필요하면 plotly `to_html(include_plotlyjs="inline")` 로 별도 파일.
- 빌드 후 브라우저 없이 검증: 파일 크기, 데이터셋 수, 행 수를 출력해 확인.
