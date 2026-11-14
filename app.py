"""
Principia · Tutor de Física con IA
Backend Flask + Google Gemini (texto, imágenes y PDF).

Ejecución:
    pip install -r requirements.txt
    export GEMINI_API_KEY="tu_clave"      # Windows (PowerShell): $env:GEMINI_API_KEY="tu_clave"
    python app.py
"""
import io
import json
import logging
import os
import random
import re
import time

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

try:  # .env opcional
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from google import genai
from google.genai import types

from graficas import build_chart, sample_expression  # noqa: F401

# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # 15 MB por petición

# Orden de preferencia de modelos (los del nivel gratuito vigentes primero; los 2.5 solo siguen
# disponibles para claves que ya los usaban, por eso van al final). La app consulta a Google qué
# modelos admite TU clave y usa solo esos, así que no se rompe cuando Google retira alguno.
DEFAULT_MODELS = (
    "gemini-3.5-flash,gemini-3.1-flash-lite,gemini-3-flash-preview,"
    "gemini-3.5-flash-lite,gemini-2.5-flash,gemini-2.5-flash-lite"
)
_user_model = os.getenv("GEMINI_MODEL", "").strip()  # opcional: fuerza uno como primera opción
PREFERRED_MODELS = [m.strip() for m in os.getenv("GEMINI_MODELS", DEFAULT_MODELS).split(",") if m.strip()]
if _user_model:
    PREFERRED_MODELS = [_user_model] + [m for m in PREFERRED_MODELS if m != _user_model]
RETRIES = max(1, int(os.getenv("GEMINI_RETRIES", "3")))               # intentos por modelo
RETRY_BASE_DELAY = float(os.getenv("GEMINI_RETRY_DELAY", "1.5"))      # 1.5s, 3s, 6s...
APP_NAME = os.getenv("APP_NAME", "Principia")  # nombre que se muestra en la app
ALLOWED_FILES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "pdf": "application/pdf",
}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("principia")

try:
    from exportar import generar_codigo, generar_pdf, slug
except ImportError as _exc:  # faltan numpy / matplotlib / reportlab: la app sigue resolviendo, sin PDF ni código
    log.warning("Exportación desactivada (%s). Ejecuta:  pip install -r requirements.txt", _exc)

    def generar_codigo(_solucion):
        return ""

    def generar_pdf(_solucion):
        raise RuntimeError("Faltan librerías para crear el PDF. Cierra la app y ejecuta: pip install -r requirements.txt")

    def slug(_texto, default="ejercicio"):
        return default

_client = None


def get_client() -> genai.Client:
    """Crea el cliente de Gemini la primera vez que se necesita."""
    global _client
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip().strip("\"'")
    if not key or key.startswith("pega_aqui"):
        raise RuntimeError(
            "Falta la clave de Gemini. Define la variable de entorno GEMINI_API_KEY."
        )
    if _client is None:
        _client = genai.Client(api_key=key)
    return _client


