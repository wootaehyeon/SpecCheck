from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# ── 색상 팔레트 ──────────────────────────────────────────────
BG_DARK      = RGBColor(0x0D, 0x1B, 0x2A)
BG_CARD      = RGBColor(0x16, 0x27, 0x3A)
ACCENT_BLUE  = RGBColor(0x00, 0x9B, 0xFF)
ACCENT_CYAN  = RGBColor(0x00, 0xD4, 0xFF)
ACCENT_PURPLE= RGBColor(0x9B, 0x59, 0xF5)
TEXT_WHITE   = RGBColor(0xFF, 0xFF, 0xFF)
TEXT_GRAY    = RGBColor(0xB0, 0xC4, 0xD8)
TAG_GREEN    = RGBColor(0x1E, 0xC8, 0x7E)
TAG_AMBER    = RGBColor(0xFF, 0xB8, 0x30)
TAG_RED      = RGBColor(0xFF, 0x4D, 0x4D)
DIVIDER      = RGBColor(0x1E, 0x3A, 0x52)
USED_COLOR   = RGBColor(0xFF, 0x8C, 0x42)   # 중고 시세 포인트

W = Inches(13.33)
H = Inches(7.5)

prs = Presentation()
prs.slide_width  = W
prs.slide_height = H

# ── 헬퍼 함수 ────────────────────────────────────────────────
def blank_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])

def fill_bg(slide, color=BG_DARK):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color

def add_rect(slide, l, t, w, h, fill_color):
    shape = slide.shapes.add_shape(1, l, t, w, h)
    shape.line.fill.background()
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    return shape

def add_text(slide, text, l, t, w, h,
             font_size=18, bold=False, color=TEXT_WHITE,
             align=PP_ALIGN.LEFT, italic=False):
    txb = slide.shapes.add_textbox(l, t, w, h)
    txb.word_wrap = True
    tf = txb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return txb

def add_multiline(slide, lines, l, t, w, h,
                  font_size=15, color=TEXT_WHITE, spacing_after=5,
                  bold_first=False):
    txb = slide.shapes.add_textbox(l, t, w, h)
    txb.word_wrap = True
    tf = txb.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(spacing_after)
        run = p.add_run()
        run.text = line
        run.font.size = Pt(font_size)
        run.font.bold = bold_first and i == 0
        run.font.color.rgb = color

def slide_header(slide, title, subtitle=None):
    add_rect(slide, 0, Inches(0.55), W, Pt(3), ACCENT_BLUE)
    add_rect(slide, Inches(0.5), Inches(0.72), Pt(8), Pt(8), ACCENT_CYAN)
    add_text(slide, title,
             Inches(0.72), Inches(0.62), Inches(11), Inches(0.7),
             font_size=28, bold=True)
    if subtitle:
        add_text(slide, subtitle,
                 Inches(0.72), Inches(1.15), Inches(11), Inches(0.4),
                 font_size=13, color=ACCENT_CYAN)


# ══════════════════════════════════════════════════════════════
#  SLIDE 1 — 표지
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
add_rect(sl, Inches(8.5), 0, Inches(4.83), H, RGBColor(0x0A, 0x14, 0x22))
add_rect(sl, Inches(8.48), Inches(1.5), Pt(3), Inches(4.5), ACCENT_BLUE)

add_text(sl, "SpecCheck",
         Inches(0.8), Inches(1.8), Inches(7.5), Inches(1.4),
         font_size=64, bold=True, color=ACCENT_CYAN)
add_text(sl, "AI 기반 PC 견적 검증 시스템",
         Inches(0.8), Inches(3.1), Inches(7.5), Inches(0.7),
         font_size=26, bold=True)
add_text(sl, "가격 (신품/중고) · 성능 · 호환성 · 커뮤니티 평가를 종합 분석",
         Inches(0.8), Inches(3.75), Inches(7.5), Inches(0.5),
         font_size=15, color=TEXT_GRAY)
add_rect(sl, Inches(0.8), Inches(4.35), Inches(4.0), Pt(2), ACCENT_BLUE)
add_text(sl, "2026  /  졸업작품 최종 발표",
         Inches(0.8), Inches(4.55), Inches(6), Inches(0.4),
         font_size=13, color=TEXT_GRAY)

for i, txt in enumerate(["💡 견적 검증", "📊 성능 분석",
                          "🔍 커뮤니티 평판", "🛒 중고 시세 최적화"]):
    add_text(sl, txt, Inches(9.0), Inches(2.3 + i*0.75), Inches(3.5), Inches(0.5),
             font_size=14, color=TEXT_GRAY)


# ══════════════════════════════════════════════════════════════
#  SLIDE 2 — 목차
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "목차", "Table of Contents")

items = [
    ("01", "프로젝트 개요"),
    ("02", "기존 서비스와의 차별점"),
    ("03", "전체 시스템 아키텍처"),
    ("04", "견적 입력 모듈"),
    ("05", "가격 분석 — 신품 시세"),
    ("06", "가격 분석 — 중고 시세 (eBay)"),
    ("07", "중고가 기반 견적 최적화"),
    ("08", "성능 분석 모듈"),
    ("09", "커뮤니티 데이터 수집"),
    ("10", "AI 감정분석 모델"),
    ("11", "3D 조립 시뮬레이션"),
    ("12", "확장 기능 및 미구현 기능"),
]

cols, gap_x = 2, Inches(6.5)
start_x, start_y, gap_y = Inches(0.8), Inches(1.6), Inches(0.83)

for idx, (num, label) in enumerate(items):
    col, row = idx % cols, idx // cols
    x = start_x + col * gap_x
    y = start_y + row * gap_y
    add_rect(sl, x, y + Inches(0.05), Inches(0.55), Inches(0.55), ACCENT_BLUE)
    add_text(sl, num, x, y, Inches(0.55), Inches(0.65),
             font_size=13, bold=True, align=PP_ALIGN.CENTER)
    color = USED_COLOR if "중고" in label else TEXT_WHITE
    add_text(sl, label, x + Inches(0.65), y + Inches(0.08), Inches(5.0), Inches(0.55),
             font_size=15, color=color)
    add_rect(sl, x, y + Inches(0.68), Inches(5.2), Pt(1), DIVIDER)


# ══════════════════════════════════════════════════════════════
#  SLIDE 3 — 프로젝트 개요
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "01. 프로젝트 개요", "Project Overview")

