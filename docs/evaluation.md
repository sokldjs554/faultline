# 평가

모든 숫자는 `artifacts/`의 JSON에서 채워지고 CI가 일치를 검사한다. 설정은 [설계](design.md)의 평가 프로토콜을 따른다. 시드 5개(7, 11, 23, 31, 47)의 평균을 쓰고, 한 시드만 쓴 것은 표시했다.

## 라벨 품질

정의가 만든 사건을 진짜 고장과 같은 설비에서 14일 이내이면 일대일로 짝지었다(가까운 쌍부터). 시드 7, 사이트 16곳 전체다.

| 정의 | 사건 | 정밀도 | 재현율 | F1 | 시각 오차 중앙값(일) |
|---|---|---|---|---|---|
| d1 긴급만 | <!-- num:base.labels.definitions.d1_emergency.overall.incidents|,d -->1,422<!-- /num --> | <!-- num:base.labels.definitions.d1_emergency.overall.precision|.0% -->63%<!-- /num --> | <!-- num:base.labels.definitions.d1_emergency.overall.recall|.0% -->46%<!-- /num --> | <!-- num:base.labels.definitions.d1_emergency.overall.f1|.2f -->0.53<!-- /num --> | <!-- num:base.labels.definitions.d1_emergency.overall.timing_median|.0f -->2<!-- /num --> |
| d2 시정 포함 | <!-- num:base.labels.definitions.d2_corrective.overall.incidents|,d -->4,561<!-- /num --> | <!-- num:base.labels.definitions.d2_corrective.overall.precision|.0% -->33%<!-- /num --> | <!-- num:base.labels.definitions.d2_corrective.overall.recall|.0% -->77%<!-- /num --> | <!-- num:base.labels.definitions.d2_corrective.overall.f1|.2f -->0.46<!-- /num --> | <!-- num:base.labels.definitions.d2_corrective.overall.timing_median|.0f -->2<!-- /num --> |
| d3 민원이 받쳐 주는 것 | <!-- num:base.labels.definitions.d3_corroborated.overall.incidents|,d -->2,470<!-- /num --> | <!-- num:base.labels.definitions.d3_corroborated.overall.precision|.0% -->50%<!-- /num --> | <!-- num:base.labels.definitions.d3_corroborated.overall.recall|.0% -->63%<!-- /num --> | <!-- num:base.labels.definitions.d3_corroborated.overall.f1|.2f -->0.56<!-- /num --> | <!-- num:base.labels.definitions.d3_corroborated.overall.timing_median|.0f -->1<!-- /num --> |
| d4 민원이 확인한 것 | <!-- num:base.labels.definitions.d4_complaint_confirmed.overall.incidents|,d -->1,750<!-- /num --> | <!-- num:base.labels.definitions.d4_complaint_confirmed.overall.precision|.0% -->53%<!-- /num --> | <!-- num:base.labels.definitions.d4_complaint_confirmed.overall.recall|.0% -->47%<!-- /num --> | <!-- num:base.labels.definitions.d4_complaint_confirmed.overall.f1|.2f -->0.50<!-- /num --> | <!-- num:base.labels.definitions.d4_complaint_confirmed.overall.timing_median|.0f -->1<!-- /num --> |
| d5 긴급, 병합 넓게 | <!-- num:base.labels.definitions.d5_emergency_loose.overall.incidents|,d -->1,390<!-- /num --> | <!-- num:base.labels.definitions.d5_emergency_loose.overall.precision|.0% -->64%<!-- /num --> | <!-- num:base.labels.definitions.d5_emergency_loose.overall.recall|.0% -->46%<!-- /num --> | <!-- num:base.labels.definitions.d5_emergency_loose.overall.f1|.2f -->0.53<!-- /num --> | <!-- num:base.labels.definitions.d5_emergency_loose.overall.timing_median|.0f -->2<!-- /num --> |
| d6 d3, 입력 시각 | <!-- num:base.labels.definitions.d6_corroborated_first_record.overall.incidents|,d -->2,469<!-- /num --> | <!-- num:base.labels.definitions.d6_corroborated_first_record.overall.precision|.0% -->50%<!-- /num --> | <!-- num:base.labels.definitions.d6_corroborated_first_record.overall.recall|.0% -->63%<!-- /num --> | <!-- num:base.labels.definitions.d6_corroborated_first_record.overall.f1|.2f -->0.56<!-- /num --> | <!-- num:base.labels.definitions.d6_corroborated_first_record.overall.timing_median|.0f -->2<!-- /num --> |

