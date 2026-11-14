"""
Principia · exportación
- generar_codigo(solucion): script de Python (numpy + matplotlib) que muestra la gráfica del ejercicio.
- generar_pdf(solucion):    PDF descargable con resumen, pasos, resultado, gráfica, código y uso cotidiano.

Ninguna parte ejecuta código escrito por el modelo: el script se arma con una plantilla fija y las
expresiones ya validadas por graficas.py.
"""
import datetime
import io
import os
import re
import struct
import textwrap
import unicodedata
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")  # sin ventanas: el servidor solo genera imágenes
import numpy as np
from matplotlib import get_data_path
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from graficas import sample_expression, to_numpy

matplotlib.rcParams["mathtext.fontset"] = "stix"  # fórmulas con aspecto de libro de texto

# --------------------------------------------------------------------------- #
# LaTeX -> texto plano con Unicode (para el PDF y los comentarios del código)
# --------------------------------------------------------------------------- #
_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν",
    "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
_SYMBOLS = {
    "cdot": "·", "times": "×", "pm": "±", "mp": "∓", "approx": "≈", "neq": "≠", "ne": "≠", "leq": "≤", "le": "≤",
    "geq": "≥", "ge": "≥", "infty": "∞", "to": "→", "rightarrow": "→", "Rightarrow": "⇒", "implies": "⇒",
    "leftarrow": "←", "leftrightarrow": "↔", "circ": "°", "degree": "°", "propto": "∝", "partial": "∂",
    "nabla": "∇", "int": "∫", "oint": "∮", "sum": "Σ", "prod": "∏", "ldots": "…", "dots": "…", "cdots": "⋯",
    "sim": "∼", "equiv": "≡", "angle": "∠", "perp": "⊥", "parallel": "||", "hbar": "ħ", "ell": "ℓ",
    "quad": "  ", "qquad": "    ", "min": "mín", "max": "máx", "cos": "cos", "sin": "sin", "tan": "tan",
    "ln": "ln", "log": "log", "exp": "exp", "lim": "lím", "Delta": "Δ", "bullet": "•",
}
_SINGLE = {",": " ", ";": " ", ":": " ", " ": " ", "!": "", "\\": " ", "%": "%", "&": "&", "#": "#"}
_SUP = dict(zip("0123456789+-=()nix", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱˣ"))
_SUP.update({"°": "°", "∘": "°", "′": "′", "″": "″"})
_SUB = dict(zip("0123456789+-=()aeoxhklmnpst", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜ"))
_ACCENTS = {"vec": "\u20d7", "hat": "\u0302", "bar": "\u0304", "overline": "\u0304", "dot": "\u0307", "ddot": "\u0308"}
_TEXT_MACROS = r"text|textbf|textit|mathrm|mathbf|mathit|operatorname|mbox|boldsymbol|bm|mathcal"


def _find_group(s: str, i: int):
    """s[i] debe ser '{'. Devuelve (contenido, índice siguiente al '}' que cierra)."""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
    return s[i + 1:], len(s)


def _wrap_term(t: str) -> str:
    return t if re.fullmatch(r"[\w.·°]+", t) else f"({t})"


def _convert_scripts(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c in "^_":
            j = i + 1
            if j < len(s) and s[j] == "{":
                content, k = _find_group(s, j)
            elif j < len(s):
                content, k = s[j], j + 1
            else:
                content, k = "", j
            content = content.strip()
            table = _SUP if c == "^" else _SUB
            mapped = [table.get(ch) for ch in content]
            if content and None not in mapped:
                out.append("".join(mapped))
            elif re.fullmatch(r"[^\s(){}\[\]]+", content or ""):
                out.append(c + content)
            else:
                out.append(f"{c}({content})" if content else "")
            i = k
        else:
            out.append(c)
            i += 1
    return "".join(out)


def latex_to_plain(tex: str) -> str:
    """Convierte LaTeX sencillo a texto legible con Unicode: \\frac{a}{b} -> a/b, v_0^2 -> v₀², etc."""
    s = str(tex).replace("$", "")
    s = re.sub(r"\\(?:left|right|displaystyle|bigg|Bigg|big|Big)\b\s*", "", s)
    s = s.replace("\\!", "")

    for _ in range(30):  # fracciones (admite anidadas)
        m = re.search(r"\\[dt]?frac\s*\{", s)
        if not m:
            break
        a, i = _find_group(s, m.end() - 1)
        j = i
        while j < len(s) and s[j] == " ":
            j += 1
        if j < len(s) and s[j] == "{":
            b, k = _find_group(s, j)
        else:
            b, k = "", i
        frac = f"{_wrap_term(latex_to_plain(a))}/{_wrap_term(latex_to_plain(b))}"
        if k < len(s) and (s[k].isalnum() or s[k] in "\\("):  # evita ambigüedad: (1/2)mv²
            frac = f"({frac})"
        s = s[:m.start()] + frac + s[k:]

    for _ in range(30):  # raíces
        m = re.search(r"\\sqrt\s*(\[[^\]]*\])?\s*\{", s)
        if not m:
            break
        a, k = _find_group(s, m.end() - 1)
        a = latex_to_plain(a)
        idx = m.group(1)
        pre = "√" if not idx else {"[3]": "∛", "[4]": "∜"}.get(idx, idx[1:-1] + "√")
        s = s[:m.start()] + pre + (a if re.fullmatch(r"[\w.]+", a) else f"({a})") + s[k:]

    for name, mark in _ACCENTS.items():  # \vec{F} -> F⃗
        for _ in range(30):
            m = re.search(r"\\" + name + r"\s*\{", s)
            if not m:
                break
            a, k = _find_group(s, m.end() - 1)
            s = s[:m.start()] + a + mark + s[k:]

    for _ in range(30):  # \text{kg} -> kg
        m = re.search(r"\\(?:" + _TEXT_MACROS + r")\s*\{", s)
        if not m:
            break
        a, k = _find_group(s, m.end() - 1)
        s = s[:m.start()] + a + s[k:]

    def macro(m):
        name = m.group(1)
        if name in _GREEK:
            return _GREEK[name]
        return _SYMBOLS.get(name, name)

    s = re.sub(r"\\([a-zA-Z]+)", macro, s)
    s = re.sub(r"\\(.)", lambda m: _SINGLE.get(m.group(1), m.group(1)), s)
    s = _convert_scripts(s)
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"[ \t]+", " ", s).strip()


def texto_plano(text: str) -> str:
    """Texto con $...$ incrustados -> texto plano en una sola línea."""
    parts = re.split(r"(\$\$.+?\$\$|\$.+?\$)", str(text), flags=re.S)
    out = []
    for p in parts:
        out.append(latex_to_plain(p) if p.startswith("$") or "\\" in p else p)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _inline_xml(text: str) -> str:
    """Para Paragraph de reportlab: escapa XML y pone en cursiva los tramos matemáticos."""
    parts = re.split(r"(\$\$.+?\$\$|\$.+?\$)", str(text), flags=re.S)
    out = []
    for p in parts:
        if p.startswith("$"):
            out.append("<i>" + escape(latex_to_plain(p)) + "</i>")
        elif "\\" in p:
            out.append(escape(latex_to_plain(p)))
        else:
            out.append(escape(p))
    return "".join(out).replace("\n", "<br/>")


def slug(text: str, default="ejercicio") -> str:
    s = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return (s[:50] or default)


# --------------------------------------------------------------------------- #
# Imágenes: fórmulas (mathtext) y gráfica
# --------------------------------------------------------------------------- #
_MATH_DPI = 300
_PALETTE = ["#2b59c3", "#d9822b", "#2f9e6e", "#8e44ad", "#c0392b"]


def _to_mathtext(tex: str) -> str:
    s = str(tex).replace("$", "").strip()
    s = re.sub(r"\\(?:left|right|displaystyle|bigg|Bigg|big|Big)\b\s*", "", s)
    s = re.sub(r"\\[dt]?frac", r"\\dfrac", s)
    s = re.sub(
        r"\\(?:text|textbf|textit|mathrm|operatorname|mbox)\s*\{([^{}]*)\}",
        lambda m: r"\mathrm{" + m.group(1).replace(" ", r"\ ") + "}",
        s,
    )
    s = re.sub(r"\\(?:bm|boldsymbol)\s*\{([^{}]*)\}", r"\\mathbf{\1}", s)
    s = s.replace(r"\;", r"\ ").replace(r"\:", r"\ ").replace(r"\degree", r"^\circ")
    s = s.replace(r"\implies", r"\Rightarrow").replace(r"\boxed", "")
    return s


def _png_size(png: bytes):
    w, h = struct.unpack(">II", png[16:24])
    return w, h


def _render_math(tex: str, size: float):
    fig = Figure(figsize=(1, 1), dpi=_MATH_DPI)
    FigureCanvasAgg(fig)
    fig.text(0, 0, f"${_to_mathtext(tex)}$", fontsize=size, color="#14161f")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_MATH_DPI, bbox_inches="tight", pad_inches=0.03, transparent=True)
    return buf.getvalue()


def _math_flowable(tex: str, size: float, max_width: float, st):
    """Fórmula como imagen nítida; si matplotlib no la entiende, cae a texto plano."""
    try:
        png = _render_math(tex, size)
        wpx, hpx = _png_size(png)
        w, h = wpx * 72 / _MATH_DPI, hpx * 72 / _MATH_DPI
        if w > max_width:
            h *= max_width / w
            w = max_width
        return Image(io.BytesIO(png), width=w, height=h)
    except Exception:
        return Paragraph(escape(latex_to_plain(tex)), st["fallback"])


def _chart_png(chart: dict) -> bytes:
    fig = Figure(figsize=(7.6, 4.3), dpi=200)
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    if chart["tipo"] == "barras":
        bars = ax.bar(chart["etiquetas"], chart["valores"], color=[_PALETTE[i % 5] for i in range(len(chart["valores"]))])
        ax.bar_label(bars, fmt="%.4g", padding=3, fontsize=9)
        ax.axhline(0, color="#555555", linewidth=0.8)
    else:
        for i, serie in enumerate(chart["series"]):
            pts = sample_expression(serie["expresion"], chart["x_min"], chart["x_max"], 400)
            xs = [p["x"] for p in pts]
            ys = [np.nan if p["y"] is None else p["y"] for p in pts]
            ax.plot(xs, ys, linewidth=2.2, color=_PALETTE[i % 5], label=serie["nombre"])
        if len(chart["series"]) > 1:
            ax.legend(frameon=False)
    if chart.get("titulo"):
        ax.set_title(chart["titulo"], fontsize=12, fontweight="bold")
    ax.set_xlabel(chart.get("eje_x", ""))
    ax.set_ylabel(chart.get("eje_y", ""))
    ax.grid(True, alpha=0.3)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Código Python ejecutable
# --------------------------------------------------------------------------- #
def _num_txt(v: float) -> str:
    return repr(round(float(v), 6))


def generar_codigo(sol: dict) -> str:
    """Script de Python (numpy + matplotlib) que muestra la gráfica del ejercicio."""
    g = sol.get("grafica")
    L = []

    def comment(text, prefix="# ", width=86):
        for ln in textwrap.wrap(str(text), width) or [""]:
            L.append(prefix + ln)

    L.append("# " + "=" * 72)
    comment("Principia · " + texto_plano(sol.get("titulo", "Ejercicio")))
    L.append("# " + "=" * 72)
    if sol.get("resumen"):
        comment("Resumen: " + texto_plano(sol["resumen"]))
    if sol.get("datos"):
        L.append("#")
        L.append("# Datos:")
        for d in sol["datos"]:
            comment(latex_to_plain(d), prefix="#   ")
    if sol.get("resultado"):
        L.append("#")
        comment("Resultado: " + latex_to_plain(sol["resultado"]))
    L += ["#", "# Requisitos:  pip install numpy matplotlib", "# Ejecución:   python grafica.py", ""]

    resultado_txt = latex_to_plain(sol.get("resultado", "")) or "ver resolución"

    if g and g.get("tipo") == "linea":
        L += ["import numpy as np", "import matplotlib.pyplot as plt", ""]
        L.append(f"x = np.linspace({_num_txt(g['x_min'])}, {_num_txt(g['x_max'])}, 500)")
        L.append("")
        L.append('with np.errstate(all="ignore"):  # evita avisos si una expresión no existe en algún punto')
        for i, serie in enumerate(g["series"], 1):
            expr, uses_x = to_numpy(serie["expresion"])
            rhs = expr if uses_x else f"np.full_like(x, {expr})"
            L.append(f"    y{i} = {rhs}")
        L += ["", f"print('Resultado:', {resultado_txt!r})", ""]
        L.append("fig, ax = plt.subplots(figsize=(9, 5.5))")
        for i, serie in enumerate(g["series"], 1):
            L.append(f"ax.plot(x, y{i}, linewidth=2.2, label={serie['nombre']!r})")
        if g.get("titulo"):
            L.append(f"ax.set_title({g['titulo']!r}, fontsize=14, fontweight='bold')")
        L.append(f"ax.set_xlabel({g.get('eje_x', '')!r})")
        L.append(f"ax.set_ylabel({g.get('eje_y', '')!r})")
        L.append("ax.grid(True, alpha=0.3)")
        if len(g["series"]) > 1:
            L.append("ax.legend()")
        L += ["fig.tight_layout()", "", "# Para guardar la imagen:  fig.savefig('grafica.png', dpi=200)", "plt.show()"]
    elif g and g.get("tipo") == "barras":
        L += ["import matplotlib.pyplot as plt", ""]
        L.append(f"etiquetas = {list(g['etiquetas'])!r}")
        L.append(f"valores = {[round(float(v), 6) for v in g['valores']]!r}")
        L += ["", f"print('Resultado:', {resultado_txt!r})", ""]
        L.append("fig, ax = plt.subplots(figsize=(9, 5.5))")
        L.append("barras = ax.bar(etiquetas, valores, color=[f'C{i}' for i in range(len(valores))])")
        L.append("ax.bar_label(barras, fmt='%.4g', padding=3)")
        L.append("ax.axhline(0, color='gray', linewidth=0.8)")
        if g.get("titulo"):
            L.append(f"ax.set_title({g['titulo']!r}, fontsize=14, fontweight='bold')")
        L.append(f"ax.set_xlabel({g.get('eje_x', '')!r})")
        L.append(f"ax.set_ylabel({g.get('eje_y', '')!r})")
        L.append("ax.grid(True, axis='y', alpha=0.3)")
        L += ["fig.tight_layout()", "", "# Para guardar la imagen:  fig.savefig('grafica.png', dpi=200)", "plt.show()"]
    else:
        L += ["# Este ejercicio no necesita gráfica: el script solo muestra el resultado.", ""]
        L.append(f"print('Resultado:', {resultado_txt!r})")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
_fonts_ready = False
NAVY = colors.HexColor("#0b1026")
CREAM = colors.HexColor("#efe3c0")
GOLD = colors.HexColor("#8a6d1d")
MUTED = colors.HexColor("#596380")
INK = colors.HexColor("#14161f")


def _register_fonts():
    global _fonts_ready
    if _fonts_ready:
        return
    base = os.path.join(get_data_path(), "fonts", "ttf")
    for name, file in [
        ("DV", "DejaVuSans.ttf"), ("DV-B", "DejaVuSans-Bold.ttf"), ("DV-I", "DejaVuSans-Oblique.ttf"),
        ("DV-BI", "DejaVuSans-BoldOblique.ttf"), ("DVS-B", "DejaVuSerif-Bold.ttf"), ("DVM", "DejaVuSansMono.ttf"),
    ]:
        pdfmetrics.registerFont(TTFont(name, os.path.join(base, file)))
    pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV-I", boldItalic="DV-BI")
    _fonts_ready = True


def _styles():
    return {
        "brand": ParagraphStyle("brand", fontName="DVS-B", fontSize=20, leading=24, textColor=CREAM),
        "brand_r": ParagraphStyle("brand_r", fontName="DV", fontSize=8, leading=11, textColor=CREAM, alignment=TA_RIGHT),
        "tema": ParagraphStyle("tema", fontName="DV-B", fontSize=8.5, leading=11, textColor=GOLD, spaceBefore=6),
        "title": ParagraphStyle("title", fontName="DVS-B", fontSize=19, leading=24, textColor=INK, spaceAfter=2),
        "h2": ParagraphStyle("h2", fontName="DV-B", fontSize=8.5, leading=11, textColor=MUTED),
        "body": ParagraphStyle("body", fontName="DV", fontSize=9.6, leading=14, textColor=INK),
        "step_t": ParagraphStyle("step_t", fontName="DV-B", fontSize=10, leading=13, textColor=INK, spaceAfter=1),
        "num": ParagraphStyle("num", fontName="DV-B", fontSize=10, leading=12, textColor=CREAM, alignment=TA_CENTER),
        "warn": ParagraphStyle("warn", fontName="DV-I", fontSize=9, leading=12.5, textColor=colors.HexColor("#6b4e00")),
        "fallback": ParagraphStyle("fallback", fontName="DV", fontSize=10, leading=13, textColor=INK),
        "bullet": ParagraphStyle("bullet", fontName="DV", fontSize=9.6, leading=14, textColor=INK, leftIndent=11, bulletIndent=1),
        "code": ParagraphStyle(
            "code", fontName="DVM", fontSize=7.3, leading=9.1, textColor=colors.HexColor("#1d2433"),
            backColor=colors.HexColor("#f4f1e6"), borderColor=colors.HexColor("#d8d2bb"), borderWidth=0.5,
            borderPadding=6, leftIndent=6, rightIndent=6,
        ),
    }


def _section(title: str, first, st):
    """Encabezado de sección que nunca queda solo al final de una página."""
    head = [
        Spacer(1, 5 * mm),
        Paragraph(title.upper(), st["h2"]),
        HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#c9c2a8"), spaceBefore=1, spaceAfter=2.5 * mm),
    ]
    return KeepTogether(head + ([first] if first is not None else []))


def _grid(items, cols, width, size, st):
    cells = [_math_flowable(x, size, width / cols - 7 * mm, st) for x in items]
    rows = []
    for i in range(0, len(cells), cols):
        row = cells[i:i + cols]
        rows.append(row + [""] * (cols - len(row)))
    t = Table(rows, colWidths=[width / cols] * cols)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f6ee")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e1dcc8")),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#e1dcc8")),
    ]))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    w, _ = A4
    canvas.setStrokeColor(colors.HexColor("#c9c2a8"))
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 13 * mm, w - 18 * mm, 13 * mm)
    canvas.setFont("DV", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 8.5 * mm, "Principia · Tutor de física con IA")
    canvas.drawRightString(w - 18 * mm, 8.5 * mm, f"Página {doc.page}")
    canvas.restoreState()


