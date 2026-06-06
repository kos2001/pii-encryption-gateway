# NER 연동 검토 — 산문 속 인명 탐지

작성: 2026-06-06 · 대상: `pii-encryption-gateway` skill

## 질문

현재 게이트웨이는 패턴 있는 PII(주민번호·전화·이메일·계좌·카드)를 컬럼명·컬럼형태·값형태 3단으로 잡지만, **산문 속 인명**은 못 잡는다(정규식 패턴이 없음). NER을 *선택적으로* 연동해 이를 보완할 수 있는가?

## 결론 요약

- **stdlib 휴리스틱 NER(성씨 gazetteer)은 폐기 권고** — 측정상 사용 불가(아래 수치).
- **권고 경로는 deny-list 기반 정밀 인명 치환(Tier 0, stdlib)** — HR 시나리오에서 인명은 *미지의 값이 아니라 명부에 이미 있는 값*이라는 점을 활용. 무의존성·오탐 0.
- **개방형(미지의 임의 인명) NER이 꼭 필요하면 Tier 1로 선택적 spaCy/Presidio 연동** — 단, 무거운 의존성·중간 정확도·게이트 임포트 비용을 감수. 기본 비활성.

## 제약: NER은 반드시 로컬이어야 한다

이 skill의 핵심 보증은 "모델이 원문 민감값을 절대 보지 않는다"이다. **클라우드 NER API에 원문을 보내면 그 자체가 누출**이다(LLM에 보내는 것과 동일한 노출). 따라서 NER은 로컬 실행만 허용된다 → 클라우드 API 옵션은 원천 배제. 로컬 NER = 모델 의존성(무게).

또한 `crypto_core.py`가 명시한 설계 불변식은 **표준 라이브러리만, 무의존성, 어떤 Python 3.8+ 환경에도 이식**이다. 로컬 NER은 이 불변식과 정면 충돌한다.

## Presidio의 실제 NER 방식 (사실관계)

