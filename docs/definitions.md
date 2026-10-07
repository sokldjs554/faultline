# 고장 정의

## 파일 형식

정의는 YAML 파일 하나다. `faultline definitions`로 내장 정의 6개를 볼 수 있고, `faultline evaluate 정의.yaml`이나 콘솔의 내 로그 탭에서 직접 쓴 정의를 평가한다.

```yaml
name: d3_corroborated
version: 1
description: 긴급이거나 민원이 뒷받침하는 작업지시, 민원 군집 포함
wo:
  kinds: [emergency, corrective]     # 고장 후보로 볼 작업지시 유형
  require: emergency_or_complaint    # none | emergency_or_complaint | complaint
complaints:
  support_window_days: [-3, 14]      # 작업지시 생성일 기준 민원이 있어야 하는 범위
  cluster:
    enabled: true                    # 작업지시 없이 민원만 모여도 사건으로 봄
    min_count: 3
    window_days: 5
    require_unique_asset: true       # 민원이 가리키는 설비가 하나로 특정될 때만
merge_window_days: 14                # 같은 설비의 기록이 이 기간 안이면 한 사건
event_time: earliest_evidence        # earliest_evidence | first_record
```

| 항목 | 뜻 |
|---|---|
| `wo.kinds` | 정규화된 작업지시 유형(긴급, 시정) 중 고장 후보 |
| `wo.require` | `none`은 후보를 모두 인정, `emergency_or_complaint`는 긴급이거나 민원이 받쳐 줄 때, `complaint`는 민원이 받쳐 줄 때만 인정 |
| `support_window_days` | 작업지시 생성일 기준 [이전, 이후] 일. 이 범위의 같은 증상 민원이 근거 |
| `cluster` | 같은 증상의 민원이 `window_days` 안에 `min_count`건 모이면 사건. 설비가 하나로 특정되지 않으면 쓰지 않고 센다 |
| `merge_window_days` | 같은 설비의 증거가 이 간격 이내면 한 사건으로 묶음 |
| `event_time` | `earliest_evidence`는 작업지시와 민원 중 이른 날짜, `first_record`는 작업지시 입력일 |

잘못된 파일은 한국어 오류 메시지와 함께 거부한다(없는 유형, 범위가 뒤집힌 창, 음수 기간, YAML 문법 오류).

## 내장 정의 6개

| 이름 | 고장으로 보는 것 | 병합 | 사건 시각 |
|---|---|---|---|
| d1_emergency | 긴급 작업지시 | 7일 | 가장 이른 증거 |
| d2_corrective | 예방이 아닌 작업지시 전부(긴급, 시정) | 7일 | 가장 이른 증거 |
| d3_corroborated | 긴급이거나 민원이 받쳐 주는 작업지시, 민원 군집 포함 | 14일 | 가장 이른 증거 |
| d4_complaint_confirmed | 민원이 받쳐 주는 작업지시만(긴급 표시는 증거로 쓰지 않음) | 14일 | 가장 이른 증거 |
| d5_emergency_loose | 긴급 작업지시, 병합 기간만 넓힘 | 21일 | 가장 이른 증거 |
| d6_corroborated_first_record | d3와 같고 사건 시각이 작업지시 입력일 | 14일 | 입력일 |

d5와 d6은 대조용이다. d5는 병합 기간 하나만 바꾸어도 결과가 거의 안 변하는 것을, d6는 사건 시각 기준이 라벨에 미치는 영향이 작은 것을 보인다.

## 엔진이 하는 일

1. 작업지시 유형을 정규화한다(`quality/contract.py`). 사전에 있는 코드(긴급, URGENT, E)는 그대로 읽고, 사이트가 쓰는 다른 코드(A1)는 코드표를 받는다
2. 정의의 유형에 맞는 작업지시를 후보로 고른다. 설비 번호가 비었거나 중복인 행은 쓰지 않고 센다
3. 민원 근거를 확인한다. 증상이 그 설비 종류에서 날 수 있고, 층이 맞고(기계실 설비는 층 조건을 보지 않음), 설비 단서가 있으면 같은 설비이고, 날짜가 창 안에 있으면 근거다
4. 군집이 켜져 있으면 같은 증상의 민원을 묶는다. 설비 단서가 하나로 모이거나 층이 60% 이상 같아 후보 설비가 하나로 줄면 사건으로 만들고, 아니면 해석하지 못한 군집으로 센다
5. 같은 설비의 증거를 병합 기간으로 이어 붙여 사건을 만든다
6. `as_of_day`를 주면 그날까지 입력된 기록만 쓴다. 학습 라벨을 과거 시점으로 재현할 때 쓴다

## 한계

- 민원 해석은 증상과 층이라는 단서에 기댄다. 단서가 없는 로그에서는 d3, d4의 근거가 약해진다
- 군집에서 설비를 못 정하면 사건을 만들지 않는다. 놓치는 쪽을 택했다
- 정의 파일은 규칙을 표현할 뿐이고, 어느 정의가 맞는지는 [현장 확인](evaluation.md)이 알려 준다
