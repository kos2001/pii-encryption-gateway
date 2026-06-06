#!/usr/bin/env python3
"""HR-facing explainer deck for the PII Encryption Gateway skill.

DS official template format: BLACK header band on a WHITE background (the
default in-use style), dark ink body text, light-gray cards, restrained
Samsung-blue accent, status colors only where semantic. 16:9, Korean-friendly
typography. Re-run to regenerate the .pptx.
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

# ---- DS template palette: black header / white background ----
BLACK      = RGBColor(0x11, 0x11, 0x11)   # header band
INK        = RGBColor(0x1A, 0x1A, 0x1A)   # body text
WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
GRAYCARD   = RGBColor(0xF4, 0xF5, 0xF7)   # neutral card
LINE       = RGBColor(0xDD, 0xDF, 0xE4)   # hairlines / borders
MUTED      = RGBColor(0x70, 0x74, 0x7C)   # captions
ACCENT     = RGBColor(0x14, 0x28, 0xA0)   # Samsung Blue — sparing accent
ACCENT_LT  = RGBColor(0xEC, 0xEF, 0xF9)   # accent tint (chips)
GREEN      = RGBColor(0x1A, 0x9E, 0x5E)
AMBER      = RGBColor(0xE5, 0x97, 0x00)
RED        = RGBColor(0xD6, 0x45, 0x41)
REDBG      = RGBColor(0xFD, 0xF1, 0xF0)

HEAD_FONT = "맑은 고딕"
BODY_FONT = "맑은 고딕"
MONO_FONT = "Consolas"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
SW, SH = prs.slide_width, prs.slide_height


def _set_font(run, name):
    run.font.name = name
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", name)


def text(slide, l, t, w, h, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         wrap=True, line_spacing=1.0):
    tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Pt(2)
    tf.margin_top = tf.margin_bottom = Pt(2)
    for i, line in enumerate(runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        if isinstance(line, str):
            line = [(line, 16, INK, False, BODY_FONT)]
        for seg in line:
            txt, size, color, bold, font = seg
            r = p.add_run()
            r.text = txt
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.color.rgb = color
            _set_font(r, font)
    return tb


def rect(slide, l, t, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE, line_w=1.0):
    sp = slide.shapes.add_shape(shape, Inches(l), Inches(t), Inches(w), Inches(h))
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line
        sp.line.width = Pt(line_w)
    sp.shadow.inherit = False
    return sp


def shape_text(sp, runs, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE):
    tf = sp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Pt(6)
    tf.margin_top = tf.margin_bottom = Pt(4)
    for i, line in enumerate(runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        for seg in line:
            txt, size, color, bold, font = seg
            r = p.add_run(); r.text = txt
            r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = color
            _set_font(r, font)


def header(slide, title, kicker=None):
    """Black header band on white slide."""
    rect(slide, 0, 0, 13.333, 7.5, WHITE)                 # white background
    rect(slide, 0, 0, 13.333, 1.2, BLACK)                 # black header band
    rect(slide, 0, 1.2, 13.333, 0.05, ACCENT)             # thin accent rule
    if kicker:
        text(slide, 0.6, 0.2, 11, 0.3, [[(kicker, 12, RGBColor(0xB9,0xC4,0xEA), True, HEAD_FONT)]])
    text(slide, 0.6, 0.46, 12, 0.66, [[(title, 26, WHITE, True, HEAD_FONT)]],
         anchor=MSO_ANCHOR.MIDDLE)
    text(slide, 9.0, 0.2, 3.73, 0.3,
         [[("SAMSUNG ", 11, WHITE, True, HEAD_FONT), ("DS", 11, RGBColor(0xB9,0xC4,0xEA), True, HEAD_FONT)]],
         align=PP_ALIGN.RIGHT)
    footer(slide)


def footer(slide):
    text(slide, 0.6, 7.08, 7, 0.3, [[("대외비 · Confidential", 9, MUTED, False, BODY_FONT)]])
    text(slide, 6.0, 7.08, 6.73, 0.3,
         [[("인사팀 대상 설명자료", 9, MUTED, False, BODY_FONT)]], align=PP_ALIGN.RIGHT)


def chip(slide, l, t, w, label):
    sp = rect(slide, l, t, w, 0.42, GRAYCARD, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    shape_text(sp, [[(label, 12, INK, True, BODY_FONT)]])
    return sp


# ============================== SLIDE 1: COVER ==============================
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, 13.333, 7.5, WHITE)
rect(s, 0, 0, 13.333, 1.5, BLACK)                          # black header band
rect(s, 0, 1.5, 13.333, 0.06, ACCENT)                      # accent rule
text(s, 0.9, 0.52, 11, 0.5, [[("SAMSUNG ", 18, WHITE, True, HEAD_FONT),
                              ("DS", 18, RGBColor(0xB9,0xC4,0xEA), True, HEAD_FONT)]],
     anchor=MSO_ANCHOR.MIDDLE)
text(s, 0.9, 2.7, 11.5, 2.0, [
    [("개인정보 보호 게이트웨이", 44, INK, True, HEAD_FONT)],
    [("PII Encryption Gateway", 22, ACCENT, False, HEAD_FONT)],
], line_spacing=1.12)
rect(s, 0.95, 4.55, 2.3, 0.06, BLACK)                      # divider tick
text(s, 0.95, 4.8, 11, 0.6,
     [[("인사 데이터를 AI에 ", 18, INK, False, BODY_FONT),
       ("그대로 노출하지 않고", 18, INK, True, BODY_FONT),
       (" 안전하게 활용하는 법", 18, INK, False, BODY_FONT)]])
text(s, 0.95, 6.45, 11, 0.4,
     [[("인사팀 대상 설명자료  ·  2026.06  ·  대외비", 13, MUTED, False, BODY_FONT)]])

# ===================== SLIDE 2: WHY (the problem) =====================
s = prs.slides.add_slide(BLANK)
header(s, "왜 필요한가요?", "배경")
text(s, 0.6, 1.55, 12.1, 0.6,
     [[("인사 데이터에는 ", 18, INK, False, BODY_FONT),
       ("가장 민감한 개인정보", 18, RED, True, BODY_FONT),
       ("가 들어 있습니다.", 18, INK, False, BODY_FONT)]])
for i, (t_, d) in enumerate([
        ("연봉·급여", "급여대장"), ("주민등록번호", "신원 정보"),
        ("계좌번호", "급여 이체"), ("전화·이메일", "연락처"), ("근태", "지각·결근")]):
    x = 0.6 + i * 2.42
    c = rect(s, x, 2.3, 2.25, 1.0, GRAYCARD, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    shape_text(c, [[(t_, 15, INK, True, BODY_FONT)], [(d, 11, MUTED, False, BODY_FONT)]])
text(s, 0.6, 3.8, 12.1, 0.6,
     [[("그런데 이 데이터로 ", 18, INK, False, BODY_FONT),
       ("AI에게 안내문·통지·리포트", 18, ACCENT, True, BODY_FONT),
       ("를 맡기려면?", 18, INK, False, BODY_FONT)]])
prob = rect(s, 0.6, 4.55, 12.13, 1.9, REDBG, line=RED, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
shape_text(prob, [
    [("⚠  위험: 원본을 그대로 AI에 넣으면 민감정보가 모델에 노출됩니다", 18, RED, True, BODY_FONT)],
    [("최민준 · 770324-1809570 · 5,350만원 · 신한 617-1434-688508 …", 14, MUTED, False, MONO_FONT)],
    [("한 번 노출된 개인정보는 되돌릴 수 없고, 유출 시 법적·평판 리스크가 큽니다.", 14, INK, False, BODY_FONT)],
], align=PP_ALIGN.LEFT)

# ===================== SLIDE 3: WHAT IT IS =====================
s = prs.slides.add_slide(BLANK)
header(s, "한 장 요약: 무엇인가요?", "개념")
big = rect(s, 0.6, 1.55, 12.13, 1.35, BLACK, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
shape_text(big, [
    [("민감한 값을 ‘대리 번호표(토큰)’로 바꿔 AI에 보여주고,", 19, WHITE, True, BODY_FONT)],
    [("작업이 끝나면 담당자 키로만 원래 값을 되돌려 주는 안전 통로입니다.", 19, WHITE, True, BODY_FONT)],
])
text(s, 0.6, 3.2, 12, 0.4, [[("🔐  은행 금고에 비유하면", 15, ACCENT, True, BODY_FONT)]])
for i, (h, d) in enumerate([
    ("금고에 보관", "원본 민감정보는 암호화해 ‘금고(vault)’에 넣습니다"),
    ("번호표로 작업", "AI는 실제 값 대신 번호표(토큰)만 보고 일합니다"),
    ("열쇠 가진 사람만", "담당자 키가 있어야 원본을 꺼내볼 수 있습니다")]):
    x = 0.6 + i * 4.04
    c = rect(s, x, 3.65, 3.85, 2.5, GRAYCARD, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    num = rect(s, x + 0.25, 3.9, 0.6, 0.6, BLACK, shape=MSO_SHAPE.OVAL)
    shape_text(num, [[(str(i + 1), 18, WHITE, True, HEAD_FONT)]])
    text(s, x + 0.25, 4.7, 3.4, 0.5, [[(h, 17, INK, True, BODY_FONT)]])
    text(s, x + 0.25, 5.2, 3.4, 1.0, [[(d, 13, INK, False, BODY_FONT)]], line_spacing=1.1)

# ===================== SLIDE 4: HOW IT WORKS =====================
s = prs.slides.add_slide(BLANK)
header(s, "어떻게 동작하나요? — 3단계", "동작 원리")
steps = [
    ("1. 보호 (Protect)", "원본 → 토큰\n원본은 키로 암호화", "5,350만원  →  [[SALARY:3f9a2c1d]]"),
    ("2. 작업 (Work)", "AI는 토큰만 보고\n안내문·통지·리포트 작성", "“[[NAME]]님의 연봉은 [[SALARY]]…”"),
    ("3. 복원 (Reveal)", "담당자 키로 토큰 →\n원본 (인가자만)", "[[SALARY:3f9a2c1d]]  →  5,350만원"),
]
for i, (h, d, ex) in enumerate(steps):
    x = 0.6 + i * 4.35
    rect(s, x, 1.75, 3.95, 3.7, WHITE, line=BLACK, shape=MSO_SHAPE.ROUNDED_RECTANGLE, line_w=1.5)
    rect(s, x, 1.75, 3.95, 0.7, BLACK, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    text(s, x, 1.83, 3.95, 0.55, [[(h, 16, WHITE, True, BODY_FONT)]], align=PP_ALIGN.CENTER)
    text(s, x + 0.3, 2.7, 3.35, 1.3, [[(ln, 14, INK, False, BODY_FONT)] for ln in d.split("\n")],
         align=PP_ALIGN.CENTER, line_spacing=1.15)
    exb = rect(s, x + 0.25, 4.3, 3.45, 0.95, GRAYCARD, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    shape_text(exb, [[(ex, 11, INK, False, MONO_FONT)]])
    if i < 2:
        rect(s, x + 3.98, 3.3, 0.34, 0.6, BLACK, shape=MSO_SHAPE.CHEVRON)
banner = rect(s, 0.6, 5.8, 12.13, 0.85, GRAYCARD, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
shape_text(banner, [[("핵심: 작업 중 AI 화면(중간본)에는 ", 15, INK, False, BODY_FONT),
                     ("실제 값이 단 한 번도 등장하지 않습니다.", 15, ACCENT, True, BODY_FONT)]])

# ===================== SLIDE 5: WHAT IT PROTECTS =====================
s = prs.slides.add_slide(BLANK)
header(s, "무엇을, 어디까지 보호하나요?", "보호 범위")
text(s, 0.6, 1.5, 12, 0.4, [[("자동으로 찾아 가리는 민감정보", 16, INK, True, BODY_FONT)]])
ents = ["주민등록번호", "연봉·급여", "계좌번호", "전화번호", "이메일", "카드번호",
        "사업자등록번호", "IP 주소", "직원 이름(명부)"]
for i, e in enumerate(ents):
    chip(s, 0.6 + (i % 5) * 2.45, 2.0 + (i // 5) * 0.55, 2.3, e)
text(s, 0.6, 3.3, 12, 0.4, [[("네 가지 방식으로 빠짐없이 탐지", 16, INK, True, BODY_FONT)]])
ways = [
    ("① 컬럼 이름", "‘연봉’, ‘주민번호’ 같은 열을 인식"),
    ("② 컬럼 형태", "이름이 달라도 값 모양으로 자동 판별"),
    ("③ 값 모양", "문장 속에 섞인 번호·연락처도 탐지"),
    ("④ 명부 이름", "담당자 명부의 직원 이름을 정확히 가림"),
]
for i, (h, d) in enumerate(ways):
    x = 0.6 + (i % 2) * 6.15
    y = 3.8 + (i // 2) * 1.05
    rect(s, x, y, 5.95, 0.92, GRAYCARD, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    rect(s, x, y, 0.1, 0.92, BLACK)
    text(s, x + 0.3, y + 0.1, 2.4, 0.7, [[(h, 14, INK, True, BODY_FONT)]], anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 2.55, y + 0.1, 3.25, 0.7, [[(d, 12.5, INK, False, BODY_FONT)]], anchor=MSO_ANCHOR.MIDDLE)
note = rect(s, 0.6, 6.0, 12.13, 0.62, ACCENT_LT, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
shape_text(note, [[("엑셀·CSV 명부뿐 아니라 ", 14, INK, False, BODY_FONT),
                   ("메모·이메일 초안 같은 문서(.txt/.md)", 14, ACCENT, True, BODY_FONT),
                   ("도 그대로 보호됩니다.", 14, INK, False, BODY_FONT)]])

# ===================== SLIDE 6: BENEFITS =====================
s = prs.slides.add_slide(BLANK)
header(s, "인사팀에게 무엇이 좋은가요?", "기대 효과")
benefits = [
    ("🛡", "안전", "민감정보가 AI에 0건 노출.\n유출 리스크를 원천 차단"),
    ("⚡", "간편", "평소처럼 안내문·통지문 작성.\n보호는 도구가 알아서 처리"),
    ("🔑", "되돌림", "담당자 키로만 원복.\n키 없으면 복원 불가 = 접근통제"),
    ("💸", "효율", "대규모에선 토큰도 더 적게 사용\n(원본 전체를 읽지 않으므로)"),
]
for i, (ic, h, d) in enumerate(benefits):
    x = 0.6 + i * 3.06
    rect(s, x, 1.75, 2.9, 2.7, WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    icb = rect(s, x + 1.05, 2.0, 0.8, 0.8, GRAYCARD, line=LINE, shape=MSO_SHAPE.OVAL)
    shape_text(icb, [[(ic, 24, INK, False, BODY_FONT)]])
    text(s, x, 2.9, 2.9, 0.4, [[(h, 18, INK, True, BODY_FONT)]], align=PP_ALIGN.CENTER)
    text(s, x + 0.2, 3.35, 2.5, 1.0, [[(ln, 12.5, INK, False, BODY_FONT)] for ln in d.split("\n")],
         align=PP_ALIGN.CENTER, line_spacing=1.1)
ev = rect(s, 0.6, 4.9, 12.13, 1.65, BLACK, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
shape_text(ev, [
    [("검증 결과 (동일 과제 비교)", 14, RGBColor(0xB9,0xC4,0xEA), True, BODY_FONT)],
    [("게이트웨이 사용 100%  vs  미사용 62.5%", 22, WHITE, True, BODY_FONT)],
    [("개인 안내·통지 작업에서 미사용은 매번 실제 PII가 노출 — 게이트웨이는 누출 0 유지", 13, RGBColor(0xD3,0xD6,0xDD), False, BODY_FONT)],
])

# ===================== SLIDE 7: EXAMPLE =====================
s = prs.slides.add_slide(BLANK)
header(s, "실제로 이렇게 쓰입니다", "사용 예시")
text(s, 0.6, 1.5, 12, 0.5,
     [[("예) 사번 E0007 직원에게 ", 16, INK, False, BODY_FONT),
       ("2026년 연봉 안내 메일", 16, ACCENT, True, BODY_FONT), (" 작성", 16, INK, False, BODY_FONT)]])
d1 = rect(s, 0.6, 2.1, 5.95, 3.6, GRAYCARD, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
rect(s, 0.6, 2.1, 5.95, 0.6, MUTED, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
text(s, 0.6, 2.17, 5.95, 0.45, [[("AI가 보는 중간본 (토큰)", 14, WHITE, True, BODY_FONT)]], align=PP_ALIGN.CENTER)
text(s, 0.9, 2.9, 5.4, 2.7, [
    [("받는사람: [[NAME:369de402]]", 12.5, INK, False, MONO_FONT)],
    [("", 6, INK, False, MONO_FONT)],
    [("안녕하세요, [[NAME:369de402]]님.", 12.5, INK, False, MONO_FONT)],
    [("2026년 확정 연봉은", 12.5, INK, False, MONO_FONT)],
    [("[[SALARY:28314826]] 입니다.", 12.5, INK, False, MONO_FONT)],
    [("", 6, INK, False, MONO_FONT)],
    [("→ 실제 이름·연봉 없음 ✓", 12.5, GREEN, True, BODY_FONT)],
], line_spacing=1.15)
arrow = rect(s, 6.62, 3.6, 0.55, 0.6, BLACK, shape=MSO_SHAPE.CHEVRON)
shape_text(arrow, [[("키", 12, WHITE, True, BODY_FONT)]])
d2 = rect(s, 7.3, 2.1, 5.43, 3.6, WHITE, line=BLACK, shape=MSO_SHAPE.ROUNDED_RECTANGLE, line_w=1.5)
rect(s, 7.3, 2.1, 5.43, 0.6, BLACK, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
text(s, 7.3, 2.17, 5.43, 0.45, [[("담당자만 보는 최종본 (원본 복원)", 14, WHITE, True, BODY_FONT)]], align=PP_ALIGN.CENTER)
text(s, 7.6, 2.9, 4.9, 2.7, [
    [("받는사람: 신다은", 12.5, INK, False, BODY_FONT)],
    [("", 6, INK, False, BODY_FONT)],
    [("안녕하세요, 신다은님.", 12.5, INK, False, BODY_FONT)],
    [("2026년 확정 연봉은", 12.5, INK, False, BODY_FONT)],
    [("3,194만원 입니다.", 12.5, INK, True, BODY_FONT)],
    [("", 6, INK, False, BODY_FONT)],
    [("→ 인가된 담당자에게만 ✓", 12.5, ACCENT, True, BODY_FONT)],
], line_spacing=1.15)
text(s, 0.6, 5.9, 12, 0.5,
     [[("같은 방식으로 ", 14, INK, False, BODY_FONT),
       ("근태 통지·상여금 입금 안내·부서 리포트", 14, ACCENT, True, BODY_FONT),
       (" 등 일상 업무에 그대로 적용됩니다.", 14, INK, False, BODY_FONT)]])

# ===================== SLIDE 8: LIMITS =====================
s = prs.slides.add_slide(BLANK)
header(s, "꼭 알아둘 점 (솔직한 한계)", "유의사항")
items = [
    ("토큰으로는 계산 불가", "‘평균 연봉’ 같은 집계는 토큰으로 못 합니다. 원본 대상 스크립트로 계산해 결과 숫자만 활용합니다."),
    ("같은 값 = 같은 번호표", "그룹핑이 가능한 대신, 누가 같은 값을 갖는지(동일성)는 드러납니다. 값 자체는 키 없이 복원 불가."),
    ("문장 속 이름은 명부 필요", "패턴이 없는 ‘이름’은 담당자 명부를 줘야 가립니다. 명부에 없는 외부 인물 이름은 탐지 못 함."),
    ("키 관리가 핵심", "복원은 담당자 키로만 가능 → 키를 안전하게 보관·관리해야 합니다. 키 분실 시 복원 불가."),
]
for i, (h, d) in enumerate(items):
    y = 1.65 + i * 1.32
    rect(s, 0.6, y, 12.13, 1.15, GRAYCARD, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    rect(s, 0.6, y, 0.12, 1.15, AMBER)
    text(s, 0.95, y + 0.12, 4.0, 0.95, [[(h, 15, INK, True, BODY_FONT)]], anchor=MSO_ANCHOR.MIDDLE)
    text(s, 5.0, y + 0.12, 7.5, 0.95, [[(d, 12.5, INK, False, BODY_FONT)]], anchor=MSO_ANCHOR.MIDDLE, line_spacing=1.05)

# ===================== SLIDE 9: GETTING STARTED =====================
s = prs.slides.add_slide(BLANK)
header(s, "시작하기", "도입")
steps2 = [
    ("1  보호", "민감 파일을 게이트웨이에 통과 → 토큰본 + 암호화 금고 생성"),
    ("2  작업", "토큰본으로 평소처럼 안내문·통지·리포트 작성"),
    ("3  복원", "담당자 키로 최종본만 원복하여 발송"),
]
for i, (h, d) in enumerate(steps2):
    y = 1.75 + i * 1.05
    rect(s, 0.6, y, 12.13, 0.9, GRAYCARD, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    nb = rect(s, 0.85, y + 0.15, 1.4, 0.6, BLACK, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    shape_text(nb, [[(h, 15, WHITE, True, HEAD_FONT)]])
    text(s, 2.5, y + 0.1, 9.8, 0.7, [[(d, 15, INK, False, BODY_FONT)]], anchor=MSO_ANCHOR.MIDDLE)
box = rect(s, 0.6, 5.1, 12.13, 1.2, BLACK, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
shape_text(box, [
    [("문의 · 도입 지원", 13, RGBColor(0xB9,0xC4,0xEA), True, BODY_FONT)],
    [("담당자 키 발급과 적용 방법은 데이터보호 담당 부서로 문의해 주세요.", 15, WHITE, False, BODY_FONT)],
], align=PP_ALIGN.LEFT)
text(s, 0.6, 6.45, 12.13, 0.4,
     [[("※ 데이터는 모두 합성(가상) 예시입니다.", 10, MUTED, False, BODY_FONT)]])

import os
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PII_게이트웨이_인사팀_설명.pptx")
prs.save(out)
print("saved:", out, "| slides:", len(list(prs.slides)))
