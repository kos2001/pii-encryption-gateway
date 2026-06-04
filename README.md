# private_protection

민감 개인정보(사번·연봉·근태·주민등록번호·계좌 등)를 **LLM에 노출하지 않고** 처리하기 위한
스킬과 그 성능을 검증하는 합성 데이터 / 평가 하니스.

## 구성

```
skills/pii-encryption-gateway/   # 스킬 본체
  SKILL.md                       #   동작 규율 (원본 파일을 읽지 않는다)
  scripts/
    crypto_core.py               #   표준 라이브러리만으로 KDF + AEAD + 결정론적 토큰
    protect.py                   #   민감 필드 → 토큰, 원본은 키로 암호화해 vault에
    reveal.py                    #   담당자 키로 토큰 → 원본 복원 (틀린 키는 실패)
    tokenize_value.py            #   알고 있는 값(예: 사번)의 토큰 계산 — 원본 안 읽고 레코드 조회
    pii_config.py                #   어떤 컬럼이 민감한지 정의 (사번 포함)
  evals/evals.json               #   4개 평가 케이스
data/
  generate_data.py               # 한국식 HR 합성 데이터 생성 (seed 고정, 40명)
  employees.csv / .json          # 생성된 합성 데이터 (실제 인물 아님)
tests/grade_eval.py              # 누출/정확도 자동 채점기
skills/pii-encryption-gateway-workspace/   # iteration-1, iteration-2 평가 결과
```

## 동작 원리

담당자마다 고유 키를 가진다. `protect.py` 가 민감 값을 결정론적 토큰
(`[[SALARY:3f9a2c1d]]`)으로 치환하고 원본은 그 키로 암호화해 vault에 넣는다.
LLM은 토큰만 보고 작업(안내문 작성·통지·리포트 등)을 수행한다. 작업이 끝나면
`reveal.py` 가 같은 키로 토큰을 원본으로 복원해 **인가된 담당자에게만** 보여준다.
키가 틀리면 복호화가 실패하므로 노출이 일어나지 않는다.

토큰은 결정론적이라 같은 값 → 같은 토큰이며, 모델은 동일인/그룹 관계는 추론할 수
있되 실제 값은 알 수 없다.

## 사용 예

```sh
# 1) 보호 (원본 → 토큰 + 암호화 vault)
python3 skills/pii-encryption-gateway/scripts/protect.py \
  --key "handler-hr-alice-key-001" --in data/employees.csv \
  --out protected.json --vault vault.json

# 2) LLM 이 protected.json(토큰)으로 작업, 결과를 토큰 그대로 저장 (draft.txt)

# 3) 복원 (담당자 키로 토큰 → 원본)
python3 skills/pii-encryption-gateway/scripts/reveal.py \
  --key "handler-hr-alice-key-001" --vault vault.json \
  --in draft.txt --out final.txt
```

## 한계 (정직한 트레이드오프)

- 토큰화된 민감 수치로는 **산술 연산이 불가**하다(평균 연봉 등). 집계가 필요하면
  원본을 대상으로 스크립트로 계산해 집계값만 모델에 넘긴다.
- protect/reveal 단계 때문에 직접 처리보다 시간·토큰 오버헤드가 있다(벤치마크 기준
  약 +32초 / +11.5k 토큰).
- 토큰이 **결정론적**이라 같은 값 → 같은 토큰이다. 그룹핑이 가능한 대신, 보호된
  데이터만 봐도 *어떤 레코드가 같은 값을 갖는지*(동일성·빈도)는 드러난다. 값 자체는
  키 없이 복원 불가하지만, 근태(0~15)처럼 값 범위가 좁은 필드는 빈도 패턴이 단서가
  될 수 있다. 동일성까지 숨겨야 하면 그 필드는 랜덤 토큰을 써야 하고, 대신 그룹핑
  능력을 잃는다.

## 평가 결과

**(1) 행동 평가** — skill-creator eval 루프로 with-skill vs baseline(스킬 없음) 비교.

| | 데이터 | with-skill | baseline | 시간 Δ | 토큰 Δ |
|---|---|---|---|---|---|
| iteration-1 (3 evals) | 40명 | 100% | 50% | — | — |
| iteration-2 (4 evals) | 40명 | 100% | 62.5% | +32s | +11.5k |
| iteration-3 (4 evals) | 250명 | 100% | 62.5% | +28s | **−13.3k** |
| iteration-4 (4 evals, 사번도 민감) | 250명 | 100% | 62.5% | +18s | **−13.4k** |

개인별 민감 값이 필요한 작업(연봉 안내, 근태 통지, 상여금 입금 안내)에서 baseline은
매번 실제 이름·연봉·계좌가 모델 컨텍스트에 노출됐고, 게이트웨이는 누출 0을 유지했다.
부서별 집계 리포트처럼 PII가 애초에 필요 없는 작업은 양쪽 모두 통과(비변별).
**규모가 커지면(250명) 게이트웨이가 더 안전할 뿐 아니라 토큰도 더 적게 쓴다** —
baseline은 250행 PII 전체를 컨텍스트로 읽어들여 토큰이 폭증하기 때문.

**(2) 스트레스 테스트** — `tests/stress_test.py`, 250명 전수 + 적대적 엣지케이스
(중복 이름, 빈 값, 쉼표/유니코드/이모지/줄바꿈/0/초대형 값, 토큰 위장 입력, 교차 핸들러 키).
**14/14 통과** (protect 250행 0.16초). 검증 속성: 누출 0 / 왕복 정확 / 틀린키 실패 /
교차핸들러 토큰 상이 / 결정성 / 토큰 포맷 / reveal 무잔여.

재현: `python3 data/generate_data.py --count 250` → `python3 tests/stress_test.py`.
행동 평가 채점은 `tests/grade_eval.py`. 평가 뷰어는 Python 3.10+ 필요(`/opt/homebrew/bin/python3.11`).
