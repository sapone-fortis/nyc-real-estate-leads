import requests
import pandas as pd
from datetime import datetime, timedelta
import os

DOB_URL = "https://data.cityofnewyork.us/resource/ic3t-wcy2.json"
CSV_FILE = "dob_permits.csv"

def pull_new_permits():
    """Pull new building permits with pagination."""
    
    # Get last update date from existing file
    last_date = None
    if os.path.exists(CSV_FILE):
        existing_df = pd.read_csv(CSV_FILE)
        print(f"Existing records: {len(existing_df)}")
        if 'latest_action_date' in existing_df.columns:
            last_date = pd.to_datetime(existing_df['latest_action_date'], errors='coerce').max()
            if pd.notna(last_date):
                last_date = last_date.strftime('%Y-%m-%dT%H:%M:%S')
    else:
        existing_df = pd.DataFrame()
        print("No existing file, will create new one")
    
    # Paginate through all results
    all_records = []
    offset = 0
    batch_size = 1000
    
    while True:
        params = {
            "$where": "job_type in('NB', 'A1', 'DM') AND latest_action_date > '2026-01-01'",
            "$limit": batch_size,
            "$offset": offset,
            "$order": "latest_action_date DESC"
        }
        
        # If we have existing data, only pull newer records
        if last_date and len(existing_df) > 0:
            params["$where"] = f"job_type in('NB', 'A1', 'DM') AND latest_action_date > '2026-01-01'"
        
        print(f"Pulling permits from DOB API (offset {offset})...")
        response = requests.get(DOB_URL, params=params)
        
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            break
        
        data = response.json()
        print(f"Fetched {len(data)} permits")
        
        if not data:
            break
            
        all_records.extend(data)
        
        if len(data) < batch_size:
            break
            
        offset += batch_size
    
    print(f"Total fetched: {len(all_records)} permits")
    
    if not all_records:
        print("No new permits found")
        return
    
    new_df = pd.DataFrame(all_records)
    
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
    
    # Merge with existing
    if len(existing_df) > 0 and 'job__' in existing_df.columns and 'job__' in new_df.columns:
        existing_jobs = set(existing_df['job__'].astype(str))
        new_records = new_df[~new_df['job__'].astype(str).isin(existing_jobs)]
        print(f"New records to add: {len(new_records)}")
        combined_df = pd.concat([existing_df, new_records], ignore_index=True)
    else:
        combined_df = new_df
    
    # Sort by units descending
    if 'proposed_dwelling_units' in combined_df.columns:
        combined_df['proposed_dwelling_units'] = pd.to_numeric(combined_df['proposed_dwelling_units'], errors='coerce').fillna(0)
        combined_df = combined_df.sort_values('proposed_dwelling_units', ascending=False)
    
    # Drop duplicates just in case
    if 'job__' in combined_df.columns:
        combined_df = combined_df.drop_duplicates(subset=['job__'], keep='first')
    
    combined_df.to_csv(CSV_FILE, index=False)
    print(f"Saved {len(combined_df)} total records to {CSV_FILE}")
    print(f"Last updated: {datetime.now().isoformat()}")

if __name__ == "__main__":
    pull_new_permits()