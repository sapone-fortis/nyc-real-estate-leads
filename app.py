import streamlit as st
import pandas as pd

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

# Search box
search = st.sidebar.text_input("Search (name, address, etc.)")

# Borough filter
boroughs = ['All'] + sorted(df['borough'].dropna().unique().tolist())
selected_borough = st.sidebar.selectbox("Borough", boroughs)

# Building class filter
if 'Class' in df.columns:
    classes = ['All'] + sorted(df['Class'].dropna().unique().tolist())
    selected_class = st.sidebar.selectbox("Building Class", classes)
else:
    selected_class = 'All'

# Min units filter
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

# Sort by units descending
if 'Units' in filtered.columns:
    filtered['Units'] = pd.to_numeric(filtered['Units'], errors='coerce').fillna(0)
    filtered = filtered.sort_values('Units', ascending=False)

# Display metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Permits", len(filtered))
col2.metric("With Phone Numbers", filtered['Phone'].notna().sum())
col3.metric("Total Units", int(filtered['Units'].sum()) if 'Units' in filtered.columns else 0)
col4.metric("Boroughs", filtered['borough'].nunique())

# Display data
st.subheader(f"Showing {len(filtered)} permits")

# Select columns to display
display_cols = ['address', 'borough', 'Business Name', 'First Name', 'Last Name', 
                'Phone', 'Units', 'Class', 'Description']
available_cols = [c for c in display_cols if c in filtered.columns]

# Make phone numbers clickable
def make_clickable_phone(phone):
    if pd.notna(phone) and str(phone) != 'None':
        phone_str = str(phone).replace('.0', '')
        return f'<a href="tel:{phone_str}">{phone_str}</a>'
    return ''

filtered_display = filtered[available_cols].copy()
filtered_display['Phone'] = filtered_display['Phone'].apply(make_clickable_phone)

st.markdown(filtered_display.to_html(escape=False, index=False), unsafe_allow_html=True)

# Download button
st.download_button(
    label="Download filtered data as CSV",
    data=filtered[available_cols].to_csv(index=False),
    file_name="filtered_permits.csv",
    mime="text/csv"
)