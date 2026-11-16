---
description: 미검토 그림을 render-then-verify 로 확인
agent: science
---

.science/pending_figure_review.json 과 outputs/figures 의 *.figure.json 을 읽고, 미검토 그림 각각을 view_image 로 전체 1회 + panel_crops 패널별로 확인하라. figure-review 스킬 기준으로 문제를 표로 보고하고, 문제가 있으면 수정 후 다시 저장·확인한다. 대상(비우면 전체): $ARGUMENTS