# --------------------------------------------------------------------------- #
# Prompt del tutor
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = r"""
Eres un tutor experto de física (nivel bachillerato y universidad). Respondes SIEMPRE en español.
Recibes un ejercicio como texto, imagen (foto de un problema) o PDF. Devuelve ÚNICAMENTE un objeto
JSON válido (sin markdown, sin ```), con esta estructura exacta:

{
  "es_fisica": true,
  "titulo": "título corto del problema",
  "tema": "ej. Cinemática, Fricción, Energía, Ondas...",
  "resumen": "2-4 frases: qué se pide, los datos principales y qué se obtiene (sin repetir el desarrollo)",
  "datos": ["m = 5\\,\\text{kg}", "v_0 = 12\\,\\text{m/s}"],
  "formulas": ["F = m a", "v = v_0 + a t"],
  "pasos": [
    {"titulo": "Planteamiento", "explicacion": "texto con LaTeX entre $...$"}
  ],
  "resultado": "x = 24.5\\,\\text{m}",
  "grafica": {
    "tipo": "linea" | "barras" | "ninguna",
    "titulo": "texto plano",
    "eje_x": "Tiempo (s)",
    "eje_y": "Posición (m)",
    "x_min": 0,
    "x_max": 10,
    "series": [{"nombre": "x(t)", "expresion": "5*x + 0.5*2*x**2"}],
    "etiquetas": ["Peso", "Normal", "Fricción"],
    "valores": [49, 49, 12]
  },
  "uso_cotidiano": {
    "texto": "1-2 frases que conectan este tipo de ejercicio con la vida real",
    "ejemplos": ["ejemplo concreto 1", "ejemplo concreto 2", "ejemplo concreto 3"]
  },
  "aviso": ""
}

REGLAS
1. "datos", "formulas" y "resultado" van en LaTeX SIN delimitadores $ (la app los añade).
   En "resumen", "pasos[].explicacion" y "uso_cotidiano" usa $...$ para fórmulas en línea.
2. Dentro del JSON escapa cada barra invertida: escribe \\frac, \\text, \\cdot, \\theta.
3. Pasos: da la resolución COMPLETA, sin saltarte cálculos: identifica datos, elige fórmulas,
   despeja, sustituye con unidades y calcula.
   Verifica las operaciones aritméticas con cuidado. El resultado final lleva unidades correctas.
4. Gráfica automática según el ejercicio:
   - "linea": curvas como posición-tiempo, velocidad-tiempo, energía, trayectoria. La "expresion" es
     una expresión matemática en la variable x (el eje horizontal) con los NÚMEROS ya sustituidos
     (sin variables simbólicas). Solo puedes usar: + - * / ** %, paréntesis, pi, e y las funciones
     sin, cos, tan, asin, acos, atan, exp, log, log10, sqrt, abs, sinh, cosh, tanh, radians.
     Usa entre 1 y 3 series. Elige x_min y x_max que muestren bien el fenómeno.
   - "barras": para diagramas de fuerzas u otras magnitudes comparables (usa "etiquetas" y "valores"
     numéricos con la misma longitud, en una misma unidad).
   - "ninguna" si no tiene sentido graficar. En ese caso deja series/etiquetas/valores vacíos.
   Los textos de la gráfica son texto plano (puedes usar símbolos Unicode como θ, ω, ², ₀), NO LaTeX.
5. "uso_cotidiano": NO es un dato curioso. Explica en qué cosas o de qué manera se usa en el día a día
   el tipo de problema que se resolvió. Da 2 o 3 ejemplos concretos y cercanos (objetos, oficios, deportes,
   transporte, tecnología, hogar) de 1-2 frases cada uno, conectados con este ejercicio.
   Ej.: fricción -> calcular la distancia de frenado sirve para fijar límites de velocidad cerca de
   escuelas y para diseñar frenos y neumáticos.
6. Si la entrada NO es un problema o pregunta de física, pon "es_fisica": false, deja "pasos" vacío,
   "grafica.tipo": "ninguna" y explica brevemente en "aviso" que solo resuelves física.
7. Si faltan datos o la imagen es ilegible, indícalo en "aviso" y resuelve con supuestos claramente
   declarados (por ejemplo g = 9.8 m/s²).
"""

# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def parse_model_json(text: str) -> dict:
    """Convierte la respuesta de Gemini en dict, tolerando cercas ``` y escapes sueltos."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Escapa barras invertidas que no forman un escape JSON válido (p. ej. \theta, \cdot).
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", text)
        return json.loads(repaired)


def fix_tex(text) -> str:
    """Si Gemini olvidó duplicar una barra (\\theta, \\frac, \\beta, \\rho), JSON la lee como
    TAB / FF / BS / CR. Esos caracteres nunca son legítimos aquí: se devuelven a su forma LaTeX."""
    return (
        str(text)
        .replace("\t", "\\t")
        .replace("\f", "\\f")
        .replace("\b", "\\b")
        .replace("\r", "\\r")
    )


def clean_list(value, limit=20) -> list[str]:
    if not isinstance(value, list):
        return []
    return [fix_tex(v) for v in value if str(v).strip()][:limit]


def normalize_solution(data: dict) -> dict:
    steps = []
    for step in data.get("pasos") or []:
        if isinstance(step, dict):
            steps.append(
                {
                    "titulo": str(step.get("titulo") or ""),
                    "explicacion": fix_tex(step.get("explicacion") or ""),
                }
            )
        elif isinstance(step, str):
            steps.append({"titulo": "", "explicacion": fix_tex(step)})
    uso = data.get("uso_cotidiano") if isinstance(data.get("uso_cotidiano"), dict) else None
    if uso is None:  # compatibilidad con respuestas antiguas
        uso = data.get("sabias_que") if isinstance(data.get("sabias_que"), dict) else {}
    return {
        "es_fisica": bool(data.get("es_fisica", True)),
        "titulo": str(data.get("titulo") or "Resolución"),
        "tema": str(data.get("tema") or ""),
        "resumen": fix_tex(data.get("resumen") or ""),
        "datos": clean_list(data.get("datos")),
        "formulas": clean_list(data.get("formulas")),
        "pasos": steps[:15],
        "resultado": fix_tex(data.get("resultado") or ""),
        "grafica": build_chart(data.get("grafica")),
        "uso_cotidiano": {
            "texto": fix_tex(uso.get("texto") or ""),
            "ejemplos": [fix_tex(e) for e in (uso.get("ejemplos") or []) if str(e).strip()][:4]
            if isinstance(uso.get("ejemplos"), list) else [],
        },
        "aviso": str(data.get("aviso") or ""),
    }


# --------------------------------------------------------------------------- #
# Llamada resiliente a Gemini: reintentos con backoff exponencial + modelo de respaldo
# --------------------------------------------------------------------------- #
TRANSIENT_CODES = {429, 500, 502, 503, 504}  # saturación, cuota por minuto, fallos temporales


def _error_code(exc: Exception):
    """Código HTTP de un error del SDK (google-genai expone .code), o None si no es de API."""
    code = getattr(exc, "code", None)
    return code if isinstance(code, int) else None


def is_transient(exc: Exception) -> bool:
    """True si vale la pena reintentar (503 saturado, 429, 5xx, cortes de red)."""
    code = _error_code(exc)
    if code is not None:
        return code in TRANSIENT_CODES
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


def friendly_api_error(exc: Exception) -> tuple[str, int]:
    """Convierte el error técnico de la API en un mensaje limpio para el usuario."""
    code = _error_code(exc)
    if code == 503:
        return ("El modelo de IA está saturado en este momento. Espera unos segundos y "
                "vuelve a enviar tu problema."), 503
    if code == 429:
        return ("Se alcanzó el límite de consultas por ahora. Espera un momento e "
                "inténtalo de nuevo."), 429
    text = str(exc).lower()
    if code in (401, 403) or "api key not valid" in text or "api_key_invalid" in text:
        return "La clave de Gemini no es válida o no tiene permiso. Revisa GEMINI_API_KEY en tu .env.", 500
    if code == 404:
        return ("Ningún modelo de Gemini está disponible con tu clave. Crea una clave nueva en "
                "Google AI Studio o abre /api/modelos para ver qué modelos admite."), 500
    if code == 400:
        return "La IA no pudo procesar esta entrada. Prueba con otra foto, PDF o texto.", 400
    return "La IA no pudo responder ahora mismo. Intenta de nuevo en unos segundos.", 502


_NOT_TEXT_MODELS = ("tts", "live", "image", "embedding", "audio", "robotics", "gemma", "veo", "imagen", "aqa")
_model_chain = None  # caché de la lista de modelos utilizables con esta clave


def discover_models() -> list[str]:
    """Pregunta a Google qué modelos admite esta clave y los ordena según PREFERRED_MODELS.
    Si el listado falla (sin red, etc.), usa la lista de preferencia tal cual."""
    global _model_chain
    if _model_chain is not None:
        return _model_chain
    try:
        available = set()
        for m in get_client().models.list():
            actions = getattr(m, "supported_actions", None)
            if actions is not None and "generateContent" not in actions:
                continue
            available.add((getattr(m, "name", "") or "").removeprefix("models/"))
        available.discard("")
    except RuntimeError:
        raise  # falta la clave: que lo vea el usuario
    except Exception as exc:
        log.warning("No pude listar los modelos (%s); uso la lista por defecto.", exc)
        _model_chain = list(PREFERRED_MODELS)
        return _model_chain

    chain = [m for m in PREFERRED_MODELS if m in available]
    # Si ninguno de los preferidos existe, usa cualquier modelo flash de texto, los más nuevos primero
    extra = sorted(
        (m for m in available
         if m.startswith("gemini-") and "flash" in m and not any(w in m for w in _NOT_TEXT_MODELS)
         and m not in chain),
        reverse=True,
    )
    chain += extra if not chain else extra[:2]
    if not chain:
        chain = list(PREFERRED_MODELS)
    log.info("Modelos que se usarán (en orden): %s", chain)
    _model_chain = chain
    return chain


def generate_with_resilience(parts) -> str:
    """Devuelve el texto de Gemini.
    - 503/5xx/red: reintenta con backoff exponencial y luego pasa al siguiente modelo.
    - 404 (modelo retirado o no disponible para tu clave) y 429 (la cuota es por modelo):
      pasa de inmediato al siguiente modelo.
    - Clave inválida o entrada rechazada: falla enseguida."""
    global _model_chain
    client = get_client()
    contents = [types.Content(role="user", parts=parts)]
    last_exc = None
    chain = discover_models()

    for model in chain:
        kwargs = dict(system_instruction=SYSTEM_PROMPT, response_mime_type="application/json")
        if not model.startswith("gemini-3"):  # Gemini 3 recomienda dejar la temperatura por defecto
            kwargs["temperature"] = 0.3
        config = types.GenerateContentConfig(**kwargs)

        for attempt in range(1, RETRIES + 1):
            try:
                response = client.models.generate_content(model=model, contents=contents, config=config)
                if not (response.text or "").strip():
                    raise ConnectionError("respuesta vacía del modelo")  # se trata como temporal
                if model != chain[0]:
                    log.info("Respondió el modelo alternativo: %s", model)
                return response.text
            except Exception as exc:
                last_exc = exc
                code = _error_code(exc)
                if code in (404, 429):
                    log.warning("%s no disponible ahora (%s); pruebo el siguiente modelo", model, code)
                    break
                if not is_transient(exc):
                    raise  # clave inválida, entrada rechazada, etc.: reintentar no ayuda
                if attempt < RETRIES:
                    wait = RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    log.warning("%s falló (%s). Reintento %d/%d en %.1fs", model, exc, attempt, RETRIES - 1, wait)
                    time.sleep(wait)
                else:
                    log.warning("%s agotó %d intentos; paso al siguiente modelo", model, RETRIES)

    if _error_code(last_exc) == 404:
        _model_chain = None  # que la próxima vez vuelva a consultar qué modelos hay
    raise last_exc


@app.get("/api/modelos")
def modelos():
    """Diagnóstico: modelos que la app usará con tu clave (ábrelo en el navegador)."""
    try:
        return jsonify(modelos_en_uso=discover_models(), preferencia=PREFERRED_MODELS)
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 500


# --------------------------------------------------------------------------- #
# Rutas
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return render_template("index.html", app_name=APP_NAME)


@app.post("/api/resolver")
def resolver():
    texto = (request.form.get("texto") or "").strip()
    archivo = request.files.get("archivo")
    tiene_archivo = bool(archivo and archivo.filename)

    if not texto and not tiene_archivo:
        return jsonify(error="Escribe un problema o adjunta una foto o PDF."), 400
    if len(texto) > 4000:
        return jsonify(error="El texto es demasiado largo (máx. 4000 caracteres)."), 400

    parts = []
    if tiene_archivo:
        ext = archivo.filename.rsplit(".", 1)[-1].lower() if "." in archivo.filename else ""
        if ext not in ALLOWED_FILES:
            return jsonify(error="Formato no admitido. Usa PNG, JPG, WEBP o PDF."), 400
        data = archivo.read()  # se procesa en memoria; no se guarda nada en disco
        if not data:
            return jsonify(error="El archivo está vacío."), 400
        if ext == "pdf" and not data.startswith(b"%PDF"):
            return jsonify(error="El archivo no parece ser un PDF válido."), 400
        parts.append(types.Part.from_bytes(data=data, mime_type=ALLOWED_FILES[ext]))

    parts.append(
        types.Part.from_text(
            text=texto or "Resuelve el ejercicio de física que aparece en el archivo adjunto."
        )
    )

    try:
        solution = normalize_solution(parse_model_json(generate_with_resilience(parts)))
        solution["codigo"] = generar_codigo(solution)
    except RuntimeError as exc:  # clave ausente
        return jsonify(error=str(exc)), 500
    except (json.JSONDecodeError, TypeError, AttributeError) as exc:
        log.exception("Respuesta de Gemini no interpretable: %s", exc)
        return jsonify(error="No pude interpretar la respuesta de la IA. Intenta de nuevo."), 502
    except Exception as exc:  # errores de red/cuota/API (ya reintentados)
        log.error("Gemini falló tras reintentos y respaldo: %s", exc)
        message, status = friendly_api_error(exc)
        return jsonify(error=message, reintentable=status in (429, 503, 504)), status

    return jsonify(solution)


@app.post("/api/pdf")
def descargar_pdf():
    """Genera el PDF del ejercicio a partir de la solución que ya tiene el navegador.
    Se vuelve a validar todo (incluida la gráfica) antes de usarlo."""
    if (request.content_length or 0) > 400_000:
        return jsonify(error="La solución es demasiado grande para exportarla."), 413
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="No hay ninguna solución que exportar."), 400
    solution = normalize_solution(data)
    if not solution["es_fisica"] or not (solution["pasos"] or solution["resultado"]):
        return jsonify(error="No hay una resolución para exportar."), 400
    try:
        pdf = generar_pdf(solution)
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 500
    except Exception as exc:
        log.exception("No se pudo generar el PDF: %s", exc)
        return jsonify(error="No pude generar el PDF. Intenta de nuevo."), 500
    return send_file(
        io.BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
        download_name=f"principia-{slug(solution['titulo'])}.pdf",
    )


@app.errorhandler(RequestEntityTooLarge)
def too_large(_):
    return jsonify(error="El archivo supera el límite de 15 MB."), 413


if __name__ == "__main__":
    # host 0.0.0.0 permite abrir la app desde el celular en la misma red Wi-Fi.
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
