"""Settings from the environment, falling back to the repo-root .env file."""
import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


@dataclass(frozen=True)
class Settings:
    paypal_env: str
    paypal_client_id: str
    paypal_client_secret: str
    paypal_webhook_id: str
    partner_email: str
    llm_provider: str
    gemini_api_key: str
    llm_daily_cap: int
    db_path: str
    frontend_dist: str

    @property
    def paypal_base_url(self) -> str:
        return "https://api-m.paypal.com" if self.paypal_env == "live" else "https://api-m.sandbox.paypal.com"


def load_settings() -> Settings:
    file_values = _read_dotenv(REPO_ROOT / ".env")

    def get(key: str, default: str = "") -> str:
        return os.environ.get(key) or file_values.get(key) or default

    env = get("PAYPAL_ENV", "sandbox")
    if env != "sandbox":
        # Kindtrail is a hackathon demo: it must never move real money.
        raise RuntimeError("Kindtrail only runs against the PayPal sandbox (PAYPAL_ENV=sandbox).")
    return Settings(
        paypal_env=env,
        paypal_client_id=get("PAYPAL_CLIENT_ID"),
        paypal_client_secret=get("PAYPAL_CLIENT_SECRET"),
        paypal_webhook_id=get("PAYPAL_WEBHOOK_ID"),
        # demo partner receives payouts in the sandbox personal account
        partner_email=get("PAYPAL_SANDBOX_PERSONAL_EMAIL"),
        llm_provider=get("LLM_PROVIDER", "gemini"),
        gemini_api_key=get("GEMINI_API_KEY"),
        llm_daily_cap=int(get("LLM_DAILY_CAP", "300")),
        db_path=get("DB_PATH", str(REPO_ROOT / "backend" / "kindtrail.db")),
        frontend_dist=get("FRONTEND_DIST", str(REPO_ROOT / "frontend" / "dist")),
    )