add_rect(sl, Inches(0.5), Inches(1.55), Inches(5.9), Inches(2.3), BG_CARD)
add_rect(sl, Inches(0.5), Inches(1.55), Pt(4), Inches(2.3), ACCENT_BLUE)
add_text(sl, "문제 정의",
         Inches(0.7), Inches(1.6), Inches(5), Inches(0.45),
         font_size=15, bold=True, color=ACCENT_CYAN)
add_multiline(sl, [
    "• 소비자는 견적서를 받아도 스스로 검증하기 어렵다",
    "• 가격 거품, 부품 불균형, 호환성 문제를 판단할 전문 지식 부족",
    "• 중고 부품과의 가격 비교 없이 신품만 구매하는 비효율",
], Inches(0.7), Inches(2.05), Inches(5.5), Inches(1.6),
   font_size=13, color=TEXT_GRAY)

add_rect(sl, Inches(6.9), Inches(1.55), Inches(5.9), Inches(2.3), BG_CARD)
add_rect(sl, Inches(6.9), Inches(1.55), Pt(4), Inches(2.3), TAG_GREEN)
add_text(sl, "솔루션",
         Inches(7.1), Inches(1.6), Inches(5), Inches(0.45),
         font_size=15, bold=True, color=TAG_GREEN)
add_multiline(sl, [
    "• 견적서를 AI가 파싱 → 부품 자동 인식",
    "• 신품(네이버) + 중고(eBay) 이원화 가격 비교",
    "• 성능 / 호환성 / 커뮤니티 다각도 분석 후 LLM 설명",
], Inches(7.1), Inches(2.05), Inches(5.5), Inches(1.6),
   font_size=13, color=TEXT_GRAY)

add_text(sl, "6대 분석 기준",
         Inches(0.5), Inches(4.1), Inches(10), Inches(0.45),
         font_size=16, bold=True)

criteria = [
    ("💰", "신품\n가격"),
    ("🛒", "중고\n시세"),
    ("⚡", "성능"),
    ("🔗", "호환성"),
    ("🕐", "최신성"),
    ("💬", "커뮤니티"),
]
for i, (icon, label) in enumerate(criteria):
    x = Inches(0.5 + i * 2.05)
    col = USED_COLOR if "중고" in label else ACCENT_BLUE
    add_rect(sl, x, Inches(4.6), Inches(1.9), Inches(1.95), BG_CARD)
    add_rect(sl, x, Inches(6.35), Inches(1.9), Pt(3), col)
    add_text(sl, icon, x, Inches(4.65), Inches(1.9), Inches(0.7),
             font_size=22, align=PP_ALIGN.CENTER)
    add_text(sl, label, x, Inches(5.3), Inches(1.9), Inches(1.0),
             font_size=13, bold=True, color=col, align=PP_ALIGN.CENTER)


# ══════════════════════════════════════════════════════════════
#  SLIDE 4 — 기존 서비스와의 차별점
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "02. 기존 서비스와의 차별점", "Competitive Differentiation")

headers = ["기능", "다나와", "컴퓨존", "SpecCheck"]
col_x = [Inches(0.5), Inches(3.1), Inches(5.7), Inches(8.3)]
cw    = [Inches(2.5), Inches(2.5), Inches(2.5), Inches(3.3)]
row_h = Inches(0.67)
rows_data = [
    ["신품 가격 비교",    "✅ 강점", "△ 부분",  "✅ 네이버 쇼핑 API"],
    ["중고 시세 비교",    "❌",      "❌",       "✅ eBay 실시간 조회"],
    ["견적 추천",         "❌",      "✅ 강점",  "⬜ 검증 중심"],
    ["견적 검증",         "❌",      "❌",       "✅ 핵심 기능"],
    ["성능 분석",         "❌",      "△ 간단",  "✅ 병목·균형"],
    ["커뮤니티 평판",     "❌",      "❌",       "✅ KoBERT 감정분석"],
    ["중고 최적화 제안",  "❌",      "❌",       "✅ 예산 절감 추천"],
    ["AI 설명 생성",      "❌",      "❌",       "✅ LLM 기반"],
]

sy = Inches(1.55)
for ci, (hdr, cx) in enumerate(zip(headers, col_x)):
    add_rect(sl, cx, sy, cw[ci] - Inches(0.05), row_h, ACCENT_BLUE if ci == 3 else BG_CARD)
    add_text(sl, hdr, cx, sy, cw[ci], row_h,
             font_size=13, bold=True, align=PP_ALIGN.CENTER)

for ri, row in enumerate(rows_data):
    y = sy + row_h * (ri + 1)
    bg = BG_CARD if ri % 2 == 0 else RGBColor(0x12, 0x22, 0x32)
    for ci, (cell, cx) in enumerate(zip(row, col_x)):
        cell_bg = RGBColor(0x0D, 0x28, 0x40) if ci == 3 else bg
        add_rect(sl, cx, y, cw[ci] - Inches(0.05), row_h, cell_bg)
        if ci == 3:
            cc = USED_COLOR if "중고" in cell else ACCENT_CYAN
        else:
            cc = TEXT_GRAY
        add_text(sl, cell, cx, y, cw[ci], row_h,
                 font_size=12, color=cc, align=PP_ALIGN.CENTER)

add_rect(sl, Inches(8.3), sy, Pt(3), row_h * 9, TAG_GREEN)
add_text(sl, "✔  SpecCheck = 신품·중고 가격을 모두 아우르는 유일한 견적 검증 도구",
         Inches(0.5), Inches(7.1), Inches(12), Inches(0.4),
         font_size=13, bold=True, color=ACCENT_CYAN)


# ══════════════════════════════════════════════════════════════
#  SLIDE 5 — 전체 시스템 아키텍처 (4 DB 소스 포함)
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "03. 전체 시스템 아키텍처", "System Architecture")

# ── 레이어 라벨 ──
layers = [
    ("입력", Inches(0.3)),
    ("파싱", Inches(2.1)),
    ("데이터 소스", Inches(4.0)),
    ("분석 엔진", Inches(7.1)),
    ("생성·출력", Inches(10.2)),
]
for lbl, x in layers:
    add_text(sl, lbl, x, Inches(1.3), Inches(2.5), Inches(0.35),
             font_size=11, color=TEXT_GRAY, align=PP_ALIGN.CENTER)
    add_rect(sl, x, Inches(1.6), Inches(1.7), Pt(2), DIVIDER)

