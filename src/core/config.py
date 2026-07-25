from pathlib import Path

# ==========================================
# Configuration Layer
# ==========================================
CONFIG = {
    "BIR_TARGET_URL": "https://www.bir.gov.ph/collection-statistics",
    "DBM_SAAODB_URL": "https://www.dbm.gov.ph/index.php/statement-of-appropriations-allotments-obligations-disbursements-and-balances",
    "GAA_REPO_ID": "bettergovph/gaa",
    "RAW_DATA_DIR": Path("data/raw"),
    "BIR_RAW_DIR": Path("data/raw/tax"),
    "GAA_RAW_DIR": Path("data/raw/gaa"),
    "SAAODB_RAW_DIR": Path("data/raw/saaodb"),
    "LOG_FILE": Path("logs/ingestion.log"),
    "MANIFEST_FILE": Path("data/raw/manifest.json"),
    "TIMEOUT": 15,
    "MAX_RETRIES": 5,
    "CHUNK_SIZE": 8192,
    # Crawl rate limiting (seconds)
    "DELAY_RANGE": (3, 7),
    "SAAODB_SOURCE_KEY": "ph_saaodb",
    "HEADERS": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
    },
}