def generar_pdf(sol: dict) -> bytes:
    """PDF descargable del ejercicio resuelto. `sol` es la solución ya normalizada."""
    _register_fonts()
    st = _styles()
    page_w, _ = A4
    margin = 18 * mm
    cw = page_w - 2 * margin

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=15 * mm, bottomMargin=20 * mm,
        title=texto_plano(sol.get("titulo", "Ejercicio")), author="Principia",
    )
    story = []

    band = Table(
        [[Paragraph("Principia", st["brand"]),
          Paragraph("Tutor de física con IA<br/>" + datetime.date.today().strftime("%d/%m/%Y"), st["brand_r"])]],
        colWidths=[cw * 0.55, cw * 0.45],
    )
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(band)
    if sol.get("tema"):
        story.append(Paragraph(escape(texto_plano(sol["tema"])).upper(), st["tema"]))
    story.append(Spacer(1, 1.5 * mm))
    story.append(Paragraph(escape(texto_plano(sol.get("titulo", "Ejercicio"))), st["title"]))

    if sol.get("aviso"):
        warn = Table([[Paragraph(_inline_xml(sol["aviso"]), st["warn"])]], colWidths=[cw])
        warn.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff4d6")),
            ("LINEBEFORE", (0, 0), (0, 0), 3, colors.HexColor("#e0a800")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story += [Spacer(1, 2 * mm), warn]

    if sol.get("resumen"):
        story.append(_section("Resumen del ejercicio", Paragraph(_inline_xml(sol["resumen"]), st["body"]), st))

    if sol.get("datos"):
        story.append(_section("Datos", _grid(sol["datos"], 2, cw, 12, st), st))

    if sol.get("formulas"):
        story.append(_section("Fórmulas", _grid(sol["formulas"], 2, cw, 12, st), st))

    if sol.get("pasos"):
        story.append(_section("Resolución paso a paso", None, st))
        for i, paso in enumerate(sol["pasos"], 1):
            cell = []
            if paso.get("titulo"):
                cell.append(Paragraph(escape(texto_plano(paso["titulo"])), st["step_t"]))
            cell.append(Paragraph(_inline_xml(paso.get("explicacion", "")), st["body"]))
            row = Table([[Paragraph(str(i), st["num"]), cell]], colWidths=[9 * mm, cw - 9 * mm])
            row.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (0, 0), 6), ("LEFTPADDING", (1, 0), (1, 0), 8),
                ("TOPPADDING", (1, 0), (1, 0), 4), ("BOTTOMPADDING", (1, 0), (1, 0), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e1dcc8")),
            ]))
            story.append(row)

    if sol.get("resultado"):
        box = Table([[_math_flowable(sol["resultado"], 16, cw - 16 * mm, st)]], colWidths=[cw])
        box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6efd6")),
            ("LINEBEFORE", (0, 0), (0, 0), 3.5, GOLD),
            ("LEFTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]))
        story.append(_section("Resultado", box, st))

    grafica = sol.get("grafica")
    if grafica:
        try:
            png = _chart_png(grafica)
            wpx, hpx = _png_size(png)
            w = cw
            h = w * hpx / wpx
            if h > 88 * mm:
                w, h = w * 88 * mm / h, 88 * mm
            story.append(_section("Gráfica", Image(io.BytesIO(png), width=w, height=h), st))
        except Exception:
            story.append(_section("Gráfica", Paragraph("No se pudo dibujar la gráfica de este ejercicio.", st["body"]), st))

    codigo = generar_codigo(sol)
    wrapped = []
    for line in codigo.rstrip("\n").split("\n"):
        wrapped += textwrap.wrap(line, 100, subsequent_indent="      ", drop_whitespace=False) or [""]
    story.append(_section("Código Python (ejecútalo para ver la gráfica)", Spacer(1, 2 * mm), st))
    story.append(Preformatted("\n".join(wrapped), st["code"]))

    uso = sol.get("uso_cotidiano") or {}
    if uso.get("texto") or uso.get("ejemplos"):
        items = []
        if uso.get("texto"):
            items.append(Paragraph(_inline_xml(uso["texto"]), st["body"]))
            items.append(Spacer(1, 1.5 * mm))
        for ej in uso.get("ejemplos", []):
            items.append(Paragraph(_inline_xml(ej), st["bullet"], bulletText="•"))
            items.append(Spacer(1, 1 * mm))
        box = Table([[items]], colWidths=[cw])
        box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fbf3dc")),
            ("LINEBEFORE", (0, 0), (0, 0), 3.5, colors.HexColor("#e0a800")),
            ("LEFTPADDING", (0, 0), (-1, -1), 11), ("RIGHTPADDING", (0, 0), (-1, -1), 11),
            ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(_section("En el día a día", box, st))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