# ── 박스 정의: (x, y, w, h, label, color) ──
B = {
    "input":   (Inches(0.3),  Inches(2.8),  Inches(1.7), Inches(1.1),
                "사용자\n입력", ACCENT_BLUE),
    "parse":   (Inches(2.1),  Inches(2.8),  Inches(1.7), Inches(1.1),
                "견적\n파싱 (LLM)", BG_CARD),
    "db_new":  (Inches(4.0),  Inches(1.65), Inches(2.6), Inches(0.95),
                "💰 신품 가격 DB\n(네이버 쇼핑 API)", BG_CARD),
    "db_used": (Inches(4.0),  Inches(2.75), Inches(2.6), Inches(0.95),
                "🛒 중고 시세 DB\n(eBay Browse API)", RGBColor(0x2A, 0x1A, 0x08)),
    "db_bench":(Inches(4.0),  Inches(3.85), Inches(2.6), Inches(0.95),
                "⚡ 성능 DB\n(CPU/GPU 벤치마크)", BG_CARD),
    "db_comm": (Inches(4.0),  Inches(4.95), Inches(2.6), Inches(0.95),
                "💬 커뮤니티 DB\n(DC인사이드 크롤링)", BG_CARD),
    "engine":  (Inches(7.1),  Inches(2.6),  Inches(2.0), Inches(1.8),
                "AI\n분석 엔진", RGBColor(0x12, 0x30, 0x55)),
    "llm":     (Inches(9.6),  Inches(2.8),  Inches(1.7), Inches(1.1),
                "LLM\n설명 생성", RGBColor(0x12, 0x30, 0x55)),
    "out":     (Inches(11.6), Inches(2.8),  Inches(1.5), Inches(1.1),
                "분석\n결과 제공", TAG_GREEN),
}

for key, (bx, by, bw, bh, lbl, col) in B.items():
    add_rect(sl, bx, by, bw, bh, col)
    if key == "db_used":
        add_rect(sl, bx, by, bw, Pt(3), USED_COLOR)
    elif key in ("db_new",):
        add_rect(sl, bx, by, bw, Pt(3), ACCENT_BLUE)
    elif key in ("db_bench",):
        add_rect(sl, bx, by, bw, Pt(3), ACCENT_CYAN)
    elif key in ("db_comm",):
        add_rect(sl, bx, by, bw, Pt(3), TAG_GREEN)
    lbl_col = USED_COLOR if key == "db_used" else TEXT_WHITE
    add_text(sl, lbl, bx + Inches(0.05), by, bw - Inches(0.1), bh,
             font_size=11, bold=True, color=lbl_col, align=PP_ALIGN.CENTER)

def h_arrow(slide, x1, y_mid, x2, color=ACCENT_BLUE):
    add_rect(slide, x1, y_mid - Pt(1.5), x2 - x1, Pt(3), color)
    add_text(slide, "▶", x2 - Pt(12), y_mid - Pt(9), Pt(20), Pt(18),
             font_size=9, color=color)

def v_line(slide, x_mid, y1, y2, color=DIVIDER):
    add_rect(slide, x_mid - Pt(1.5), y1, Pt(3), y2 - y1, color)

# input → parse
bx, by, bw, bh = B["input"][:4]
nbx, nby, nbw, nbh = B["parse"][:4]
h_arrow(sl, bx + bw, by + bh/2, nbx, ACCENT_BLUE)

# parse → 4 DB (수직 분기선 + 4개 수평선)
px_end = B["parse"][0] + B["parse"][2]
branch_x = px_end + Inches(0.15)
db_mids = [B[k][1] + B[k][3]/2 for k in ("db_new", "db_used", "db_bench", "db_comm")]
y_parse_mid = B["parse"][1] + B["parse"][3]/2
v_line(sl, branch_x, min(db_mids), max(db_mids), DIVIDER)
for y_mid in db_mids:
    col = USED_COLOR if abs(y_mid - db_mids[1]) < Pt(2) else ACCENT_BLUE
    add_rect(sl, branch_x, y_mid - Pt(1.5), B["db_new"][0] - branch_x, Pt(3), col)
    add_text(sl, "▶", B["db_new"][0] - Pt(14), y_mid - Pt(9), Pt(20), Pt(18),
             font_size=9, color=col)
# parse → branch 수평선
h_arrow(sl, px_end, y_parse_mid, branch_x, ACCENT_BLUE)

# 4 DB → engine (수직 수합선)
ex = B["engine"][0]
merge_x = ex - Inches(0.15)
for k in ("db_new", "db_used", "db_bench", "db_comm"):
    y_mid = B[k][1] + B[k][3]/2
    col = USED_COLOR if k == "db_used" else ACCENT_BLUE
    add_rect(sl, B[k][0] + B[k][2], y_mid - Pt(1.5), merge_x - (B[k][0] + B[k][2]), Pt(3), col)
v_line(sl, merge_x, min(db_mids), max(db_mids), DIVIDER)
ey_mid = B["engine"][1] + B["engine"][3]/2
h_arrow(sl, merge_x, ey_mid, ex, ACCENT_BLUE)

# engine → llm → out
for (ak, bk) in [("engine", "llm"), ("llm", "out")]:
    ax, ay, aw, ah = B[ak][:4]
    bx2, by2, bw2, bh2 = B[bk][:4]
    h_arrow(sl, ax + aw, ay + ah/2, bx2, ACCENT_BLUE)

# ── API 엔드포인트 라벨 (하단) ──
add_rect(sl, Inches(0.3), Inches(6.35), Inches(12.7), Inches(1.0), BG_CARD)
add_text(sl, "주요 API 엔드포인트",
         Inches(0.5), Inches(6.38), Inches(3), Inches(0.35),
         font_size=11, bold=True, color=ACCENT_CYAN)
apis = [
    "/api/price-check", "/api/market-prices",
    "/api/used-prices", "/api/optimize-estimate",
    "/api/crawl",       "/api/market-intelligence",
]
for i, api in enumerate(apis):
    col_i = i % 3
    row_i = i // 3
    add_rect(sl, Inches(0.5 + col_i*4.1), Inches(6.72 + row_i*0.35),
             Inches(3.8), Pt(20), BG_DARK)
    c = USED_COLOR if "used" in api or "optimize" in api else ACCENT_BLUE
    add_text(sl, api,
             Inches(0.55 + col_i*4.1), Inches(6.71 + row_i*0.35),
             Inches(3.7), Pt(22),
             font_size=10, color=c)