- 전체로는 d3와 d6의 F1이 가장 높고, d1은 정밀하지만 재현율이 낮다
- 사이트 습관별로 나누면 결과가 크게 달라진다. 긴급 코드를 거의 안 쓰는 사이트에서 d1의 재현율은 <!-- num:summary.labels.d1_recall_no_emergency_sites|.0% -->2%<!-- /num -->, 표준 사이트에서는 <!-- num:summary.labels.d1_recall_standard_sites|.0% -->58%<!-- /num -->이다. 긴급 남용 사이트에서 d1의 정밀도는 <!-- num:summary.labels.d1_precision_abuse_sites|.0% -->40%<!-- /num -->로 떨어진다
- d5와 d1의 차이, d6와 d3의 차이는 거의 없다. 병합 기간과 사건 시각 기준은 이 세계에서 중요하지 않다

## 정의 민감도

같은 특징, 같은 모형(HistGradientBoosting)에 라벨만 바꿔 학습하고 평가 구간(주 104~151)에서 채점했다. 자기 라벨은 그 정의가 만든 라벨이고, 진짜는 시뮬레이터의 진짜 고장이다.

| 학습 라벨 | 자기 라벨로 채점(AUC) | 진짜 고장으로 채점(AUC) | 진짜 AUC 범위(시드 5개) |
|---|---|---|---|
| d1 긴급만 | <!-- num:multiseed.base.models.d1_emergency.own_auc.mean|.3f -->0.758<!-- /num --> | <!-- num:multiseed.base.models.d1_emergency.truth_auc.mean|.3f -->0.580<!-- /num --> | <!-- num:multiseed.base.models.d1_emergency.truth_auc.min|.3f -->0.559<!-- /num --> ~ <!-- num:multiseed.base.models.d1_emergency.truth_auc.max|.3f -->0.618<!-- /num --> |
| d2 시정 포함 | <!-- num:multiseed.base.models.d2_corrective.own_auc.mean|.3f -->0.690<!-- /num --> | <!-- num:multiseed.base.models.d2_corrective.truth_auc.mean|.3f -->0.638<!-- /num --> | <!-- num:multiseed.base.models.d2_corrective.truth_auc.min|.3f -->0.629<!-- /num --> ~ <!-- num:multiseed.base.models.d2_corrective.truth_auc.max|.3f -->0.651<!-- /num --> |
| d3 민원이 받쳐 주는 것 | <!-- num:multiseed.base.models.d3_corroborated.own_auc.mean|.3f -->0.700<!-- /num --> | <!-- num:multiseed.base.models.d3_corroborated.truth_auc.mean|.3f -->0.626<!-- /num --> | <!-- num:multiseed.base.models.d3_corroborated.truth_auc.min|.3f -->0.612<!-- /num --> ~ <!-- num:multiseed.base.models.d3_corroborated.truth_auc.max|.3f -->0.645<!-- /num --> |
| d4 민원이 확인한 것 | <!-- num:multiseed.base.models.d4_complaint_confirmed.own_auc.mean|.3f -->0.700<!-- /num --> | <!-- num:multiseed.base.models.d4_complaint_confirmed.truth_auc.mean|.3f -->0.628<!-- /num --> | <!-- num:multiseed.base.models.d4_complaint_confirmed.truth_auc.min|.3f -->0.618<!-- /num --> ~ <!-- num:multiseed.base.models.d4_complaint_confirmed.truth_auc.max|.3f -->0.634<!-- /num --> |
| d5 긴급, 병합 넓게 | <!-- num:multiseed.base.models.d5_emergency_loose.own_auc.mean|.3f -->0.757<!-- /num --> | <!-- num:multiseed.base.models.d5_emergency_loose.truth_auc.mean|.3f -->0.579<!-- /num --> | <!-- num:multiseed.base.models.d5_emergency_loose.truth_auc.min|.3f -->0.562<!-- /num --> ~ <!-- num:multiseed.base.models.d5_emergency_loose.truth_auc.max|.3f -->0.616<!-- /num --> |
| d6 d3, 입력 시각 | <!-- num:multiseed.base.models.d6_corroborated_first_record.own_auc.mean|.3f -->0.701<!-- /num --> | <!-- num:multiseed.base.models.d6_corroborated_first_record.truth_auc.mean|.3f -->0.627<!-- /num --> | <!-- num:multiseed.base.models.d6_corroborated_first_record.truth_auc.min|.3f -->0.610<!-- /num --> ~ <!-- num:multiseed.base.models.d6_corroborated_first_record.truth_auc.max|.3f -->0.643<!-- /num --> |
| 진짜 고장(상한) | 해당 없음 | <!-- num:multiseed.base.models.truth.truth_auc.mean|.3f -->0.644<!-- /num --> | <!-- num:multiseed.base.models.truth.truth_auc.min|.3f -->0.638<!-- /num --> ~ <!-- num:multiseed.base.models.truth.truth_auc.max|.3f -->0.647<!-- /num --> |
| 손상 오라클 | 해당 없음 | <!-- num:multiseed.base.models.oracle.truth_auc.mean|.3f -->0.773<!-- /num --> | <!-- num:multiseed.base.models.oracle.truth_auc.min|.3f -->0.766<!-- /num --> ~ <!-- num:multiseed.base.models.oracle.truth_auc.max|.3f -->0.780<!-- /num --> |

