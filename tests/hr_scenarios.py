#!/usr/bin/env python3
"""End-to-end HR scenarios over diverse data: statistics + real HR tasks.

Exercises the keyless de-identification mode the way an HR analyst/LLM would:
de-identify → work on the de-identified file (identifiers are tokens, numbers
are raw) → re-identify only the final deliverable. Every scenario asserts BOTH:

  · correctness   — the statistic / HR output matches ground truth
  · safety        — the LLM-visible working artifact contains NO raw identifier

Datasets: employees.csv (250), employees_freetext.csv (250 + free-text 비고),
incident_memo.md (document), and a runtime-generated 80-person company (variety).
Deterministic; writes sample artifacts to claudedocs/hr-demo/. Non-zero exit on
any failure.

Usage:  python3 tests/hr_scenarios.py
"""

import csv
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pii-encryption-gateway", "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(ROOT, "data"))

import deidentify as deid          # noqa: E402
import reidentify as reid          # noqa: E402
import deid_core                   # noqa: E402
from pii_config import classify_identifier  # noqa: E402
import generate_data               # noqa: E402

DATA = os.path.join(ROOT, "data")
DEMO = os.path.join(ROOT, "claudedocs", "hr-demo")
os.makedirs(DEMO, exist_ok=True)
TOKEN_RE = re.compile(r"\[\[[A-Z_]+:[0-9a-f]{8}\]\]")

_passed = 0
_failed = 0


def check(label, ok, detail=""):
    global _passed, _failed
    if ok:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}  -- {detail}")


def won(s):
    d = re.sub(r"[^0-9]", "", str(s))
    return int(d) if d else 0


def load_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def identifier_values(rows):
    vals = set()
    for r in rows:
        for col, v in r.items():
            if classify_identifier(col) and str(v).strip():
                vals.add(str(v).strip())
    return vals


def leaks(text, id_values):
    return [v for v in id_values if v in text]


def de_id(in_path, d, names=()):
    out = os.path.join(d, "deid.json"); mp = os.path.join(d, "map.json")
    _so = sys.stdout; sys.stdout = open(os.devnull, "w")
    deid.deidentify(in_path, out, mp, set(names))
    sys.stdout = _so
    return json.load(open(out, encoding="utf-8")), mp