# ── 범례 ──
legend = [("신품 가격", ACCENT_BLUE), ("중고 시세", USED_COLOR),
          ("성능/커뮤니티", ACCENT_CYAN), ("AI 엔진", RGBColor(0x12, 0x30, 0x55)),
          ("결과", TAG_GREEN)]
for i, (lbl, col) in enumerate(legend):
    add_rect(sl, Inches(0.3 + i*2.4), Inches(7.3), Inches(0.22), Inches(0.22), col)
    add_text(sl, lbl, Inches(0.6 + i*2.4), Inches(7.27), Inches(2.0), Inches(0.3),
             font_size=10, color=TEXT_GRAY)


# ══════════════════════════════════════════════════════════════
#  SLIDE 6 — 견적 입력 모듈
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "04. 견적 입력 모듈", "Spec Input Module")

add_multiline(sl, [
    "✦ 입력 방식",
    "   • 견적서 파일 업로드 (텍스트 / PDF)",
    "   • 직접 텍스트 입력 지원",
], Inches(0.6), Inches(1.55), Inches(5.8), Inches(1.3), font_size=15, color=TEXT_WHITE)

add_multiline(sl, [
    "✦ LLM Parsing",
    "   • 부품명, 가격, 수량 자동 추출",
    "   • 비정형 견적서도 처리 가능",
], Inches(0.6), Inches(2.95), Inches(5.8), Inches(1.3), font_size=15, color=TEXT_WHITE)

add_multiline(sl, [
    "✦ 부품명 정규화",
    "   • 판매처별 표기 차이 통일",
    "   • 예: 'RTX 4070 Ti SUPER' ↔ 'GeForce RTX4070Ti Super'",
    "   • 정규화 후 신품/중고 시세 조회에 동일 키워드 활용",
], Inches(0.6), Inches(4.3), Inches(5.8), Inches(1.7), font_size=15, color=TEXT_WHITE)

add_rect(sl, Inches(7.0), Inches(1.55), Inches(5.8), Inches(5.5), BG_CARD)
add_rect(sl, Inches(7.0), Inches(1.55), Pt(4), Inches(5.5), ACCENT_CYAN)
add_text(sl, "입력 → 파싱 결과",
         Inches(7.2), Inches(1.6), Inches(5), Inches(0.45),
         font_size=14, bold=True, color=ACCENT_CYAN)

add_multiline(sl, [
    "[ 견적서 원문 ]",
    "AMD Ryzen 7 7800X3D ............... 459,000원",
    "ASUS ROG STRIX B650E-F ........... 389,000원",
    "Samsung DDR5-6000 16GB x2 ....... 128,000원",
    "RTX 4070 Ti SUPER 16GB ........... 899,000원",
], Inches(7.2), Inches(2.1), Inches(5.4), Inches(1.8), font_size=11, color=TEXT_GRAY)

add_rect(sl, Inches(7.2), Inches(3.85), Inches(5.2), Pt(1), DIVIDER)
add_multiline(sl, [
    "[ 파싱·정규화 결과 ]",
    "CPU  : Ryzen 7 7800X3D     → ₩459,000",
    "MB   : ASUS ROG B650E-F    → ₩389,000",
    "RAM  : Samsung DDR5 32GB   → ₩128,000",
    "GPU  : RTX 4070 Ti SUPER   → ₩899,000",
    "",
    "→ 신품/중고 시세 조회 키워드 생성 완료",
], Inches(7.2), Inches(4.0), Inches(5.4), Inches(2.8), font_size=11, color=TAG_GREEN)


# ══════════════════════════════════════════════════════════════
#  SLIDE 7 — 가격 분석: 신품 시세
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "05. 가격 분석 — 신품 시세", "New Product Price Analysis (Naver Shopping API)")

add_multiline(sl, [
    "✦ 데이터 소스",
    "   • 네이버 쇼핑 API",
    "   • 상위 20개 상품 기준 평균가 산출",
    "   • 최저가 / 평균가 / 최고가 실시간 조회",
    "",
    "✦ 오버페이율 계산",
    "   오버페이율 = 사용자 입력가 ÷ 평균 시세",
    "   • 1.05 이하 : 합리적 (최저가 근접)",
    "   • 1.05 ~ 1.20 : 주의 (소폭 비쌈)",
    "   • 1.20 초과 : 고위험 (재협상 권고)",
], Inches(0.6), Inches(1.55), Inches(5.8), Inches(3.5), font_size=14, color=TEXT_WHITE)

headers_p = ["부품", "입력가", "평균 시세", "오버페이율", "판정"]
col_x_p   = [Inches(6.8), Inches(8.6), Inches(9.9), Inches(11.1), Inches(12.4)]
cw_p      = [Inches(1.7), Inches(1.2), Inches(1.1), Inches(1.2),  Inches(0.9)]
row_h_p   = Inches(0.62)
data_p = [
    ["Ryzen 7 7800X3D",   "459,000", "449,000", "1.02", "✅"],
    ["RTX 4070 Ti SUPER", "899,000", "789,000", "1.14", "⚠️"],
    ["Samsung DDR5 32GB", "128,000", "132,000", "0.97", "✅"],
    ["ASUS B650E-F",      "389,000", "359,000", "1.08", "✅"],
]

sy = Inches(1.55)
for ci, (hdr, cx) in enumerate(zip(headers_p, col_x_p)):
    add_rect(sl, cx, sy, cw_p[ci] - Pt(4), row_h_p, ACCENT_BLUE)
    add_text(sl, hdr, cx, sy, cw_p[ci], row_h_p,
             font_size=12, bold=True, align=PP_ALIGN.CENTER)