- d2가 d1보다 높은 시드는 <!-- num:summary.auc.d2_beats_d1_seeds|d -->5<!-- /num -->개 중 <!-- num:summary.auc.d2_beats_d1_seeds|d -->5<!-- /num -->개이고, 차이의 평균은 <!-- num:summary.auc.d2_minus_d1|.3f -->0.058<!-- /num -->(가장 작은 시드 <!-- num:summary.auc.d2_minus_d1_min|.3f -->0.033<!-- /num -->)이다
- d1과 d5의 자기 라벨 AUC가 가장 높다. 자기 라벨로 고른 1위가 진짜 1위인 시드는 <!-- num:summary.apparent.best_by_own_is_best_by_truth|d -->0<!-- /num -->개다. 모형이 사이트 수준의 긴급 비중 특징으로 습관을 읽어 자기 라벨을 맞히는 것으로 보인다
- d2의 진짜 AUC는 진짜 고장으로 학습한 모형(<!-- num:summary.auc.truth_label|.3f -->0.644<!-- /num -->)에 가깝다. 특징이 담은 신호의 상한이 거기까지라는 뜻이다
- 점검 5곳을 고를 때 d1과 d2 모형의 선택이 겹치는 비율은 <!-- num:summary.overlap.d1_d2|.2f -->0.22<!-- /num -->이다(시드 7). 진짜 라벨 모형과 비교해도 <!-- num:summary.overlap.d1_truth|.2f -->0.26<!-- /num --> 안팎이라 어느 정의든 선택이 많이 다르다
- 점검 5곳 100번당 적중은 사이트 습관에 따라 순위가 바뀐다. 긴급 코드를 안 쓰는 사이트에서 d1은 <!-- num:summary.topk.no_emergency_d1|.1f -->6.9<!-- /num -->으로 무작위(<!-- num:summary.topk.no_emergency_random|.1f -->5.5<!-- /num -->)와 비슷하고 d3는 <!-- num:summary.topk.no_emergency_d3|.1f -->11.5<!-- /num -->이다. 표준 사이트에서는 d1이 <!-- num:summary.topk.standard_d1|.1f -->13.3<!-- /num -->으로 d3(<!-- num:summary.topk.standard_d3|.1f -->11.9<!-- /num -->)보다 높다
- PyTorch MLP(같은 입력)도 순위가 같다(시드 7). d1 <!-- num:summary.mlp.d1|.3f -->0.579<!-- /num -->, d2 <!-- num:summary.mlp.d2|.3f -->0.649<!-- /num -->, d3 <!-- num:summary.mlp.d3|.3f -->0.642<!-- /num -->, 진짜 라벨 <!-- num:summary.mlp.truth|.3f -->0.653<!-- /num -->. 모형 종류가 달라도 순위가 같아서 차이의 원천은 라벨로 보인다

