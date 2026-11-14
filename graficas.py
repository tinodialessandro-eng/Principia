"""
Principia · gráficas
- Valida la gráfica que propone Gemini y calcula sus puntos con un evaluador seguro (sin eval).
- Traduce las expresiones a código NumPy para el script de Python descargable.
"""
import ast
import logging
import math
import operator

log = logging.getLogger("principia")

# --------------------------------------------------------------------------- #
# Evaluador seguro de expresiones
# --------------------------------------------------------------------------- #
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_FUNCS = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "exp": math.exp,
    "log": math.log,
    "log10": math.log10,
    "sqrt": math.sqrt,
    "abs": abs,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "radians": math.radians,
}
_CONSTS = {"pi": math.pi, "e": math.e}

# Nombre de cada función en NumPy
_NUMPY_NAMES = {
    "asin": "arcsin", "acos": "arccos", "atan": "arctan",
}


def _ev(node, x: float) -> float:
    if isinstance(node, ast.Expression):
        return _ev(node.body, x)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        raise ValueError("constante no permitida")
    if isinstance(node, ast.Name):
        if node.id == "x":
            return x
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ValueError(f"nombre no permitido: {node.id}")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _ev(node.left, x), _ev(node.right, x)
        if isinstance(node.op, ast.Pow) and abs(right) > 12:
            raise ValueError("exponente demasiado grande")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _ev(node.operand, x)
        return -value if isinstance(node.op, ast.USub) else value
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCS
        and not node.keywords
        and len(node.args) == 1
    ):
        return _FUNCS[node.func.id](_ev(node.args[0], x))
    raise ValueError("expresión no permitida")


def clean_expression(expr: str) -> str:
    """Normaliza símbolos habituales (^, ×, ·) a sintaxis de Python."""
    return str(expr).strip().replace("^", "**").replace("×", "*").replace("·", "*")


def sample_expression(expr: str, x_min: float, x_max: float, n: int = 120):
    """Evalúa `expr` en n puntos de [x_min, x_max]. Puntos inválidos -> y = None."""
    expr = clean_expression(expr)
    if not expr or len(expr) > 200:
        raise ValueError("expresión vacía o demasiado larga")
    tree = ast.parse(expr, mode="eval")
    step = (x_max - x_min) / (n - 1)
    points = []
    for i in range(n):
        x = x_min + i * step
        try:
            y = _ev(tree, x)
            y = round(y, 5) if math.isfinite(y) else None
        except (ValueError, ZeroDivisionError, OverflowError):
            y = None
        points.append({"x": round(x, 5), "y": y})
    if all(p["y"] is None for p in points):
        raise ValueError("la expresión no produjo valores")
    return points


def to_numpy(expr: str) -> tuple[str, bool]:
    """Traduce una expresión ya validada a código NumPy.
    Devuelve (texto, usa_x). Ej.: 'sin(2*pi*x)' -> 'np.sin(2*np.pi*x)'."""
    tree = ast.parse(clean_expression(expr), mode="eval")
    uses_x = False

    class _ToNumpy(ast.NodeTransformer):
        def visit_Name(self, node):
            nonlocal uses_x
            if node.id == "x":
                uses_x = True
                return node
            if node.id in _CONSTS:
                return ast.copy_location(
                    ast.Attribute(value=ast.Name(id="np", ctx=ast.Load()), attr=node.id, ctx=ast.Load()), node
                )
            return node

        def visit_Call(self, node):
            self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
                name = _NUMPY_NAMES.get(node.func.id, node.func.id)
                node.func = ast.Attribute(value=ast.Name(id="np", ctx=ast.Load()), attr=name, ctx=ast.Load())
            return node

    new = ast.fix_missing_locations(_ToNumpy().visit(tree))
    return ast.unparse(new.body), uses_x


# --------------------------------------------------------------------------- #
# Validación de la gráfica propuesta por el modelo
# --------------------------------------------------------------------------- #
def _num(value, default=None):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _txt(value, limit=120) -> str:
    """Texto plano para títulos/ejes: sin $ ni barras (evita que matplotlib lo lea como mathtext)."""
    return str(value or "").replace("$", "").replace("\\", "").strip()[:limit]


def build_chart(raw) -> dict | None:
    """Valida y completa la gráfica que propone Gemini. Devuelve None si no hay nada que dibujar.
    La salida conserva las claves de entrada (tipo, x_min, x_max, expresion, etiquetas, valores),
    así que puede volver a validarse tal cual (lo usa la descarga del PDF)."""
    if not isinstance(raw, dict):
        return None
    tipo = raw.get("tipo")
    base = {
        "tipo": tipo,
        "titulo": _txt(raw.get("titulo")),
        "eje_x": _txt(raw.get("eje_x")),
        "eje_y": _txt(raw.get("eje_y")),
    }

    if tipo == "barras":
        labels = raw.get("etiquetas") or []
        values = [_num(v) for v in (raw.get("valores") or [])]
        if not labels or len(labels) != len(values) or None in values or len(labels) > 12:
            return None
        return {**base, "etiquetas": [_txt(l, 40) for l in labels], "valores": values}

    if tipo == "linea":
        x_min = _num(raw.get("x_min"), 0.0)
        x_max = _num(raw.get("x_max"), 10.0)
        if x_max <= x_min:
            x_min, x_max = 0.0, 10.0
        series = []
        for serie in (raw.get("series") or [])[:3]:
            try:
                expr = clean_expression(serie.get("expresion", ""))
                points = sample_expression(expr, x_min, x_max)
            except (ValueError, SyntaxError, AttributeError) as exc:
                log.warning("Serie descartada (%s): %s", exc, serie)
                continue
            series.append({"nombre": _txt(serie.get("nombre") or "serie", 40), "expresion": expr, "puntos": points})
        if not series:
            return None
        return {**base, "x_min": x_min, "x_max": x_max, "series": series}

    return None