for ri, row in enumerate(data_p):
    y = sy + row_h_p * (ri + 1)
    bg = BG_CARD if ri % 2 == 0 else RGBColor(0x12, 0x22, 0x32)
    for ci, cell in enumerate(row):
        add_rect(sl, col_x_p[ci], y, cw_p[ci] - Pt(4), row_h_p, bg)
        try:
            val = float(row[3])
            cc = TAG_RED if (ci == 3 and val > 1.1) else (
                 TAG_GREEN if ci == 4 and "✅" in cell else TEXT_GRAY)
        except:
            cc = TEXT_GRAY
        add_text(sl, cell, col_x_p[ci], y, cw_p[ci], row_h_p,
                 font_size=11, color=cc, align=PP_ALIGN.CENTER)

add_text(sl, "오버페이율 시각화",
         Inches(0.6), Inches(5.2), Inches(6), Inches(0.4),
         font_size=14, bold=True)
bar_items = [
    ("Ryzen 7 7800X3D", 1.02, TAG_GREEN),
    ("RTX 4070 Ti SUPER", 1.14, TAG_AMBER),
    ("Samsung DDR5 32GB", 0.97, TAG_GREEN),
    ("ASUS B650E-F", 1.08, TAG_GREEN),
]
for i, (name, ratio, color) in enumerate(bar_items):
    y = Inches(5.7 + i * 0.42)
    add_text(sl, name, Inches(0.6), y, Inches(2.5), Inches(0.38), font_size=11, color=TEXT_GRAY)
    add_rect(sl, Inches(3.2), y + Pt(4), Inches(5.0) * min(ratio/1.3, 1.0), Pt(16), color)
    add_text(sl, f"×{ratio:.2f}", Inches(3.2) + Inches(5.0)*min(ratio/1.3,1.0) + Pt(6),
             y, Inches(0.7), Inches(0.38), font_size=11, color=TEXT_WHITE)


# ══════════════════════════════════════════════════════════════
#  SLIDE 8 — 가격 분석: 중고 시세 (eBay)
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "06. 가격 분석 — 중고 시세 (eBay)", "Used Price Analysis via eBay Browse API")

# 중고 포인트 배너
add_rect(sl, Inches(0.5), Inches(1.52), Inches(12.3), Pt(3), USED_COLOR)

# 좌측 설명
add_multiline(sl, [
    "✦ 데이터 소스",
    "   • eBay Browse API (공식 OAuth 토큰)",
    "   • 폴백: 직접 스크래핑 (봇 차단 회피)",
    "   • 24시간 캐시로 불필요한 API 호출 방지",
    "",
    "✦ 수집 방식",
    "   • 조건: Used (중고) 상품만 필터링",
    "     conditionIds = {3000 | 2500 | 2000}",
    "   • USD → KRW 실시간 환율 변환",
    "     (기본 환율: $1 = ₩1,380)",
    "",
    "✦ 구현 파일",
    "   • backend/app/services/ebay_api.py",
    "   • backend/data/used_price_cache.json",
], Inches(0.6), Inches(1.65), Inches(5.8), Inches(5.1),
   font_size=13, color=TEXT_WHITE, spacing_after=3)

# 우측 예시 카드
add_rect(sl, Inches(7.0), Inches(1.55), Inches(5.8), Inches(5.7), BG_CARD)
add_rect(sl, Inches(7.0), Inches(1.55), Pt(4), Inches(5.7), USED_COLOR)
add_text(sl, "eBay 중고 시세 조회 결과 예시",
         Inches(7.2), Inches(1.6), Inches(5.5), Inches(0.45),
         font_size=14, bold=True, color=USED_COLOR)

used_data = [
    ("RTX 4070 Ti SUPER", "$420 USD", "₩579,600", "₩899,000", "▼ 35.4% 절감"),
    ("Ryzen 7 7800X3D",   "$280 USD", "₩386,400", "₩459,000", "▼ 15.8% 절감"),
    ("ASUS B650E-F",       "$195 USD", "₩269,100", "₩389,000", "▼ 30.8% 절감"),
    ("Samsung DDR5 32GB",  "$75 USD",  "₩103,500", "₩128,000", "▼ 19.1% 절감"),
]
sub_h = ["부품", "eBay 시세", "원화 환산", "신품가 비교", "절감액"]
sub_x = [Inches(7.1), Inches(8.7), Inches(9.9), Inches(11.0), Inches(12.0)]
sub_w = [Inches(1.5), Inches(1.1), Inches(1.0), Inches(0.95), Inches(1.1)]
sub_rh = Inches(0.57)

for ci, (hdr, cx) in enumerate(zip(sub_h, sub_x)):
    add_rect(sl, cx, Inches(2.15), sub_w[ci] - Pt(4), sub_rh, RGBColor(0x2A, 0x1A, 0x08))
    add_text(sl, hdr, cx, Inches(2.15), sub_w[ci], sub_rh,
             font_size=10, bold=True, color=USED_COLOR, align=PP_ALIGN.CENTER)

for ri, row in enumerate(used_data):
    y = Inches(2.15) + sub_rh * (ri + 1)
    bg = RGBColor(0x1A, 0x10, 0x05) if ri % 2 == 0 else RGBColor(0x12, 0x0C, 0x02)
    for ci, (cell, cx) in enumerate(zip(row, sub_x)):
        add_rect(sl, cx, y, sub_w[ci] - Pt(4), sub_rh, bg)
        cc = TAG_GREEN if ci == 4 else TEXT_GRAY
        add_text(sl, cell, cx, y, sub_w[ci], sub_rh,
                 font_size=10, color=cc, align=PP_ALIGN.CENTER)

add_rect(sl, Inches(7.2), Inches(4.55), Inches(5.3), Pt(1), DIVIDER)
add_text(sl, "총 견적 합계:",
         Inches(7.2), Inches(4.65), Inches(2.0), Inches(0.4),
         font_size=12, bold=True, color=TEXT_WHITE)
add_multiline(sl, [
    "신품 기준: ₩1,875,000",
    "중고 기준: ₩1,338,600",
    "예상 절감액: ₩536,400 (28.6% ↓)",
], Inches(7.2), Inches(5.05), Inches(5.3), Inches(1.5),
   font_size=13, color=TEXT_GRAY, spacing_after=4)
add_rect(sl, Inches(7.2), Inches(6.0), Inches(5.3), Pt(2), USED_COLOR)
add_text(sl, "★  동일 스펙을 약 53만 원 저렴하게 구성 가능",
         Inches(7.2), Inches(6.1), Inches(5.3), Inches(0.4),
         font_size=12, bold=True, color=USED_COLOR)

