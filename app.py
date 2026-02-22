import streamlit as st
import pandas as pd
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
MONDAY_BOARD_ID = os.getenv("MONDAY_BOARD_ID")

st.set_page_config(page_title="NYC Real Estate Leads", layout="wide")

st.title("NYC New Building Permits")
st.markdown("Filter and browse potential borrowers from DOB permit filings")

# Load data
df = pd.read_csv('dob_permits.csv')

# Clean up column names for display
df = df.rename(columns={
    'owner_s_business_name': 'Business Name',
    'owner_s_first_name': 'First Name',
    'owner_s_last_name': 'Last Name',
    'owner_sphone__': 'Phone',
    'proposed_dwelling_units': 'Units',
    'building_class': 'Class',
    'job_description': 'Description'
})

# Sidebar filters
st.sidebar.header("Filters")

search = st.sidebar.text_input("Search (name, address, etc.)")

boroughs = ['All'] + sorted(df['borough'].dropna().unique().tolist())
selected_borough = st.sidebar.selectbox("Borough", boroughs)

if 'Class' in df.columns:
    classes = ['All'] + sorted(df['Class'].dropna().unique().tolist())
    selected_class = st.sidebar.selectbox("Building Class", classes)
else:
    selected_class = 'All'

min_units = st.sidebar.number_input("Minimum Dwelling Units", min_value=0, value=0)

# Apply filters
filtered = df.copy()
if selected_borough != 'All':
    filtered = filtered[filtered['borough'] == selected_borough]
if selected_class != 'All':
    filtered = filtered[filtered['Class'] == selected_class]
if min_units > 0:
    filtered['Units'] = pd.to_numeric(filtered['Units'], errors='coerce').fillna(0)
    filtered = filtered[filtered['Units'] >= min_units]
if search:
    mask = filtered.apply(lambda row: search.lower() in str(row).lower(), axis=1)
    filtered = filtered[mask]

if 'Units' in filtered.columns:
    filtered['Units'] = pd.to_numeric(filtered['Units'], errors='coerce').fillna(0)
    filtered = filtered.sort_values('Units', ascending=False)

# Display metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Permits", len(filtered))
col2.metric("With Phone Numbers", filtered['Phone'].notna().sum())
col3.metric("Total Units", int(filtered['Units'].sum()) if 'Units' in filtered.columns else 0)
col4.metric("Boroughs", filtered['borough'].nunique())

# Monday.com integration
def get_existing_addresses():
    """Fetch all item names (addresses) from Monday.com board"""
    url = "https://api.monday.com/v2"
    headers = {
        "Authorization": MONDAY_API_KEY,
        "Content-Type": "application/json"
    }
    
    query = '''
    query ($board_id: ID!) {
        boards(ids: [$board_id]) {
            items_page(limit: 500) {
                items {
                    name
                }
            }
        }
    }
    '''
    
    variables = {"board_id": MONDAY_BOARD_ID}
    response = requests.post(url, headers=headers, json={"query": query, "variables": variables})
    result = response.json()
    
    try:
        items = result['data']['boards'][0]['items_page']['items']
        return set(item['name'].strip().upper() for item in items)
    except (KeyError, IndexError):
        return set()

def push_to_monday(row):
    url = "https://api.monday.com/v2"
    headers = {
        "Authorization": MONDAY_API_KEY,
        "Content-Type": "application/json"
    }
    
    phone_val = str(row.get('Phone', '') or '').replace('.0', '').replace('nan', '')
    units_val = int(row.get('Units', 0)) if pd.notna(row.get('Units')) else 0
    
    column_values = {
        "text_mm0see9h": str(row.get('borough', '') or ''),
        "text_mm0s36q": str(row.get('Business Name', '') or ''),
        "text_mm0shfbr": str(row.get('First Name', '') or ''),
        "text_mm0s280h": str(row.get('Last Name', '') or ''),
        "phone_mm0s2cbm": {"phone": phone_val, "countryShortName": "US"} if phone_val else {},
        "numeric_mm0s3q1g": units_val,
        "text_mm0sb4dq": str(row.get('Class', '') or ''),
        "long_text_mm0sp894": {"text": str(row.get('Description', '') or '')},
        "color_mm0skpjs": {"label": "Not Called"},
        "text_mm0s2f28": "DOB Permits"
    }
    
    query = '''
    mutation ($board_id: ID!, $item_name: String!, $column_values: JSON!) {
        create_item (board_id: $board_id, item_name: $item_name, column_values: $column_values) {
            id
        }
    }
    '''
    
    variables = {
        "board_id": MONDAY_BOARD_ID,
        "item_name": str(row.get('address', 'No Address')),
        "column_values": json.dumps(column_values)
    }
    
    response = requests.post(url, headers=headers, json={"query": query, "variables": variables})
    return response.json()

