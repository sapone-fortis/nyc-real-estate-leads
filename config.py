import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# NYC Open Data endpoints
DOB_PERMITS_URL = "https://data.cityofnewyork.us/resource/ic3t-wcy2.json"
ACRIS_MASTER_URL = "https://data.cityofnewyork.us/resource/bnx9-e6tj.json"
ACRIS_PARTIES_URL = "https://data.cityofnewyork.us/resource/636b-3b5g.json"
PLUTO_URL = "https://data.cityofnewyork.us/resource/64uk-42ks.json"

# Filter settings
MIN_PROJECT_COST = 25_000_000
MAX_PROJECT_COST = 200_000_000