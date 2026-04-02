import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

# --- API Keys ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

if not GEMINI_API_KEY:
    raise EnvironmentError("GEMINI_API_KEY is missing from .env")
if not TELEGRAM_BOT_TOKEN:
    raise EnvironmentError("TELEGRAM_BOT_TOKEN is missing from .env")

# --- Paths ---
RESUMES_DIR = ROOT_DIR / "resumes"
EXCEL_PATH = ROOT_DIR / "jobs.xlsx"

# --- Search settings ---
LOCATIONS = ["United States", "USA", "Remote"]

# Minimum Gemini match score (0–100) to include a job in the output
MIN_MATCH_SCORE = 60

# How many days back to search for job postings
SEARCH_DAYS_BACK = 14

# Max jobs to score per run (to control Gemini API usage)
MAX_JOBS_TO_SCORE = 100

# --- Gemini model ---
GEMINI_MODEL = "gemini-2.0-flash"           # primary: resume parse + search grounding
GEMINI_FLASH_MODEL = "gemini-2.0-flash-lite"  # cheaper model for bulk job scoring

# --- Schedule ---
SCHEDULE_HOUR = 9    # 9 AM local time
SCHEDULE_MINUTE = 0

# --- Excel column names (order matters) ---
EXCEL_COLUMNS = [
    "Job Title",
    "Company",
    "Location",
    "Source",
    "URL",
    "Date Posted",
    "Match Score",
    "Matched Skills",
    "Missing Skills",
    "Salary",
    "Date Found",
    "Status",
    "Notes",
]

# A curated list of well-known companies using Greenhouse.
# This list is used for direct API discovery without burning Gemini quota.
# Add more slugs as needed: visit https://boards.greenhouse.io/{slug}
GREENHOUSE_COMPANY_SLUGS = [
    "openai", "anthropic", "scale", "cohere", "mistral",
    "huggingface", "stability", "together", "modal", "replicate",
    "databricks", "snowflake", "pinecone", "weaviate", "qdrant",
    "langchain", "llamaindex", "weights-biases", "wandb",
    "deepmind", "inflection", "adept", "cohere", "runway",
    "midjourney", "perplexity", "cognition", "characterai",
    "pika", "kling", "luma", "elevenabs", "heygen",
    "groq", "cerebras", "sambanova", "tenstorrent",
    "palantir", "c3-ai", "datarobot", "h2oai",
    "stripe", "brex", "ramp", "mercury", "column",
    "figma", "notion", "linear", "vercel", "railway",
    "supabase", "planetscale", "neon", "turso",
    "temporal", "inngest", "trigger",
    "retool", "airplane", "baseten",
    "harvey", "lexi", "ironclad", "spellbook",
    "cursor", "codeium", "tabnine",
]

# Ashby company slugs for direct API polling
ASHBY_COMPANY_SLUGS = [
    "openai", "anthropic", "scale-ai", "cohere", "mistral-ai",
    "hugging-face", "stability-ai", "together-ai",
    "perplexity-ai", "cognition-ai", "character-ai",
    "groq", "cerebras-systems",
    "harvey-ai", "lexi-legal",
    "cursor", "codeium",
    "linear", "vercel", "supabase", "neon",
    "retool", "baseten",
]
