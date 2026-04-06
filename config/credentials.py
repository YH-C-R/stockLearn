import os

from dotenv import load_dotenv

load_dotenv()

# FinMind API token — set in .env as FINMIND_TOKEN=<your_token>
# Leave blank to use the unauthenticated (rate-limited) endpoint.
FINMIND_TOKEN: str = os.getenv("FINMIND_TOKEN", "")