## 습관이 모두 같은 대조 세계

모든 사이트가 표준 습관인 세계(시드 3개)에서 같은 비교를 했다.

| 학습 라벨 | 진짜 AUC |
|---|---|
| d1 긴급만 | <!-- num:multiseed.uniform.models.d1_emergency.truth_auc.mean|.3f -->0.654<!-- /num --> |
| d2 시정 포함 | <!-- num:multiseed.uniform.models.d2_corrective.truth_auc.mean|.3f -->0.663<!-- /num --> |
| d3 민원이 받쳐 주는 것 | <!-- num:multiseed.uniform.models.d3_corroborated.truth_auc.mean|.3f -->0.665<!-- /num --> |
| 정의 사이의 차이(최대−최소) | <!-- num:summary.auc.spread_uniform|.3f -->0.025<!-- /num --> (습관이 다른 세계 <!-- num:summary.auc.spread|.3f -->0.061<!-- /num -->) |

습관이 같으면 정의 사이의 차이가 절반 이하로 줄고, 최선도 d2에서 d3 계열(d3, d6)로 바뀐다. 정의 선택이 중요해지는 정도는 사이트 사이의 습관 차이가 정한다.

## 전조 신호 가정

시뮬레이터는 손상이 클수록 경미한 시정 작업지시와 약한 민원이 늘어난다고 가정한다. d2가 높은 이유가 이 전조를 d2의 라벨이 품고 있기 때문일 수 있어서, 전조의 세기를 0, 0.5, 1배로 바꿔 시드 3개로 다시 돌렸다.

| 전조 세기 | d1 | d2 | d3 | 진짜 라벨 | d2−d1 |
|---|---|---|---|---|---|
| 0배 | <!-- num:summary.robustness.0_0.d1|.3f -->0.605<!-- /num --> | <!-- num:summary.robustness.0_0.d2|.3f -->0.670<!-- /num --> | <!-- num:summary.robustness.0_0.d3|.3f -->0.669<!-- /num --> | <!-- num:summary.robustness.0_0.truth|.3f -->0.684<!-- /num --> | <!-- num:summary.robustness.0_0.d2_minus_d1|.3f -->0.065<!-- /num --> |
| 0.5배 | <!-- num:summary.robustness.0_5.d1|.3f -->0.589<!-- /num --> | <!-- num:summary.robustness.0_5.d2|.3f -->0.652<!-- /num --> | <!-- num:summary.robustness.0_5.d3|.3f -->0.645<!-- /num --> | <!-- num:summary.robustness.0_5.truth|.3f -->0.656<!-- /num --> | <!-- num:summary.robustness.0_5.d2_minus_d1|.3f -->0.063<!-- /num --> |
| 1배(기본) | <!-- num:summary.robustness.1_0.d1|.3f -->0.588<!-- /num --> | <!-- num:summary.robustness.1_0.d2|.3f -->0.643<!-- /num --> | <!-- num:summary.robustness.1_0.d3|.3f -->0.632<!-- /num --> | <!-- num:summary.robustness.1_0.truth|.3f -->0.643<!-- /num --> | <!-- num:summary.robustness.1_0.d2_minus_d1|.3f -->0.055<!-- /num --> |