add_text(sl, "⚠  eBay = 해외 중고시장 기준 / 국내 당근마켓·번개장터는 향후 확장 예정",
         Inches(0.5), Inches(7.1), Inches(12), Inches(0.35),
         font_size=11, color=TAG_AMBER)


# ══════════════════════════════════════════════════════════════
#  SLIDE 9 — 중고가 기반 견적 최적화
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "07. 중고가 기반 견적 최적화", "Used Price Optimizer  |  /api/optimize-estimate")

add_rect(sl, Inches(0.5), Inches(1.52), Inches(12.3), Pt(3), USED_COLOR)

# 3단 카드
cards = [
    ("🔍 STEP 1\n중고가 수집",
     "• eBay API로 각 부품의\n  중고 시세 조회\n• 24h 캐시 활용\n• USD → KRW 변환",
     ACCENT_BLUE),
    ("💡 STEP 2\n절감 분석",
     "• 신품가 vs 중고가 비교\n• 부품별 절감 금액 계산\n• 절감율 순 정렬\n• 오래된 부품 우선 교체 제안",
     USED_COLOR),
    ("📋 STEP 3\n최적화 보고서",
     "• 교체 추천 목록 생성\n• 동일 예산 내 성능 향상 방안\n• LLM으로 쉬운 언어 설명\n• recommend.html 페이지 출력",
     TAG_GREEN),
]
for i, (title, desc, col) in enumerate(cards):
    x = Inches(0.5 + i * 4.2)
    add_rect(sl, x, Inches(1.65), Inches(3.9), Inches(3.5), BG_CARD)
    add_rect(sl, x, Inches(1.65), Inches(3.9), Pt(3), col)
    add_text(sl, title, x + Inches(0.1), Inches(1.72), Inches(3.7), Inches(0.85),
             font_size=14, bold=True, color=col)
    add_text(sl, desc, x + Inches(0.1), Inches(2.6), Inches(3.7), Inches(2.3),
             font_size=12, color=TEXT_GRAY)
    if i < 2:
        add_text(sl, "→", x + Inches(3.9), Inches(3.0), Inches(0.4), Inches(0.5),
                 font_size=20, bold=True, color=USED_COLOR, align=PP_ALIGN.CENTER)

# 최적화 결과 예시
add_rect(sl, Inches(0.5), Inches(5.3), Inches(12.3), Inches(1.9), BG_CARD)
add_rect(sl, Inches(0.5), Inches(5.3), Pt(4), Inches(1.9), USED_COLOR)
add_text(sl, "최적화 결과 예시 (RTX 4070 Ti SUPER 교체 제안)",
         Inches(0.7), Inches(5.35), Inches(12), Inches(0.45),
         font_size=13, bold=True, color=USED_COLOR)
add_multiline(sl, [
    "현재 견적 GPU:  RTX 4070 Ti SUPER 신품  →  ₩899,000",
    "중고 대안:      RTX 4070 Ti SUPER (eBay Used)  →  ₩579,600  (절감: ₩319,400 / 35.4%↓)",
    "절감 예산 활용: 남은 ₩319,400으로 32GB DDR5 추가 → 전체 견적 성능 향상",
], Inches(0.7), Inches(5.82), Inches(12.0), Inches(1.2),
   font_size=12, color=TEXT_GRAY, spacing_after=4)

add_text(sl, "⚠  중고품 컨디션(Used / Good / Acceptable) 필터 적용 — conditionIds 기반 품질 구분",
         Inches(0.5), Inches(7.2), Inches(12.3), Inches(0.3),
         font_size=10, color=TAG_AMBER)


# ══════════════════════════════════════════════════════════════
#  SLIDE 10 — 성능 분석 모듈
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "08. 성능 분석 모듈", "Performance Analysis Module")

add_multiline(sl, [
    "✦ 활용 데이터",
    "   • CPU Benchmark (cpu_benchmark.json, 564KB)",
    "   • GPU Benchmark (gpu_benchmark.json, 323KB)",
    "   • RAM 속도 및 용량",
    "   • SSD 읽기/쓰기 성능 지수",
    "",
    "✦ 분석 항목",
    "   • 부품별 성능 점수 계산",
    "   • CPU-GPU 밸런스 비율 평가",
    "   • 병목 가능성 감지",
    "   • 용도별 권장 스펙 대비 충족도",
], Inches(0.6), Inches(1.55), Inches(5.8), Inches(4.0), font_size=14, color=TEXT_WHITE)

add_rect(sl, Inches(7.0), Inches(1.55), Inches(5.8), Inches(5.6), BG_CARD)
add_text(sl, "성능 분석 결과 예시",
         Inches(7.2), Inches(1.6), Inches(5), Inches(0.45),
         font_size=14, bold=True, color=ACCENT_CYAN)

perf_items = [
    ("CPU 성능",       92, ACCENT_BLUE),
    ("GPU 성능",       85, ACCENT_CYAN),
    ("RAM 대역폭",     78, TAG_GREEN),
    ("SSD 속도",       88, TAG_GREEN),
    ("CPU-GPU 균형",   73, TAG_AMBER),
]
for i, (label, score, color) in enumerate(perf_items):
    y = Inches(2.15 + i * 0.9)
    add_text(sl, label, Inches(7.2), y, Inches(2.0), Inches(0.45),
             font_size=13, color=TEXT_GRAY)
    add_rect(sl, Inches(9.4), y + Pt(5), Inches(3.0) * score / 100, Pt(18), color)
    add_text(sl, f"{score}",
             Inches(9.4) + Inches(3.0)*score/100 + Pt(6), y,
             Inches(0.5), Inches(0.45), font_size=13, bold=True)
add_rect(sl, Inches(7.2), Inches(6.6), Inches(5.2), Pt(1), DIVIDER)
add_text(sl, "⚠  CPU-GPU 균형 73점 — GPU 업그레이드 또는 CPU 하향 검토 권장",
         Inches(7.2), Inches(6.7), Inches(5.5), Inches(0.5),
         font_size=11, color=TAG_AMBER)


# ══════════════════════════════════════════════════════════════
#  SLIDE 11 — 커뮤니티 데이터 수집
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "09. 커뮤니티 데이터 수집", "Community Data Collection")