- Presidio는 `NlpEngine` 추상화로 NER을 수행: spaCy(기본 `en_core_web_lg`) / Stanza / transformers.
- 다국어는 해당 언어 모델을 내려받아 설정해야 함. 한국어는 1급 문서 예시에 없음.
- 한국어 spaCy 모델 `ko_core_news_lg`는 존재하며 `ner` 컴포넌트 포함. 단 한국어 NER 정확도 이슈가 공개 트래커에 보고됨(조사 처리 등). 즉 "있지만 완벽하지 않음".
- 출처: [Customizing NLP models](https://microsoft.github.io/presidio/analyzer/customizing_nlp_models/), [Multi-language](https://microsoft.github.io/presidio/analyzer/languages/), [Transformers engine](https://microsoft.github.io/presidio/analyzer/nlp_engines/transformers/), [spaCy ko_core_news_lg](https://huggingface.co/spacy/ko_core_news_lg), [Korean NER accuracy issue #13705](https://github.com/explosion/spaCy/issues/13705)

## 측정: stdlib 성씨-gazetteer 휴리스틱 (PoC)

성씨 약 100개 gazetteer + "성씨 + 1~2 한글 음절" 토큰 패턴. 합성 명부 이름 20개를 산문에 넣고, 성씨-동음 일반 단어가 든 평범한 문장 15개로 오탐 측정.

| 변형 | 재현율(이름+직함) | 재현율(이름+조사) | 오탐(문장 15개) |
|---|---|---|---|
| V1: 성씨+1~2음절(토큰경계) | 20/20 (100%) | 0/20 (0%) | **15/15** (정보·최대·조직·고객·성과·강조…) |
| V2: V1 + 직함/조사 문맥 게이트 | 20/20 (100%) | 0/20 (0%) | 0/15 |

**해석**: 규칙 기반이 한국어에서 근본적으로 실패하는 두 원인 —
1. **교착어**: 이름+조사가 띄어쓰기 없이 붙어("장지민이") 토큰 경계가 무너짐 → 맨이름 재현율 0%, 경계 오정렬.
2. **성씨=일반어 첫음절 동형**: 정(정보), 최(최대), 조(조직), 고(고객), 성(성과)… → 정밀도 붕괴.
정밀도(V2)와 재현율은 양립 불가. 제대로 하려면 형태소 분석 + 학습된 문맥 = 통계 모델이 필요하다.

## 옵션 비교

| | Tier 0: deny-list 치환 | Tier 1: 선택적 spaCy/Presidio | (폐기) stdlib 휴리스틱 |
|---|---|---|---|
| 의존성 | 없음(stdlib) | 무거움(spaCy+모델 수백 MB, 또는 transformers+torch) | 없음 |
| 누출 위험 | 없음(로컬 정확매칭) | 없음(로컬 추론) | 없음 |
| 정밀도 | 100%(정확매칭) | 중간(한국어 NER 한계) | 사용 불가 |
| 재현율 | 명부에 있는 이름 한정 | 개방형(미지 이름 포함) | — |
| 콜드스타트 | 즉시 | 느림(모델 로드) | 즉시 |
| 무의존성 불변식 | 유지 | **위반**(선택적 임포트로 격리) | 유지 |

## 권고

### Tier 0 (권장, 즉시 구현 가치 있음): deny-list 인명 치환

핵심 통찰: **HR 맥락에서 인명은 미지의 값이 아니다.** 담당자는 이미 직원 명부(`employees.csv`의 `이름` 컬럼)를 쥐고 있다. 따라서 문서에서 redact할 이름 집합은 *알려져 있다*. 알려진 이름을 문서에서 정확 문자열 매칭으로 토큰화하면:
- 오탐 0(정확매칭), 무의존성, 결정론적 토큰(기존 `make_token`/`tokenize_value.py`와 동일 메커니즘) → `reveal.py` 그대로 역변환.
- Presidio로 치면 `PatternRecognizer(deny_list=...)`에 해당.

설계 스케치: `protect.py` 문서 모드에 `--names <name1,name2,...>` 또는 `--names-from <roster.csv>` 옵션 추가 → 그 이름들을 `[[NAME:hash]]`로 치환(가장 긴 것부터, 조사 경계 무관 정확매칭). recognizer 패스와 독립적으로 동작.

한계: 명부에 없는 제3자(외부 인물) 이름은 못 잡음 → 그 경우만 Tier 1 필요.

### Tier 1 (선택, 기본 비활성): 게이트된 spaCy/Presidio

개방형 인명까지 필요할 때만. `try: import presidio_analyzer / spacy` 로 격리하고, 미설치 시 현행 동작(인명 미탐) 그대로 + 안내 메시지. 설치 시 `ko_core_news_lg`로 PERSON 엔티티를 recognizer 결과에 합류. SKILL.md에 "정확도 한계·의존성·로컬 전용" 명시.

이 경로의 비용: 수백 MB 모델, 느린 콜드스타트, 한국어 NER 중간 정확도, 그리고 무의존성이라는 skill의 정체성 약화. 그래서 **기본 비활성·명시적 opt-in**이 전제.

## 진행 상태

1. **Tier 0 구현 완료** ✅ — `recognizers.find_names()`(deny-list 정확매칭) + `protect.py`의 `--names-from <roster>` / `--names "a,b"` 옵션. 문서·자유텍스트 패스에서 알려진 인명을 `[[NAME:…]]`로 봉인, `reveal.py` 무수정 역변환. 무의존성 유지, 오탐 0. 테스트: `test_denylist_names.py`(7), `test_protect_names.py`(9). SKILL.md에 사용법·한계(명부 외 제3자 미탐) 명시.
2. **Tier 1(선택적 spaCy/Presidio)은 미착수** — 개방형(명부 외) 인명 요구가 실제로 제기될 때 별도 PR. 그 전까지 SKILL.md의 "공급된 이름만 봉인" 한계 문구 유지.