전조가 없어도 d1이 낮다. d1이 낮은 원인은 긴급 코드를 안 쓰는 사이트에서 라벨이 비는 것이고, 습관이 같은 세계에서 d1의 불리함이 줄어드는 것이 이를 뒷받침한다. 전조가 강할수록 d2와 진짜 라벨 모형의 격차가 줄어든다.

## 라벨 지표와 모형 성능

정의 6개를 시드마다 지표 순위로 매겨 진짜 AUC 순위와의 스피어만 상관을 구했다(창 단위 지표, 시드 5개 평균).

| 지표 | 순위 상관 |
|---|---|
| 정밀도 | <!-- num:summary.validity.precision|.2f -->-0.79<!-- /num --> |
| 재현율 | <!-- num:summary.validity.recall|.2f -->0.78<!-- /num --> |
| F1 | <!-- num:summary.validity.f1|.2f -->-0.39<!-- /num --> |
| F2 | <!-- num:summary.validity.f2|.2f -->0.39<!-- /num --> |
| 양성 비율 | <!-- num:summary.validity.positive_rate|.2f -->0.77<!-- /num --> |

정밀도가 높은 정의일수록 모형이 나빠진다. 이유는 따로 확인하지 않았다. 정밀한 정의는 양성이 적고(창의 4% 안팎, d2는 12%) 습관이 반영된 소수 설비에 몰린 것이 원인일 수 있다. 그래서 정의를 고르는 기준으로 F1을 쓰지 않고 재현율에 무게를 둔 F2를 쓴다. F2의 상관(0.39)도 시드마다 흔들려서 강한 근거는 아니다. 재현율만 기준으로 하면 항상 가장 넓은 정의(d2)를 고르게 된다.

## 현장 확인

사이트마다 설비·주 창을 두 층으로 나눈다. S1은 어느 정의든 고장으로 표시한 창, S0은 아무도 표시하지 않은 창이다. 각 층에서 절반씩 표본을 뽑아 진짜 고장 여부를 확인하고, 층의 크기로 가중해 정의별 정밀도와 재현율을 추정한다. 정의가 표시한 창은 모두 S1 안에 있으므로 맞힌 수는 S1 표본에서, 전체 고장 창 수는 두 층의 표본에서 추정한다. S0을 뽑지 않으면 재현율을 잴 수 없다. 추정값이 정답의 평균과 맞는지는 테스트로 확인한다(`tests/test_eval.py`).

확인 건수를 늘릴 때 선택한 정의가 F2 기준 최선과 0.02 이내인 비율과, 최선을 못 골라서 잃은 점수(후회)다. 사이트 16곳, 확인 표본 150번 반복, 시드 5개 평균이다.

| 확인 건수 | 최선과 0.02 이내 | 잃은 점수 |
|---|---|---|
| 10 | <!-- num:multiseed.base.audit.p_near.0|.0% -->31%<!-- /num --> | <!-- num:multiseed.base.audit.regret.0|.3f -->0.073<!-- /num --> |
| 20 | <!-- num:multiseed.base.audit.p_near.1|.0% -->44%<!-- /num --> | <!-- num:multiseed.base.audit.regret.1|.3f -->0.049<!-- /num --> |
| 40 | <!-- num:multiseed.base.audit.p_near.2|.0% -->55%<!-- /num --> | <!-- num:multiseed.base.audit.regret.2|.3f -->0.035<!-- /num --> |
| 80 | <!-- num:multiseed.base.audit.p_near.3|.0% -->67%<!-- /num --> | <!-- num:multiseed.base.audit.regret.3|.3f -->0.022<!-- /num --> |
| 160 | <!-- num:multiseed.base.audit.p_near.4|.0% -->78%<!-- /num --> | <!-- num:multiseed.base.audit.regret.4|.3f -->0.012<!-- /num --> |
| 320 | <!-- num:multiseed.base.audit.p_near.5|.0% -->88%<!-- /num --> | <!-- num:multiseed.base.audit.regret.5|.3f -->0.006<!-- /num --> |

