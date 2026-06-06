# private_protection

민감 개인정보(사번·연봉·근태·주민등록번호·계좌·전화·이메일·카드·사업자번호·IP 등)를
**LLM에 노출하지 않고** 처리하기 위한 스킬과, 그 성능을 검증하는 합성 데이터 / 평가 하니스.

## 구성

```
skills/pii-encryption-gateway/   # 스킬 본체
  SKILL.md                       #   동작 규율 (원본 파일을 읽지 않는다)
  scripts/
    deidentify.py                #   [기본] 식별자→토큰, 숫자는 원본 유지(집계 가능), 평문 매핑(키 없음)
    reidentify.py                #   평문 매핑으로 식별자 복원
    deid_core.py                 #   키 없는 결정론적 토큰 (암호화·키 없음)
    protect.py                   #   [보조] 키 게이트웨이: 모든 값 토큰화 + 암호화 vault
    reveal.py                    #   담당자 키로 vault→원본 복원 (틀린 키는 실패)
    tokenize_value.py            #   알고 있는 값(예: 사번)의 토큰 계산 — 키 모드 레코드 조회
    crypto_core.py               #   표준 라이브러리만으로 KDF + AEAD + 키 기반 토큰
    pii_config.py                #   민감 필드 + 직접 식별자 구분 정의
    recognizers.py               #   값 형태 PII 탐지 · 컬럼 추론 · deny-list 인명 (자유텍스트/문서)
  evals/evals.json               #   6개 행동 평가 케이스 (문서 모드·자유텍스트 누출 포함)
data/
  generate_data.py               # 한국식 HR 합성 데이터 생성 (seed 고정; --freetext 변형)
  employees.csv / .json          # 생성된 합성 데이터 (실제 인물 아님)
  employees_freetext.csv         # 자유서술 '비고' 칼럼에 PII 매립 (누출 평가용)
  incident_memo.md               # 문서 모드 평가용 합성 메모
tests/                           # 결정적 테스트 스위트 (LLM 불필요) + 채점기
  stress_test.py                 #   보안 불변식 14개 (250명 전수 + 적대적 엣지)
  test_recognizers*.py           #   값 형태 탐지: 기본/적대적 포맷/IP/유니코드
  test_protect_*.py              #   protect 통합: 자유텍스트/컬럼추론/문서/인명/퍼지/스케일
  test_column_inference.py       #   값 샘플링 컬럼 분류
  test_denylist_names.py         #   deny-list 인명 정확매칭
  test_deid*.py                  #   keyless de-id: 코어/통합(식별자 토큰·숫자 raw·평균)
  deid_eval.py                   #   3-way 검증: 누출 vs 평균 계산 (baseline/키/de-id)
  leakage_eval.py                #   누출 before/after 정량 (컬럼 전용 vs +recognizer)
  grade_eval.py                  #   행동 평가 자동 채점기
skills/pii-encryption-gateway-workspace/   # iteration-1~5 평가 결과 + 비교
```

## 동작 원리

**기본은 keyless 비식별화(de-identification)다.** `deidentify.py` 가 **직접 식별자**
(이름·주민번호·사번·계좌·전화·이메일 등)만 결정론적 토큰(`[[NAME:3f9a2c1d]]`)으로
치환하고, **숫자 속성(연봉·근태)은 원본 그대로 둔다.** 그래서 LLM은 *누구의* 값인지는
모른 채 숫자만 보고 **평균·합계·분포 같은 집계·통계를 직접 계산**할 수 있다. 원본↔토큰
대응은 **평문 매핑**(`map.json`)에 저장되고, 작업 끝에 `reidentify.py` 가 식별자를
복원한다. 키·암호화는 없다.

**at-rest 암호화와 키 기반 접근통제**가 추가로 필요하면 더 강한 **키 게이트웨이**
(`protect.py`/`reveal.py`)를 쓴다. 이건 식별자뿐 아니라 **숫자까지 모든 값**을 토큰화해
키로 암호화한 vault에 넣고, 인가된 키로만 복원한다(틀린 키는 실패). 대신 숫자가 봉인되어
**집계는 불가**하다 — 통계는 원본 대상 스크립트로 따로 계산한다.

