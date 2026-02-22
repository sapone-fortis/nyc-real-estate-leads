import requests
import pandas as pd
from datetime import datetime
import os

DOB_URL = "https://data.cityofnewyork.us/resource/ic3t-wcy2.json"
CSV_FILE = "dob_permits.csv"

def pull_new_permits():
    """Pull new building permits and merge with existing data."""
    
    params = {
        "$where": "job_type = 'NB'",
        "$limit": 1000,
        "$order": "latest_action_date DESC"
    }
    
    print(f"Pulling permits from DOB API...")
    response = requests.get(DOB_URL, params=params)
    
    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        return
    
    data = response.json()
    print(f"Fetched {len(data)} permits from API")
    
    if not data:
        print("No data returned")
        return
    
    # Create dataframe from API response
    new_df = pd.DataFrame(data)
    
    # Keep useful columns
    cols = ['job__', 'borough', 'house__', 'street_name', 'zip', 
            'initial_cost', 'building_class', 'proposed_dwelling_units',
            'owner_s_business_name', 'owner_s_first_name', 'owner_s_last_name',
            'owner_sphone__', 'job_description', 'latest_action_date']
    
    available = [c for c in cols if c in new_df.columns]
    new_df = new_df[available]
    
    # Create address column
    if 'house__' in new_df.columns and 'street_name' in new_df.columns:
        new_df['address'] = new_df['house__'].fillna('') + ' ' + new_df['street_name'].fillna('')
        new_df['address'] = new_df['address'].str.strip()
    
    # Borough mapping
    borough_map = {'1': 'Manhattan', '2': 'Bronx', '3': 'Brooklyn', '4': 'Queens', '5': 'Staten Island'}
    if 'borough' in new_df.columns:
        new_df['borough'] = new_df['borough'].map(borough_map).fillna(new_df['borough'])
    
    # Load existing data if it exists
    if os.path.exists(CSV_FILE):
        existing_df = pd.read_csv(CSV_FILE)
        print(f"Existing records: {len(existing_df)}")
        
        # Merge: use job__ as unique identifier
        if 'job__' in existing_df.columns and 'job__' in new_df.columns:
            # Find new records not in existing
            existing_jobs = set(existing_df['job__'].astype(str))
            new_records = new_df[~new_df['job__'].astype(str).isin(existing_jobs)]
            
            print(f"New records to add: {len(new_records)}")
            
            # Combine
            combined_df = pd.concat([existing_df, new_records], ignore_index=True)
        else:
            combined_df = new_df
    else:
        combined_df = new_df
        print("No existing file, creating new one")
    
    # Sort by units descending
    if 'proposed_dwelling_units' in combined_df.columns:
        combined_df['proposed_dwelling_units'] = pd.to_numeric(combined_df['proposed_dwelling_units'], errors='coerce').fillna(0)
        combined_df = combined_df.sort_values('proposed_dwelling_units', ascending=False)
    
    # Save
    combined_df.to_csv(CSV_FILE, index=False)
    print(f"Saved {len(combined_df)} total records to {CSV_FILE}")
    
    # Log timestamp
    print(f"Last updated: {datetime.now().isoformat()}")

if __name__ == "__main__":
    pull_new_permits()