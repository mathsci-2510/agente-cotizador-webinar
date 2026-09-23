# app/config.py
import os
import logging
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"


def _running_on_aws() -> bool:
    """ECS/App Runner/Lambda set AWS_EXECUTION_ENV; en ese caso las variables
    de entorno ya las provee el runtime (o Secrets Manager) y no hay .env local."""
    return bool((os.getenv("AWS_EXECUTION_ENV") or "").strip())


if not _running_on_aws() and ENV_PATH.exists():
    load_dotenv(ENV_PATH)
    logger.info("Local .env loaded: %s", ENV_PATH)


def _clean(name: str, default: str = "") -> str:
    return (os.getenv(name) or default or "").strip()


@dataclass(frozen=True)
class Settings:
    app_name: str
    openai_api_key: str
    openai_model: str
    openai_temperature: float
    checkpoint_db_path: str
    quotes_dir: str
    company_display_name: str
    redis_url: str


settings = Settings(
    app_name=_clean("APP_NAME", "Agente Cotizador de Equipos Médicos"),
    openai_api_key=_clean("OPENAI_API_KEY", ""),
    openai_model=_clean("OPENAI_MODEL", "gpt-4o-mini"),
    openai_temperature=float(_clean("OPENAI_TEMPERATURE", "0.2")),
    checkpoint_db_path=_clean("CHECKPOINT_DB_PATH", str(BASE_DIR / "data" / "checkpoints.sqlite")),
    quotes_dir=_clean("QUOTES_DIR", str(BASE_DIR / "data" / "quotes")),
    company_display_name=_clean("COMPANY_DISPLAY_NAME", "Demo Webinar - Agentes de IA en la Nube"),
    redis_url=_clean("REDIS_URL", ""),
)

OFFLINE_MODE = not bool(settings.openai_api_key)

if OFFLINE_MODE:
    logger.warning(
        "OPENAI_API_KEY no configurada: el agente arrancará en MODO OFFLINE "
        "(extracción de datos basada en reglas). Útil como respaldo de "
        "contingencia para la demo en vivo del webinar."
    )
