# 실제 로그에 적용하기

이 저장소는 합성 로그만 다뤘다. 아래는 고객 로그에 적용하는 순서이고, 각 단계는 명령줄로 돌아간다. 합성 세계의 숫자가 고객 로그에서 그대로 나온다는 뜻은 아니다.

## 준비물

| 표 | 필수 열 | 비고 |
|---|---|---|
| 작업지시 | `wo_id`, `site`, `asset`, `created_day`, `closed_day`, `type_raw` | 날짜는 숫자(일)나 날짜 문자열. 날짜면 가장 이른 생성일을 0으로 바꾼다 |
| 설비 대장 | `asset`, `site`, `category`, `floor` | `category`는 내장 8종(ahu, chiller, boiler, pump, fire_pump, elevator, generator, switchgear). 층이 없는 중앙 설비는 `floor`를 -1로 둔다 |
| 민원(선택) | `site`, `floor`, `day`, `symptom`, `hint_asset` | `symptom`은 내장 12가지 증상 중 하나. `hint_asset`은 민원이 설비를 가리킬 때만 |

설비 종류와 민원 증상이 내장 목록과 다르면 먼저 목록에 맞춰야 한다. 민원 문장을 증상으로 바꾸는 부분은 없다.

## 순서

1. 로그 품질 점검

   ```bash
   faultline quality work_orders.csv
   ```

   유형 코드를 못 읽은 사이트, 긴급 비중이 다른 사이트와 크게 다른 사이트, 중복·날짜 역전·설비 번호 누락이 나온다. 코드 미분류 사이트에는 빈도 순서로 짐작한 코드표 제안이 붙는다. 제안은 사람이 확인한다.

2. 코드표 작성. 사이트가 쓰는 코드를 유형으로 옮기는 JSON 파일이다.

   ```json
   {"A1": "emergency", "B2": "corrective", "C3": "preventive"}
   ```

3. 정의 후보 확인. `faultline definitions`로 내장 6개를 보고, 고객사 업무에 맞는 정의가 있으면 [정의 파일](definitions.md)을 쓴다. `faultline evaluate 정의.yaml`은 합성 데모 세계에서 정의를 시험해 보는 용도다.

4. 현장 확인표 만들기. 사이트 하나, 확인 건수 80건 기준이다.

   ```bash
   faultline audit-sample --work-orders wo.csv --assets assets.csv --complaints cm.csv \
     --code-book book.json --site 3 -n 80 -o sample.csv
   ```

   확인표의 한 줄은 설비 하나와 4주 구간(`from_day`~`to_day`)이다. 정의가 고장으로 표시한 구간(S1)과 아무 정의도 표시하지 않은 구간(S0)이 반반 섞여 있다. 관측이 끝난 시점을 알면 `--weeks`로 준다. 주지 않으면 마지막 기록의 날짜로 정하는데, 마지막 몇 주는 입력이 늦어 기록이 덜 채워져 있을 수 있다.

5. 현장 확인. 확인자에게는 `stratum`, `flagged_by` 열을 지운 사본을 준다. 그 설비에 그 구간 안에 고장이 있었는지를 `confirmed` 열에 1(있었음) 또는 0(없었음)으로 적는다. 정지하거나 성능이 떨어져 수리한 것을 고장으로 보고, 소모품 교체 같은 경미한 작업은 고장으로 보지 않는다고 미리 정한다.

6. 정의별 추정

   ```bash
   faultline audit-estimate --work-orders wo.csv --assets assets.csv --complaints cm.csv \
     --code-book book.json --site 3 --sample sample.csv
   ```

   정의별 정밀도, 재현율, F2, 90% 구간과 F2가 가장 높은 정의(`pick`)가 JSON으로 나온다. 구간이 서로 크게 겹치면 확인 건수를 늘린다. 합성 세계에서 확인 건수별로 최선과 0.02 이내인 정의를 고르는 비율은 [평가](evaluation.md)에 있다.

7. 선택한 정의로 라벨을 만들어 모형을 학습한다. 특징은 정의와 무관하게 같다(`models/features.py`).

8. 운영 중 감시. 습관이 바뀌면 같은 정의의 뜻이 바뀐다. 아래처럼 신호를 계산하고, 경보가 나면 4번부터 다시 한다.

   ```python
   from faultline.logs import read_logs
   from faultline.monitor.drift import monitor_sites

   logs = read_logs("wo.csv", "assets.csv", "cm.csv", "book.json")
   res = monitor_sites(logs.wo_norm, logs.assets, logs.n_weeks, logs.complaints)
   ```

## 기대하면 안 되는 것

- 사이트 하나의 고장 구간은 5% 안팎이라 확인 80건에는 고장이 몇 건 안 들어온다. 층화로 S1을 절반 뽑아도 구간이 넓다
- 확인표는 사이트 단위다. 사이트가 많으면 사이트마다 따로 해야 한다
- 감시의 기준 구간(26~78주)에 습관이 이미 흔들리던 사이트는 기준이 틀어진다
- 이 흐름을 실제 사람이 돌려 본 적은 없다