steps = [
    ("1", "DC인사이드\n컴퓨터 본체 갤러리",
     "부품명 키워드로 게시글 수집\n(crawl_service.py)", ACCENT_BLUE),
    ("2", "텍스트\n전처리",
     "HTML 제거 / 욕설 필터링\n/ 중복 제거 / 토크나이징", BG_CARD),
    ("3", "감정분석\n입력 데이터",
     "부품별 언급 문장 추출\n→ 분석 입력 형식 변환", BG_CARD),
    ("4", "평판 점수\n생성",
     "긍정/부정 비율 → 0~100점\n부품별 평판 점수화", TAG_GREEN),
]
for i, (num, title, desc, color) in enumerate(steps):
    x = Inches(0.5 + i * 3.1)
    add_rect(sl, x, Inches(1.55), Inches(2.9), Inches(3.8), color)
    add_rect(sl, x, Inches(1.55), Inches(2.9), Pt(3), ACCENT_CYAN)
    add_text(sl, num, x + Inches(0.1), Inches(1.6), Inches(0.5), Inches(0.5),
             font_size=22, bold=True, color=ACCENT_CYAN)
    add_text(sl, title, x + Inches(0.1), Inches(2.05), Inches(2.7), Inches(0.8),
             font_size=13, bold=True)
    add_text(sl, desc, x + Inches(0.1), Inches(2.9), Inches(2.6), Inches(2.0),
             font_size=12, color=TEXT_GRAY)
    if i < 3:
        add_text(sl, "→", x + Inches(2.9), Inches(2.8), Inches(0.3), Inches(0.5),
                 font_size=20, bold=True, color=ACCENT_BLUE, align=PP_ALIGN.CENTER)

add_rect(sl, Inches(0.5), Inches(5.6), Inches(12.3), Inches(1.55), BG_CARD)
add_multiline(sl, [
    "수집 예시 — 'RTX 4070 Ti SUPER' 관련 DC인사이드 게시글:",
    "  💬  \"이 가격대에서 4070 Ti SUPER가 최고 가성비임. 발열도 생각보다 괜찮음\"",
    "  💬  \"근데 소비전력이 좀 높아서 700W PSU 필요함... 그 부분이 아쉬움\"",
], Inches(0.7), Inches(5.65), Inches(12), Inches(1.4), font_size=13, color=TEXT_GRAY)


# ══════════════════════════════════════════════════════════════
#  SLIDE 12 — AI 감정분석 모델
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "10. AI 감정분석 모델", "Sentiment Analysis (KoBERT-based)")

add_rect(sl, Inches(0.5), Inches(1.55), Inches(5.9), Inches(5.6), BG_CARD)
add_rect(sl, Inches(0.5), Inches(1.55), Pt(4), Inches(5.6), ACCENT_BLUE)
add_multiline(sl, [
    "✦ 모델 기반",
    "   KoBERT (한국어 BERT) 파인튜닝",
    "",
    "✦ 학습 데이터셋",
    "   • NSMC (네이버 영화 리뷰 감성 데이터)",
    "   • DC인사이드 게시글 크롤링 데이터",
    "",
    "✦ 분류 라벨",
    "   • 긍정 (부품 만족)",
    "   • 가격 불만",
    "   • 성능 불만",
    "   • 호환성 문제",
    "   • 중립",
    "",
    "✦ 출력",
    "   부품별 평판 점수 (0 ~ 100)",
], Inches(0.7), Inches(1.65), Inches(5.5), Inches(5.2),
   font_size=13, color=TEXT_GRAY, spacing_after=3)

add_text(sl, "분류 결과 예시 — RTX 4070 Ti SUPER",
         Inches(7.0), Inches(1.55), Inches(6.0), Inches(0.45),
         font_size=14, bold=True, color=ACCENT_CYAN)
label_items = [
    ("긍정",        72, TAG_GREEN),
    ("가격 불만",   11, TAG_RED),
    ("성능 불만",    8, TAG_AMBER),
    ("호환성 문제",  5, TAG_AMBER),
    ("중립",         4, TEXT_GRAY),
]
for i, (label, pct, color) in enumerate(label_items):
    y = Inches(2.1 + i * 0.82)
    add_text(sl, label, Inches(7.0), y, Inches(2.0), Inches(0.45),
             font_size=13, color=TEXT_WHITE)
    add_rect(sl, Inches(9.2), y + Pt(5), Inches(4.0)*pct/100, Pt(18), color)
    add_text(sl, f"{pct}%",
             Inches(9.2) + Inches(4.0)*pct/100 + Pt(6), y,
             Inches(0.6), Inches(0.45), font_size=13)

add_rect(sl, Inches(7.0), Inches(6.3), Inches(5.8), Pt(1), DIVIDER)
add_text(sl, "→ 종합 평판 점수: 74 / 100  (신뢰할 만한 선택)",
         Inches(7.0), Inches(6.4), Inches(6.0), Inches(0.45),
         font_size=13, bold=True, color=TAG_GREEN)


# ══════════════════════════════════════════════════════════════
#  SLIDE 13 — 3D 조립 시뮬레이션
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "11. 3D 조립 시뮬레이션", "3D Assembly Simulation — Three.js (Extension)")

add_rect(sl, Inches(0.5), Inches(1.55), Inches(12.3), Inches(0.5), BG_CARD)
add_text(sl, "⚠  확장 기능 — 현재 pc_3d_assembly/ 디렉토리에 기본 뷰어 구현, 완전한 인터랙션은 개발 예정",
         Inches(0.6), Inches(1.6), Inches(12), Inches(0.4),
         font_size=13, bold=True, color=TAG_AMBER)

features = [
    ("🖥️", "인터랙티브\n3D 뷰어",   "Three.js로 PC 케이스 및\n부품을 3D 렌더링"),
    ("🔧", "드래그 앤\n드롭 조립",   "사용자가 직접 부품을\n끼워보며 조립 학습"),
    ("⚡", "호환성\n시각적 경고",    "호환 불가 슬롯 시도 시\n빨간색 경고 표시"),
    ("🎓", "초보자\n학습 모드",      "단계별 가이드와 함께\n조립 과정 실습"),
]
for i, (icon, title, desc) in enumerate(features):
    x = Inches(0.5 + i * 3.1)
    add_rect(sl, x, Inches(2.3), Inches(2.9), Inches(3.5), BG_CARD)
    add_text(sl, icon, x, Inches(2.4), Inches(2.9), Inches(0.8),
             font_size=30, align=PP_ALIGN.CENTER)
    add_text(sl, title, x, Inches(3.2), Inches(2.9), Inches(0.8),
             font_size=14, bold=True, align=PP_ALIGN.CENTER)
    add_text(sl, desc, x + Inches(0.1), Inches(4.0), Inches(2.7), Inches(1.5),
             font_size=12, color=TEXT_GRAY, align=PP_ALIGN.CENTER)