토큰은 두 모드 모두 결정론적이라 같은 값 → 같은 토큰이며, 모델은 동일인/그룹 관계는
추론할 수 있되 실제 식별자 값은 알 수 없다.

### 무엇을, 어떻게 찾는가 (Microsoft Presidio 아키텍처를 stdlib로 이식)

민감 값은 **네 가지 경로**로 잡혀 어디에 있든 보호된다:

1. **컬럼명** — `pii_config.py` 의 별칭 매칭 (정형 CSV/JSON 컬럼).
2. **컬럼 형태** — 이름이 안 맞는 컬럼도 값을 샘플링해 단일 PII 엔티티면 컬럼 단위로
   분류. 다수에서 일반화하므로 개별 off-format 셀까지 봉인.
3. **값 형태** — 문장 속에 박힌 PII를 span 단위로 탐지: 주민등록번호(대시/무대시),
   전화(모바일·유선·+82, `-`/`.`/공백 구분자), 이메일, 계좌, 카드, 사업자등록번호,
   IPv4. 전각 숫자(`０１０…`)도 길이 보존 fold로 인식.
4. **deny-list 인명** — 패턴 없는 인명은 담당자가 가진 명부의 이름을 정확매칭으로 봉인
   (`--names-from`). 명부 밖 제3자 인명은 탐지 못 함(정직한 한계).

검증기는 Presidio 방식: **RRN은 fail-safe**(체크섬은 신뢰도만 가산, 형식만 맞아도 봉인 —
실/합성 덤프가 체크섬을 자주 실패하므로), **카드(Luhn)·사업자번호(체크섬)는 게이팅**
(실패 시 제외 — ISBN 등 오탐이 흔하고 실값은 통과). 구조적 CSV뿐 아니라 `.txt`/`.md`
**문서**(메모·이메일 초안·인시던트 리포트)도 같은 방식으로 처리한다.

## 사용 예

기본 — 비식별화(집계·통계 가능):

```sh
# 1) 비식별화 (식별자→토큰, 숫자는 원본 유지, 평문 매핑)
python3 skills/pii-encryption-gateway/scripts/deidentify.py \
  --in data/employees.csv --out deidentified.json --map map.json \
  --names-from data/employees.csv      # .md/.txt 문서도 동일하게 지원

# 2) LLM 이 deidentified.json 으로 작업 — 부서별 평균 연봉 등 집계를 직접 계산
#    (이름·주민·계좌는 토큰, 연봉·근태는 raw)

# 3) 출력에 식별자 토큰이 있으면 복원 (순수 집계 리포트면 생략)
python3 skills/pii-encryption-gateway/scripts/reidentify.py \
  --map map.json --in draft.json --out final.json
```

보조 — 키 게이트웨이(개인별 + at-rest 암호화가 필요할 때):

```sh
python3 skills/pii-encryption-gateway/scripts/protect.py \
  --key "handler-hr-alice-key-001" --in data/employees.csv \
  --out protected.json --vault vault.json
# ... 토큰으로 작업 후 ...
python3 skills/pii-encryption-gateway/scripts/reveal.py \
  --key "handler-hr-alice-key-001" --vault vault.json --in draft.txt --out final.txt
```

## 한계 (정직한 트레이드오프)

- **비식별화(기본 모드)는 숫자 값 자체를 (이름과 분리해) 노출**한다. 이게 집계를
  가능케 하는 핵심이지만, de-linked 숫자조차 모델에 보이면 안 되는 경우엔 원본 대상
  스크립트로 집계해 결과값만 넘긴다. **키 게이트웨이는 숫자까지 봉인**되어 집계 불가.
- 비식별화의 복원 매핑(`map.json`)은 **평문**(키·암호화 없음)이라 원본만큼 민감하다 —
  원본 파일처럼 보관해야 한다. 키 게이트웨이의 vault 는 대신 암호화된다.
