#!/usr/bin/env python3
"""Generate synthetic Korean HR data (연봉/근태 등 민감정보 포함).

Fully synthetic and deterministic (fixed seed) so evals are reproducible. No
real person's data is used. Produces both CSV and JSON.

Usage:
    python generate_data.py --count 40 --out-dir .
"""

import argparse
import csv
import json
import os
import random

SURNAMES = list("김이박최정강조윤장임한오서신권황안송류전")
GIVEN = ["민준", "서연", "지우", "도윤", "예은", "하준", "지호", "수아", "지민", "현우",
         "은서", "준서", "유진", "지안", "시우", "하은", "건우", "윤서", "정우", "다은",
         "성민", "예진", "재윤", "서준", "지율", "민서", "태현", "수빈", "동현", "혜원"]
DEPARTMENTS = ["인사팀", "영업팀", "개발팀", "마케팅팀", "재무팀", "고객지원팀"]
TITLES = ["사원", "대리", "과장", "차장", "부장"]
BANKS = ["국민", "신한", "우리", "하나", "농협"]


def _rrn(rng):
    yy = rng.randint(70, 99)
    mm = rng.randint(1, 12)
    dd = rng.randint(1, 28)
    gender = rng.choice([1, 2])
    tail = rng.randint(100000, 999999)
    return f"{yy:02d}{mm:02d}{dd:02d}-{gender}{tail}"


def generate(count, seed=42):
    rng = random.Random(seed)
    rows = []
    used_names = set()
    for i in range(1, count + 1):
        while True:
            name = rng.choice(SURNAMES) + rng.choice(GIVEN)
            if name not in used_names:
                used_names.add(name)
                break
        title = rng.choice(TITLES)
        base = {"사원": 3200, "대리": 4200, "과장": 5500, "차장": 7000, "부장": 9000}[title]
        salary = base + rng.randint(-400, 600)  # 만원
        rows.append({
            "사번": f"E{i:04d}",
            "이름": name,
            "주민등록번호": _rrn(rng),
            "부서": rng.choice(DEPARTMENTS),
            "직급": title,
            "입사일": f"20{rng.randint(10, 23):02d}-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}",
            "연봉": f"{salary}만원",
            "지각횟수": rng.randint(0, 8),
            "결근일수": rng.randint(0, 4),
            "연차사용일수": rng.randint(0, 15),
            "전화번호": f"010-{rng.randint(1000,9999)}-{rng.randint(1000,9999)}",
            "이메일": f"user{i:04d}@company.co.kr",
            "계좌번호": f"{rng.choice(BANKS)} {rng.randint(100,999)}-{rng.randint(1000,9999)}-{rng.randint(100000,999999)}",
        })
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=40)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out-dir", default=os.path.dirname(os.path.abspath(__file__)))
    args = p.parse_args()

    rows = generate(args.count, args.seed)
    csv_path = os.path.join(args.out_dir, "employees.csv")
    json_path = os.path.join(args.out_dir, "employees.json")

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"Generated {len(rows)} synthetic employees -> {csv_path}, {json_path}")


if __name__ == "__main__":
    main()