320건으로도 90%에 닿지 않는다. 사이트 안의 고장 창이 5% 안팎이라 표본에 들어오는 고장이 적은 것이 원인으로 보인다. 잃는 점수는 건수에 따라 꾸준히 줄어든다. 콘솔의 현장 확인 시뮬레이션에서 사이트와 건수를 바꿔 가며 추정, 90% 구간, 정답을 같이 볼 수 있다.

## 고객 맞춤 정의

사이트마다 다른 정의를 써서 라벨을 만들고 하나의 모형을 학습한 뒤, 진짜 고장 AUC로 비교했다(시드 5개 평균).

| 전략 | 진짜 AUC |
|---|---|
| 전 사이트 d1 | <!-- num:summary.customization.fixed_d1|.3f -->0.580<!-- /num --> |
| 전 사이트 d2 | <!-- num:summary.customization.fixed_d2|.3f -->0.638<!-- /num --> |
| 전 사이트 d3 | <!-- num:summary.customization.fixed_d3|.3f -->0.626<!-- /num --> |
| 현장 확인 40건으로 사이트별 선택 | <!-- num:summary.customization.audit_40|.3f -->0.629<!-- /num --> |
| 현장 확인 80건으로 사이트별 선택 | <!-- num:summary.customization.audit_80|.3f -->0.632<!-- /num --> |
| 사이트별 최선(정답으로 고름) | <!-- num:summary.customization.oracle|.3f -->0.638<!-- /num --> |
| 진짜 고장으로 학습 | <!-- num:summary.customization.truth|.3f -->0.644<!-- /num --> |

사이트별 선택은 가장 나쁜 정의(d1)를 피하는 데는 쓸모가 있다. 하지만 정답으로 고른 사이트별 최선도 전 사이트 d2와 같아서, 이 세계에서는 넓은 정의 하나가 최선이다. 사이트별로 정의를 고르는 일이 이익이 되려면 사이트마다 최선이 갈리는 세계여야 하는데, 이 시뮬레이터에서는 그렇지 않았다.

## 라벨이 성숙하는 시간

고장 난 날부터 작업지시가 입력될 때까지의 지연은 늦게 입력하는 사이트에서 중앙값 <!-- num:summary.delay.late_median_days|.0f -->11<!-- /num -->일, 7일 안에 입력되는 비율이 <!-- num:summary.delay.late_within_7|.0% -->32%<!-- /num -->이다. 표준 사이트는 중앙값 <!-- num:summary.delay.standard_median_days|.0f -->2<!-- /num -->일, 7일 안 비율 <!-- num:summary.delay.standard_within_7|.0% -->95%<!-- /num -->다. 하지만 학습 기준 시점에 이미 입력된 기록만 쓴 라벨과 충분히 기다린 라벨로 학습한 모형의 AUC 차이는 <!-- num:summary.maturity.mature_minus_current|.3f -->-0.001<!-- /num -->로 거의 없다. 4주 라벨 창에 비해 지연이 짧아서 라벨 대부분이 이미 채워져 있기 때문으로 보인다.

## 데이터 품질 점검

작업지시 <!-- num:quality.report_without_code_book.total.work_orders|,d -->16,713<!-- /num -->건에서 유형을 읽지 못한 행이 <!-- num:quality.report_without_code_book.total.unknown_type|,d -->2,648<!-- /num -->건이다. 사이트 5와 11이 코드 A1, B2, C3를 쓰기 때문이다. 코드표를 주면 0건이 된다. 이 두 사이트에서 d1(긴급만)로 만든 사건의 진짜 고장 재현율은 코드표 없이 <!-- num:quality.code_book_effect_d1.without.recall|.0% -->0%<!-- /num -->, 코드표가 있으면 <!-- num:quality.code_book_effect_d1.with.recall|.0% -->70%<!-- /num -->이다. 점검 보고서는 긴급 비중이 사이트 중앙값에 비해 지나치게 낮거나 높은 사이트도 표시한다(긴급 안 씀 3곳은 높음, 긴급 남용 3곳은 중간).