- 토큰이 **결정론적**이라 같은 값 → 같은 토큰이다. 그룹핑이 가능한 대신, 보호된
  데이터만 봐도 *어떤 레코드가 같은 값을 갖는지*(동일성·빈도)는 드러난다.
- **산문 속 인명**은 값 형태가 없어 recognizer로 못 잡는다. 명부 기반 deny-list로
  메우되, 명부 밖 인명은 별도 NER(선택적·미구현)이 필요하다.
  근거·대안 분석: `claudedocs/ner-integration-review.md`.

## 평가 결과

**(1) 행동 평가** — skill-creator eval 루프로 with-skill vs baseline(스킬 없음) 비교.

| | 데이터 | with-skill | baseline | 시간 Δ | 토큰 Δ |
|---|---|---|---|---|---|
| iteration-1 (3 evals) | 40명 | 100% | 50% | — | — |
| iteration-2 (4 evals) | 40명 | 100% | 62.5% | +32s | +11.5k |
| iteration-3 (4 evals) | 250명 | 100% | 62.5% | +28s | **−13.3k** |
| iteration-4 (4 evals, 사번도 민감) | 250명 | 100% | 62.5% | +18s | **−13.4k** |
| iteration-5 (4 evals, 기능 확장 후) | 250명 | 100% | 62.5% | +30s | **−10.6k** |

개인별 민감 값이 필요한 작업(연봉 안내·근태 통지·상여금 입금)에서 baseline은 매번 실제
이름·연봉·계좌를 모델 컨텍스트에 노출했고, 게이트웨이는 누출 0을 유지했다. 부서별 집계
리포트처럼 PII가 애초에 필요 없는 작업은 양쪽 모두 통과(비변별). **규모가 커지면(250명)
게이트웨이가 더 안전할 뿐 아니라 토큰도 더 적게 쓴다.** iteration-5는 이번 확장(다층 탐지·
문서 모드·deny-list·확장 엔티티·유니코드) 이후에도 합격률·토큰이 회귀 없음을 확인한다.
교차 비교: `skills/pii-encryption-gateway-workspace/iteration-comparison.md`.

**(2) 결정적 테스트 스위트** — `tests/` (LLM 불필요, 18개 파일):

- `stress_test.py` — 보안 불변식 14/14 (250명 전수 + 적대적 엣지: 중복·빈값·유니코드·
  이모지·줄바꿈·토큰 위장·교차 핸들러 키). protect 250행 0.16초.
- 값 형태 탐지 — 기본(15) · 적대적 포맷(21) · IP(6) · 유니코드 전각(9).
- protect 통합 — 자유텍스트(13) · 컬럼추론(7) · 문서(15) · 인명(9).
- **keyless de-id** — 코어(7) · 통합(20, 식별자 토큰·숫자 raw·평균 직접 계산·매핑 복원).
- **퍼지(속성 기반)** — 무작위 문서 3,200개(4시드)에서 누출 0 / 왕복 정확.
- **스케일·멱등성** — 175KB/3,000건 protect+reveal ~1.3초 / 재보호 no-op.
- `leakage_eval.py` — 자유텍스트·미명명 컬럼 PII recall **0% → 100%**, off-format 셀
  **80% → 100%** (컬럼 전용 vs +recognizer/컬럼추론).
- `deid_eval.py` — 집계 과제 3-way 검증: **baseline**(평균 O, 식별자 1500건 누출) ·
  **키 게이트웨이**(누출 0, 평균 X) · **keyless de-id**(누출 0 + 평균 정확 ✓ = 목표 달성).

**(3) 트리거링 정확도** — 스킬 호출 description을 30쿼리 세트로 평가(문서 모드 positive +
까다로운 near-miss), 독립 분류기 3개 다수결 **30/30**(proxy). 기록: 워크스페이스의
`trigger_eval_v2_results.md`.

재현: `python3 data/generate_data.py --count 250 --freetext` → `python3 tests/stress_test.py`.
행동 평가 채점은 `tests/grade_eval.py`. 평가 뷰어는 Python 3.10+ 필요.
