---
name: data-analysis
description: 데이터 분석, 수치 계산, 모델 피팅, 통계 검정, 시뮬레이션, 대용량 CSV/parquet 처리. science-kernel MCP 의 지속 커널(python_exec)에서 단계별로 실행하고, 결정에 필요한 값만 출력하며, 결과 파일은 outputs/ 에 저장 후 artifact_save 로 계보를 남긴다.
---

# 데이터 분석 (data-analysis)

## 실행 규칙
- 한 셀 = 한 단계(로드→계산→판단 값 출력). 루프는 셀 안에서 돌린다(도구 호출 왕복 최소화).
- 출력은 다음 결정을 좌우하는 값만. 10줄 넘는 표는 파일로 쓰고 필요한 부분만 읽는다.
- 무거운 중간 상태(파싱된 DB, 학습 모델)는 `outputs/checkpoints/*.parquet|pkl` 로 저장.
- 보고하는 모든 숫자는 실행한 코드 또는 읽은 파일에서 나온다. 실패/대체/부분 실행은 그대로 밝힌다.
- 패키지가 없으면(ImportError) 설치하거나 다른 환경 사용 — 방법을 바꾸지 않는다.
- 장시간(>10분) 작업은 백그라운드로 돌리고 진행 상황을 로그 파일로 확인.

## 통계 최소 요건
- 효과 크기 + 불확도(95% CI) + n + 검정명. p값만 보고 금지.
- 다중 비교 보정 명시, 이상치 처리 규칙은 분석 전에 정한다.
- 피팅: 잔차 확인, 파라미터 표준오차, 물리적으로 타당한 범위인지 점검.

## 산출물
- 표/그림 뒤의 데이터는 CSV 로 함께 저장(`save_figure(data=...)`).
- `artifact_save(paths, description, data_status=measured|simulated|illustrative)`.
- 원자료 열 이름/단위가 바뀌면 원본 열 이름 사본을 보존(재현용).