add_rect(sl, Inches(0.5), Inches(6.0), Inches(12.3), Inches(1.1), BG_CARD)
add_text(sl, "기대 효과",
         Inches(0.7), Inches(6.05), Inches(3), Inches(0.4),
         font_size=14, bold=True, color=ACCENT_CYAN)
add_text(sl, "조립 경험 없는 초보자도 시뮬레이션으로 실수 없이 조립 가능  →  조립 서비스 비용 절감",
         Inches(0.7), Inches(6.5), Inches(12), Inches(0.5),
         font_size=13, color=TEXT_GRAY)


# ══════════════════════════════════════════════════════════════
#  SLIDE 14 — 확장 기능 및 미구현 기능
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "12. 확장 기능 및 미구현 기능", "Extensions & Future Work")

future_items = [
    ("🤖", "LLM 설명 생성",       "GPT / Claude 기반\n분석 결과를 쉬운 언어로 설명",      TAG_AMBER),
    ("📄", "문서 기반\n자동 추출", "견적서 PDF에서\n부품 정보 자동 파싱",                  TAG_AMBER),
    ("🛒", "국내 중고\n플랫폼",   "당근마켓 · 번개장터 · 중고나라\n시세 크롤링 확장",     TAG_RED),
    ("📈", "가격 예측",            "시계열 모델로\n부품 가격 트렌드 예측",                  TAG_RED),
    ("🎮", "FPS 시뮬레이션",      "게임별 예상 FPS\n성능 예측 모델",                       TAG_RED),
    ("🔄", "재평가 고도화",        "부품 교체 후\n재점수 자동 산출",                        TAG_AMBER),
]

status_map = {TAG_AMBER: "개발 중", TAG_RED: "미구현"}
for i, (icon, title, desc, sc) in enumerate(future_items):
    col, row = i % 3, i // 3
    x = Inches(0.5 + col * 4.2)
    y = Inches(1.6 + row * 2.65)
    add_rect(sl, x, y, Inches(3.9), Inches(2.35), BG_CARD)
    add_rect(sl, x, y, Inches(3.9), Pt(3), sc)
    add_text(sl, icon, x + Inches(0.1), y + Inches(0.1), Inches(0.7), Inches(0.6), font_size=22)
    add_text(sl, title, x + Inches(0.85), y + Inches(0.1), Inches(2.0), Inches(0.65),
             font_size=13, bold=True)
    add_rect(sl, x + Inches(2.65), y + Inches(0.12), Inches(1.15), Inches(0.35), sc)
    add_text(sl, status_map[sc],
             x + Inches(2.65), y + Inches(0.1), Inches(1.15), Inches(0.4),
             font_size=10, bold=True, align=PP_ALIGN.CENTER)
    add_text(sl, desc, x + Inches(0.1), y + Inches(0.8), Inches(3.6), Inches(1.4),
             font_size=12, color=TEXT_GRAY)

# 범례 + 국내 중고 플랫폼 강조
add_rect(sl, Inches(0.5), Inches(7.0), Inches(1.1), Pt(14), TAG_AMBER)
add_text(sl, "개발 중", Inches(1.7), Inches(6.97), Inches(1.5), Inches(0.4),
         font_size=12, color=TEXT_GRAY)
add_rect(sl, Inches(3.5), Inches(7.0), Inches(1.1), Pt(14), TAG_RED)
add_text(sl, "미구현 — 향후 로드맵", Inches(4.7), Inches(6.97), Inches(3), Inches(0.4),
         font_size=12, color=TEXT_GRAY)
add_text(sl, "★ 국내 중고 플랫폼 연동이 추가되면 eBay 대비 훨씬 정확한 국내 시세 제공 가능",
         Inches(7.5), Inches(6.97), Inches(5.5), Inches(0.4),
         font_size=11, color=USED_COLOR)


# ══════════════════════════════════════════════════════════════
#  SLIDE 15 — 마무리 / 결론
# ══════════════════════════════════════════════════════════════
sl = blank_slide(prs)
fill_bg(sl)
add_rect(sl, 0, 0, W, Inches(0.08), ACCENT_BLUE)
add_rect(sl, 0, H - Inches(0.08), W, Inches(0.08), USED_COLOR)

add_text(sl, "SpecCheck",
         Inches(1.0), Inches(1.5), Inches(11), Inches(1.4),
         font_size=56, bold=True, color=ACCENT_CYAN, align=PP_ALIGN.CENTER)
add_text(sl, "신품 가격 · 중고 시세 · 성능 · 호환성 · 커뮤니티 평가를 종합한\nAI 기반 PC 견적 의사결정 지원 시스템",
         Inches(1.0), Inches(2.9), Inches(11), Inches(1.2),
         font_size=19, align=PP_ALIGN.CENTER)
add_rect(sl, Inches(4.5), Inches(4.3), Inches(4.3), Pt(2), ACCENT_BLUE)

summary = [
    "단순 추천이 아닌 사용자 견적을 검증·설명하는 AI 시스템",
    "신품(네이버) + 중고(eBay) 이원화 가격으로 최적 예산 산출",
    "성능 병목, 커뮤니티 평판까지 한 번에 확인",
]
for i, s in enumerate(summary):
    add_text(sl, f"✔  {s}",
             Inches(1.5), Inches(4.75 + i*0.6), Inches(10), Inches(0.5),
             font_size=15, color=TEXT_GRAY, align=PP_ALIGN.CENTER)

add_text(sl, "감사합니다",
         Inches(1.0), Inches(6.5), Inches(11), Inches(0.7),
         font_size=28, bold=True, align=PP_ALIGN.CENTER)


# ── 저장 ──────────────────────────────────────────────────────
out_path = r"c:\Users\samsung\OneDrive\바탕 화면\졸작\SpecCheck\SpecCheck_발표.pptx"
prs.save(out_path)
print(f"저장 완료: {out_path}")
