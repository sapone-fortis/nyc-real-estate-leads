import requests
import pandas as pd

DOB_URL = "https://data.cityofnewyork.us/resource/ic3t-wcy2.json"

params = {
    "$where": "job_type = 'NB' AND initial_cost > '0'",
    "$limit": 500,
    "$order": "latest_action_date DESC"
}

print("Pulling new building permits with cost data...")
response = requests.get(DOB_URL, params=params)
print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    print(f"Found {len(data)} permits")
    
    if data:
        df = pd.DataFrame(data)
        
        # Keep useful columns
        cols = ['job__', 'borough', 'house__', 'street_name', 'zip', 
                'initial_cost', 'building_class', 'proposed_dwelling_units',
                'owner_s_business_name', 'owner_s_first_name', 'owner_s_last_name',
                'owner_sphone__', 'job_description', 'latest_action_date']
        
        available = [c for c in cols if c in df.columns]
        df = df[available]
        
        # Create address column
        if 'house__' in df.columns and 'street_name' in df.columns:
            df['address'] = df['house__'].fillna('') + ' ' + df['street_name'].fillna('')
        
        # Convert cost to number for sorting
        df['cost_numeric'] = df['initial_cost'].replace('[\$,]', '', regex=True).astype(float)
        df = df.sort_values('cost_numeric', ascending=False)
        
        df.to_csv('dob_permits.csv', index=False)
        print("Saved to dob_permits.csv")
        
        print(f"\nTop 10 by cost:")
        print(df[['address', 'borough', 'initial_cost', 'owner_s_business_name']].head(10).to_string())
else:
    print(f"Error: {response.text}")