def reveal(mp, obj, d):
    inp = os.path.join(d, "draft.json"); outp = os.path.join(d, "final.json")
    with open(inp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    _so = sys.stdout; sys.stdout = open(os.devnull, "w")
    reid.reidentify(mp, inp, outp)
    sys.stdout = _so
    return json.load(open(outp, encoding="utf-8"))


# ============================ STATISTICS ============================
def stat_scenarios(d):
    print("\n[A] 통계 시나리오 (de-id 파일에서 직접 계산; 숫자는 raw)")
    raw = load_csv(os.path.join(DATA, "employees.csv"))
    ids = identifier_values(raw)
    deidf, _ = de_id(os.path.join(DATA, "employees.csv"), d)
    blob = json.dumps(deidf, ensure_ascii=False)

    # safety: de-id file holds no raw identifier
    check("통계 입력(de-id)에 식별자 0건", leaks(blob, ids) == [], leaks(blob, ids)[:3])

    # S1 부서별 평균 연봉
    def dept_avg(rows):
        acc = {}
        for r in rows:
            acc.setdefault(r["부서"], []).append(won(r["연봉"]))
        return {k: round(sum(v) / len(v)) for k, v in acc.items()}
    truth1 = dept_avg(raw); got1 = dept_avg(deidf)
    check("S1 부서별 평균 연봉 정확", got1 == truth1, (got1, truth1))

    # S2 직급별 연봉 min/max/mean
    def title_stats(rows):
        acc = {}
        for r in rows:
            acc.setdefault(r["직급"], []).append(won(r["연봉"]))
        return {k: (min(v), max(v), round(sum(v) / len(v))) for k, v in acc.items()}
    check("S2 직급별 연봉 min/max/mean 정확", title_stats(deidf) == title_stats(raw))

    # S3 근태 평균 (지각/결근/연차)
    def att_avg(rows):
        out = {}
        for f in ["지각횟수", "결근일수", "연차사용일수"]:
            out[f] = round(sum(int(r[f]) for r in rows) / len(rows), 2)
        return out
    check("S3 근태 평균 정확", att_avg(deidf) == att_avg(raw), att_avg(deidf))

    # S4 부서 인원수 (no PII at all)
    def headcount(rows):
        c = {}
        for r in rows:
            c[r["부서"]] = c.get(r["부서"], 0) + 1
        return c
    check("S4 부서 인원수 정확", headcount(deidf) == headcount(raw))

    # artifact: dept salary stats report (PII-free)
    lines = ["# 부서별 연봉·인원 통계 (개인정보 미포함)\n",
             "| 부서 | 인원 | 평균 연봉(만원) |", "|---|---|---|"]
    hc = headcount(deidf)
    for dept in sorted(got1, key=lambda k: -got1[k]):
        lines.append(f"| {dept} | {hc[dept]} | {got1[dept]:,} |")
    lines.append(f"\n> 전사 {len(deidf)}명 · 평균 연봉 {round(sum(won(r['연봉']) for r in deidf)/len(deidf)):,}만원")
    lines.append("> de-id 파일에서 직접 산출 — 이름·주민·계좌는 토큰이라 미포함")
    open(os.path.join(DEMO, "salary_stats_by_dept.md"), "w", encoding="utf-8").write("\n".join(lines))


# ============================ HR TASKS ============================
def hr_task_scenarios(d):
    print("\n[B] 실제 HR 업무 시나리오 (de-id → 토큰으로 작업 → 최종본만 재식별)")
    raw = load_csv(os.path.join(DATA, "employees.csv"))
    ids = identifier_values(raw)
    deidf, mp = de_id(os.path.join(DATA, "employees.csv"), d)
    by_emp_token = {r["사번"]: r for r in deidf}  # keyed by EMPNO token

    # T1 연봉 인상 안내 메일 (E0007)
    e7_token = deid_core.token("EMPNO", "E0007")
    row = by_emp_token[e7_token]
    draft = (f"받는사람: {row['이름']}\n\n안녕하세요, {row['이름']}님.\n"
             f"2026년 확정 연봉은 {row['연봉']} 입니다.\n- 인사팀")
    check("T1 draft(작업본)에 식별자 0건", leaks(draft, ids) == [], leaks(draft, ids))
    final = reveal(mp, {"t": draft}, d)["t"]
    raw7 = next(r for r in raw if r["사번"] == "E0007")
    check("T1 최종본에 실제 이름·연봉", raw7["이름"] in final and raw7["연봉"] in final,
          (raw7["이름"], raw7["연봉"]))
    open(os.path.join(DEMO, "salary_notice_E0007.txt"), "w", encoding="utf-8").write(
        "=== 작업본 (LLM이 보는 것, 토큰) ===\n" + draft +
        "\n\n=== 최종본 (담당자에게만, 재식별) ===\n" + final + "\n")

    # T2 영업팀 근태 통지문
    sales = [r for r in deidf if r["부서"] == "영업팀"]
    notices = "\n---\n".join(
        f"{r['이름']}님 분기 근태: 지각 {r['지각횟수']}회, 결근 {r['결근일수']}일, 연차 {r['연차사용일수']}일"
        for r in sales)
    check("T2 영업팀 통지 draft 식별자 0건", leaks(notices, ids) == [])
    final2 = reveal(mp, {"t": notices}, d)["t"]
    sales_names = {r["이름"] for r in raw if r["부서"] == "영업팀"}
    check("T2 최종본에 영업팀 전원 이름", all(n in final2 for n in sales_names),
          f"team={len(sales_names)}")

    # T3 개발팀 상여금 입금 안내 (이름+계좌)
    dev = [r for r in deidf if r["부서"] == "개발팀"]
    msgs = "\n".join(f"{r['이름']}님 상여금을 계좌 {r['계좌번호']}(으)로 입금 예정입니다." for r in dev)
    check("T3 상여금 draft 식별자 0건", leaks(msgs, ids) == [])
    final3 = reveal(mp, {"t": msgs}, d)["t"]
    dev_raw = [r for r in raw if r["부서"] == "개발팀"]
    check("T3 최종본에 개발팀 이름+계좌",
          all(r["이름"] in final3 and r["계좌번호"] in final3 for r in dev_raw),
          f"team={len(dev_raw)}")

    # T4 평균 미달 연봉자 식별 + 면담 안내 (통계 + 개인별 결합)
    avg = sum(won(r["연봉"]) for r in deidf) / len(deidf)
    below = [r for r in deidf if won(r["연봉"]) < avg]
    meeting = "\n".join(f"{r['이름']}님(연봉 {r['연봉']}) 면담 대상" for r in below)
    check("T4 면담 draft 식별자 0건", leaks(meeting, ids) == [])
    final4 = reveal(mp, {"t": meeting}, d)["t"]
    truth_below = {r["이름"] for r in raw if won(r["연봉"]) < avg}
    got_below = {ln.split("님")[0] for ln in final4.splitlines()}
    check("T4 평균 미달자 집합 정확", got_below == truth_below,
          f"got={len(got_below)} truth={len(truth_below)}")
    open(os.path.join(DEMO, "below_avg_meeting.txt"), "w", encoding="utf-8").write(
        f"전사 평균 연봉 {round(avg):,}만원 미만 {len(below)}명 면담 안내\n\n"
        "=== 작업본(토큰) 일부 ===\n" + "\n".join(meeting.splitlines()[:3]) +
        "\n\n=== 최종본(재식별) 일부 ===\n" + "\n".join(final4.splitlines()[:3]) + "\n")

    # T5 문서: incident_memo.md (명부 밖 인명은 --names로)
    memo_names = ["한지수"]
    deid_doc_out = os.path.join(d, "memo_deid.md"); memo_map = os.path.join(d, "memo_map.json")
    _so = sys.stdout; sys.stdout = open(os.devnull, "w")
    deid.deidentify(os.path.join(DATA, "incident_memo.md"), deid_doc_out, memo_map, set(memo_names))
    sys.stdout = _so
    memo_deid = open(deid_doc_out, encoding="utf-8").read()
    for v in ["880712-2345671", "010-7788-1234", "jisoo.han@partner.example.com",
              "국민 123-4567-890123", "한지수"]:
        check(f"T5 문서 식별자 봉인: {v[:12]}", v not in memo_deid)
    check("T5 문서 본문(비식별자 텍스트) 보존", "영업팀" in memo_deid and "비정상 접속" in memo_deid)
    restored_doc = reveal(memo_map, {"t": memo_deid}, d)["t"]
    check("T5 문서 재식별 복원", "한지수" in restored_doc and "010-7788-1234" in restored_doc)


# ===================== DATA DIVERSITY =====================
def diversity_scenarios(d):
    print("\n[C] 데이터 다양성 (다른 규모/스키마)")
    # D1: a different 80-person company (runtime-generated, seed 7)
    rows = generate_data.generate(80, seed=7)
    p = os.path.join(d, "company2.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    ids = identifier_values(rows)
    deidf, _ = de_id(p, d)
    blob = json.dumps(deidf, ensure_ascii=False)
    check("D1(80명) 식별자 0건", leaks(blob, ids) == [], leaks(blob, ids)[:3])
    avg_raw = round(sum(won(r["연봉"]) for r in rows) / len(rows))
    avg_did = round(sum(won(r["연봉"]) for r in deidf) / len(deidf))
    check("D1(80명) 평균 연봉 계산 정확", avg_did == avg_raw, (avg_did, avg_raw))

    # D2: free-text 비고 column with embedded phone/RRN (employees_freetext.csv)
    ft_path = os.path.join(DATA, "employees_freetext.csv")
    if os.path.exists(ft_path):
        ftraw = load_csv(ft_path)
        ftids = identifier_values(ftraw)
        # embedded phone/RRN from row 0's own values
        embedded = [ftraw[0]["전화번호"], ftraw[0]["주민등록번호"]]
        ftdeid, _ = de_id(ft_path, d)
        ftblob = json.dumps(ftdeid, ensure_ascii=False)
        check("D2 비고(자유텍스트) 매립 식별자 봉인",
              all(e not in ftblob for e in embedded), embedded)
        check("D2 연봉 raw 유지(평균 가능)",
              round(sum(won(r["연봉"]) for r in ftdeid) / len(ftdeid)) ==
              round(sum(won(r["연봉"]) for r in ftraw) / len(ftraw)))


def run():
    with tempfile.TemporaryDirectory() as d:
        stat_scenarios(d)
        hr_task_scenarios(d)
        diversity_scenarios(d)
    print(f"\n{_passed} passed, {_failed} failed   (artifacts in claudedocs/hr-demo/)")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