# Display data with checkboxes
st.subheader(f"Showing {len(filtered)} permits")

display_cols = ['address', 'borough', 'Business Name', 'First Name', 'Last Name', 
                'Phone', 'Units', 'Class', 'Description']
available_cols = [c for c in display_cols if c in filtered.columns]

filtered_display = filtered.reset_index(drop=True)

# Add Select column for checkboxes
filtered_display.insert(0, 'Select', False)

# Select all / Deselect all
st.markdown("---")
col1, col2, col3 = st.columns([1, 1, 4])
with col1:
    select_all = st.button("Select All")
with col2:
    deselect_all = st.button("Deselect All")

# Initialize session state for selections
if 'selections' not in st.session_state:
    st.session_state.selections = [False] * len(filtered_display)

# Handle select/deselect all
if select_all:
    st.session_state.selections = [True] * len(filtered_display)
if deselect_all:
    st.session_state.selections = [False] * len(filtered_display)

# Make sure selections list matches filtered data length
if len(st.session_state.selections) != len(filtered_display):
    st.session_state.selections = [False] * len(filtered_display)

# Create editable dataframe with selections
filtered_display['Select'] = st.session_state.selections

edited_df = st.data_editor(
    filtered_display[['Select'] + available_cols],
    use_container_width=True,
    height=450,
    hide_index=True,
    column_config={
        "Select": st.column_config.CheckboxColumn("Select", default=False),
        "Phone": st.column_config.TextColumn("Phone"),
        "Units": st.column_config.NumberColumn("Units", format="%d"),
    },
    disabled=available_cols,
    key="data_editor"
)

# Update session state with edited selections
st.session_state.selections = edited_df['Select'].tolist()

# Count selected
selected_count = sum(st.session_state.selections)

# Push to Monday section
st.markdown("---")
col1, col2 = st.columns([3, 1])
with col1:
    st.write(f"**{selected_count} leads selected**")
with col2:
    push_button = st.button("Push Selected to Monday", type="primary", disabled=(selected_count == 0))

if push_button and selected_count > 0:
    # Get existing addresses to check for duplicates
    with st.spinner("Checking for duplicates..."):
        existing_addresses = get_existing_addresses()
    
    progress_bar = st.progress(0)
    success_count = 0
    skipped_count = 0
    
    selected_indices = [i for i, selected in enumerate(st.session_state.selections) if selected]
    
    for idx, i in enumerate(selected_indices):
        row = filtered_display.iloc[i]
        address = str(row.get('address', '')).strip().upper()
        
        # Check for duplicate
        if address in existing_addresses:
            st.warning(f"⏭ Skipped (already exists): {row.get('address', 'Unknown')}")
            skipped_count += 1
        else:
            result = push_to_monday(row)
            
            if 'data' in result and result['data'].get('create_item'):
                success_count += 1
                existing_addresses.add(address)  # Add to set so we don't push twice in same batch
                st.success(f"✓ Pushed: {row.get('address', 'Unknown')}")
            else:
                st.error(f"✗ Failed: {row.get('address', 'Unknown')} - {result}")
        
        progress_bar.progress((idx + 1) / len(selected_indices))
    
    st.info(f"Pushed {success_count} new leads, skipped {skipped_count} duplicates")
    
    # Clear selections after push
    st.session_state.selections = [False] * len(filtered_display)

# Download button
st.download_button(
    label="Download filtered data as CSV",
    data=filtered[available_cols].to_csv(index=False),
    file_name="filtered_permits.csv",
    mime="text/csv"
)