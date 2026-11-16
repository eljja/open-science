---
name: report-html
description: Markdown 보고서를 Confluence 업로드용 HTML로 변환한다(인라인 스타일, 그림 base64 내장형 또는 첨부형). 보고서·문서를 공유/게시용 HTML, PDF, docx 로 내보낼 때. 사용자가 HTML 보고서를 요구하면 항상 사용.
---

# HTML 보고서 (report-html)

```python
from sciharness.report import build_html
build_html("outputs/report/report.md", "outputs/html/report.html", mode="embed")          # 단일 파일(그림 내장)
build_html("outputs/report/report.md", "outputs/html/confluence/report.html", mode="attach")  # images/ 첨부형
```
또는 CLI: `python -m sciharness.cli html outputs/report/report.md --mode attach`

## 규칙
- Confluence 본문은 `<style>`·`<script>` 를 버린다 → 스타일은 모두 인라인(빌더가 처리). JavaScript 가 필요한 뷰어(데이터 뷰어 등)는 **페이지 첨부 파일**로 올린다.
- 그림 경로는 md 파일 기준 상대경로. 빌드 후 HTML 을 열어 그림 누락이 없는지 확인(`<img src="data:` 개수 = md 의 그림 수).
- 표는 Markdown 표 그대로(빌더가 테두리/머리행 스타일 부여). 열이 많으면 부록 CSV + 데이터 뷰어로 분리.
- PDF 가 필요하면 pandoc + xelatex(`-V mainfont="Malgun Gothic"`) 또는 브라우저 인쇄. 한글 글꼴 임베드 확인.
- 산출물 저장: md, html(embed), confluence/(attach) 세 벌을 artifact_save.
