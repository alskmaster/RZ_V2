# rz_debug.py
from __future__ import annotations
import functools
import json
import logging
import os
import time
import uuid
from typing import Any, Callable, Iterable, Mapping, Optional

# Sinaliza se Flask está instalado e acessível
_HAS_FLASK = False
try:
    from flask import g, request, has_request_context, has_app_context  # type: ignore
    _HAS_FLASK = True
except Exception:
    _HAS_FLASK = False

# -----------------------------------------------------------------------------
# Configuração de logging
# -----------------------------------------------------------------------------
def _coerce_level(value: str | None, default: int = logging.INFO) -> int:
    if not value:
        return default
    try:
        return getattr(logging, value.upper())
    except Exception:
        return default

_LOG_LEVEL = _coerce_level(os.getenv("RZ_LOG_LEVEL"), logging.INFO)

logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s"
)
LOG = logging.getLogger("rz")

# Quais chaves de kwargs/params nunca devem ser logadas
_DEFAULT_EXCLUDE = {"password", "passwd", "secret", "token", "apikey", "api_key", "authorization", "cookie"}
_EXCLUDE = _DEFAULT_EXCLUDE | {
    k.strip().lower() for k in os.getenv("RZ_LOG_EXCLUDE_KEYS", "").split(",") if k.strip()
}

# -----------------------------------------------------------------------------
# Utilidades
# -----------------------------------------------------------------------------
def _safe_serialize(value: Any, max_len: int = 1000) -> Any:
    """
    Serializa valores para log sem explodir o tamanho nem vazar segredos.
    """
    try:
        s = json.dumps(value, ensure_ascii=False, default=str)
        if len(s) > max_len:
            return s[:max_len] + f"...(+{len(s)-max_len} bytes)"
        return json.loads(s)
    except Exception:
        text = str(value)
        return text[:max_len] + ("..." if len(text) > max_len else "")

def _scrub_mapping(d: Mapping[str, Any]) -> Mapping[str, Any]:
    cleaned = {}
    for k, v in d.items():
        if k.lower() in _EXCLUDE:
            cleaned[k] = "***redacted***"
        else:
            cleaned[k] = v
    return cleaned

def _now_ms() -> float:
    return time.perf_counter() * 1000.0

def _get_request_id() -> Optional[str]:
    """
    Obtém um request id se (e somente se) houver contexto válido de Flask.
    Nunca levanta RuntimeError fora de contexto.
    """
    if not _HAS_FLASK:
        return None
    try:
        if not (has_app_context() and has_request_context()):
            return None
        rid = getattr(g, "request_id", None)
        if rid:
            return rid
        try:
            return request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID")
        except Exception:
            return None
    except Exception:
        # Qualquer erro de contexto/cabecalho retorna None
        return None

# -----------------------------------------------------------------------------
# Decorador principal
# -----------------------------------------------------------------------------
def with_debug(name: Optional[str] = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Instrumenta a função com logs de entrada/saída/erro, tempo e correlação.
    Seguro para uso fora de request (ex.: código de startup).
    """
    def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        label = name or f"{fn.__module__}.{fn.__name__}"

        @functools.wraps(fn)
        def inner(*args: Any, **kwargs: Any) -> Any:
            rid = _get_request_id() or uuid.uuid4().hex[:8]
            t0 = _now_ms()

            # Log de entrada (kwargs saneados)
            try:
                kw_log = _safe_serialize(_scrub_mapping(kwargs))
            except Exception:
                kw_log = "<unable to serialize kwargs>"

            LOG.debug(_safe_serialize({
                "rid": rid,
                "evt": "enter",
                "fn": label,
                "kwargs": kw_log if kw_log else {},
                "args_len": len(args)
            }))

            out = None
            try:
                out = fn(*args, **kwargs)
                return out
            except Exception as e:
                LOG.exception(_safe_serialize({
                    "rid": rid,
                    "evt": "error",
                    "fn": label,
                    "err": str(e.__class__.__name__),
                    "msg": str(e),
                }))
                raise
            finally:
                dt = max(_now_ms() - t0, 0.01)
                result_info = {"type": None, "len": None}
                try:
                    if isinstance(out, (str, bytes)):
                        result_info = {"type": type(out).__name__, "len": len(out)}
                    elif isinstance(out, Iterable) and not isinstance(out, (dict, set)):
                        result_info = {"type": type(out).__name__, "len": None}
                    else:
                        result_info = {"type": type(out).__name__, "len": None}
                except Exception:
                    pass

                LOG.debug(_safe_serialize({
                    "rid": rid,
                    "evt": "exit",
                    "fn": label,
                    "ms": round(dt, 2),
                    "result": result_info
                }))

        return inner
    return _wrap

# -----------------------------------------------------------------------------
# Integração com Flask (correlation-id por requisição)
# -----------------------------------------------------------------------------
def install_request_context(app) -> None:
    """
    Registra before/after_request para gerar/propagar request_id e
    adicionar informações úteis no log.
    Chamar dentro da factory: install_request_context(app)
    """
    if not _HAS_FLASK:
        LOG.warning("install_request_context chamado sem Flask disponível.")
        return

    @app.before_request
    def _before():
        rid = None
        try:
            rid = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID")
        except Exception:
            rid = None
        try:
            g.request_id = rid or uuid.uuid4().hex
        except Exception:
            # Em caso extremo, seguimos sem g
            pass

        LOG.debug(_safe_serialize({
            "rid": getattr(g, "request_id", None),
            "evt": "http_enter",
            "method": getattr(request, "method", None),
            "path": getattr(request, "path", None),
            "remote": getattr(request, "remote_addr", None),
        }))

    @app.after_request
    def _after(response):
        try:
            response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        except Exception:
            pass
        LOG.debug(_safe_serialize({
            "rid": getattr(g, "request_id", None),
            "evt": "http_exit",
            "status": getattr(response, "status_code", None),
            "len": response.calculate_content_length() if hasattr(response, "calculate_content_length") else None,
        }))
        return response
