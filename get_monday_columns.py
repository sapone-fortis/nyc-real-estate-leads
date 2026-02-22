import requests
import os
from dotenv import load_dotenv

load_dotenv()

MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
MONDAY_BOARD_ID = os.getenv("MONDAY_BOARD_ID")

url = "https://api.monday.com/v2"
headers = {
    "Authorization": MONDAY_API_KEY,
    "Content-Type": "application/json"
}

query = '''
query {
    boards(ids: %s) {
        columns {
            id
            title
            type
        }
    }
}
''' % MONDAY_BOARD_ID

response = requests.post(url, headers=headers, json={"query": query})
print(response.json())