## 습관 변화 감시

사이트 4곳이 100주째에 습관을 바꾸는 세계를 시드 5개로 만들었다(변경 20건). 신호 5개(비예방 작업지시 건수, 긴급 비중, 분류 불가 비중, 설비 번호 누락 비중, 작업지시와 이어지는 민원 비중)를 4주 단위로 세고, 앞선 기준 구간(26~78주)과 비교하는 CUSUM으로 경보를 낸다.

| 바뀐 습관 | 탐지 | 중앙값 지연(주) |
|---|---|---|
| 긴급 남용으로 | <!-- num:summary.drift_by_target.abuse.detected|d -->5<!-- /num --> / <!-- num:summary.drift_by_target.abuse.n|d -->5<!-- /num --> | <!-- num:summary.drift_by_target.abuse.delay_median|.0f -->20<!-- /num --> |
| 긴급 안 씀으로 | <!-- num:summary.drift_by_target.no_emergency.detected|d -->3<!-- /num --> / <!-- num:summary.drift_by_target.no_emergency.n|d -->5<!-- /num --> | <!-- num:summary.drift_by_target.no_emergency.delay_median|.0f -->40<!-- /num --> |
| 입력 누락으로 | <!-- num:summary.drift_by_target.missing.detected|d -->2<!-- /num --> / <!-- num:summary.drift_by_target.missing.n|d -->5<!-- /num --> | <!-- num:summary.drift_by_target.missing.delay_median|.0f -->36<!-- /num --> |
| 표준으로(늦게 입력에서) | <!-- num:summary.drift_by_target.standard.detected|d -->1<!-- /num --> / <!-- num:summary.drift_by_target.standard.n|d -->5<!-- /num --> | <!-- num:summary.drift_by_target.standard.delay_median|.0f -->32<!-- /num --> |

- 전체 <!-- num:summary.drift.shifts|d -->20<!-- /num -->건 중 <!-- num:summary.drift.detected|d -->11<!-- /num -->건을 탐지했고 중앙값 <!-- num:summary.drift.delay_median_weeks|.0f -->32<!-- /num -->주, 가장 늦은 것은 <!-- num:summary.drift.delay_max_weeks|d -->44<!-- /num -->주가 걸렸다
- 바뀌지 않은 사이트·실행 <!-- num:summary.drift.quiet_site_runs|d -->140<!-- /num -->건 중 <!-- num:summary.drift.false_alarm_site_runs|d -->3<!-- /num -->건에서 경보가 났다
- 사이트 하나의 고장은 4주에 3건쯤이라 건수가 적다. 변화가 작으면 몇 달이 지나도 신호가 기준 구간의 잡음 안에 있다
- 습관이 바뀐 사이트에서 d1의 F1은 바뀌기 전 <!-- num:summary.drift.d1_f1_before|.2f -->0.66<!-- /num -->에서 바뀐 뒤 <!-- num:summary.drift.d1_f1_after|.2f -->0.48<!-- /num -->로 내려간다. 경보를 늦게 받는 동안 라벨은 이미 나빠져 있다
- 경보는 현장 확인을 다시 하라는 신호이고, 어느 정의가 맞는지는 현장 확인이 판정한다

## 하지 못한 것

- 실제 로그에서의 검증(모든 결과가 합성 세계에서 나옴)
- 사이트별로 최선의 정의가 갈리는 세계에서의 고객 맞춤 정의 비교
- 현장 확인을 실제 사람이 하는 과정의 오류(확인자의 오판)
- 정의 위에 얹는 모형의 개선(특징은 고정하고 라벨만 바꿈)
