"""
Capital Partner Matcher
=======================
Matches deals to capital partners based on lending criteria stored in Monday.com.

Usage:
    python capital_matcher.py --deal "41-08 Crescent"
    python capital_matcher.py --deal-size 100000000 --property-type Multifamily --location NYC --loan-type Construction --ltc 75
"""

import os
import json
import requests
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import List, Optional

load_dotenv()

MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
MONDAY_API_URL = "https://api.monday.com/v2"

# Board IDs - UPDATE THESE WITH YOUR ACTUAL BOARD IDs
ACCOUNTS_BOARD_ID = os.getenv("MONDAY_ACCOUNTS_BOARD_ID", "")
DEALS_BOARD_ID = os.getenv("MONDAY_DEALS_BOARD_ID", "18391321597")  # From your screenshot
DEAL_PARTNERS_BOARD_ID = os.getenv("MONDAY_DEAL_PARTNERS_BOARD_ID", "")


@dataclass
class Deal:
    """Represents a deal's key parameters for matching."""
    name: str
    deal_size: float
    property_type: str
    location: str
    loan_type: str
    target_ltc: float
    target_ltv: Optional[float] = None


@dataclass
class CapitalPartner:
    """Represents a capital partner's lending program."""
    name: str
    item_id: str
    min_deal_size: float
    max_deal_size: float
    loan_types: List[str]
    property_types: List[str]
    geographies: List[str]
    max_ltc: float
    max_ltv: float
    typical_spread: str
    leverage_point: str
    pricing_tier: str
    recourse: str
    program_notes: str
    primary_contact: str


def monday_query(query: str, variables: dict = None):
    """Execute a Monday.com GraphQL query."""
    headers = {
        "Authorization": MONDAY_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    
    response = requests.post(MONDAY_API_URL, headers=headers, json=payload)
    return response.json()


def get_accounts_board_id():
    """Find the Accounts board ID."""
    query = """
    query {
        boards(limit: 50) {
            id
            name
        }
    }
    """
    result = monday_query(query)
    boards = result.get("data", {}).get("boards", [])
    
    for board in boards:
        if "account" in board["name"].lower():
            return board["id"]
    
    return None


def get_capital_partners():
    """Fetch all lender/LP accounts from Monday.com with their lending programs."""
    
    board_id = ACCOUNTS_BOARD_ID or get_accounts_board_id()
    
    if not board_id:
        print("❌ Could not find Accounts board. Please set MONDAY_ACCOUNTS_BOARD_ID in .env")
        return []
    
    query = """
    query ($boardId: ID!) {
        boards(ids: [$boardId]) {
            items_page(limit: 200) {
                items {
                    id
                    name
                    column_values {
                        id
                        text
                        value
                    }
                }
            }
        }
    }
    """
    
    result = monday_query(query, {"boardId": board_id})
    
    if "errors" in result:
        print(f"❌ Error fetching accounts: {result['errors']}")
        return []
    
    items = result.get("data", {}).get("boards", [{}])[0].get("items_page", {}).get("items", [])
    
    partners = []
    for item in items:
        # Parse column values into a dict
        cols = {}
        for col in item.get("column_values", []):
            cols[col["id"]] = col["text"] or ""
        
        # Check if this is a lender/LP (has lending program data)
        account_type = cols.get("type", "") or cols.get("dropdown", "")
        if "lender" not in account_type.lower() and "lp" not in account_type.lower() and "investor" not in account_type.lower():
            # Also check if they have max_ltc filled in (indicates lending program)
            if not cols.get("max_ltc") and not cols.get("numbers", ""):
                continue
        
        # Parse multi-select fields
        def parse_multi(val):
            if not val:
                return []
            # Monday returns multi-select as comma-separated or JSON
            try:
                parsed = json.loads(val) if val.startswith("[") else val.split(", ")
                return [str(x).strip() for x in parsed if x]
            except:
                return [x.strip() for x in val.split(",") if x.strip()]
        
        partner = CapitalPartner(
            name=item["name"],
            item_id=item["id"],
            min_deal_size=float(cols.get("min_deal_size", "0").replace(",", "").replace("$", "") or 0),
            max_deal_size=float(cols.get("max_deal_size", "0").replace(",", "").replace("$", "") or 999999999),
            loan_types=parse_multi(cols.get("loan_types", "")),
            property_types=parse_multi(cols.get("property_types", "")),
            geographies=parse_multi(cols.get("geographies", "")),
            max_ltc=float(cols.get("max_ltc", "0").replace("%", "") or 0),
            max_ltv=float(cols.get("max_ltv", "0").replace("%", "") or 0),
            typical_spread=cols.get("typical_spread", ""),
            leverage_point=cols.get("leverage_point", ""),
            pricing_tier=cols.get("pricing_tier", ""),
            recourse=cols.get("recourse", ""),
            program_notes=cols.get("program_notes", ""),
            primary_contact=cols.get("primary_contact", "")
        )
        partners.append(partner)
    
    return partners


def match_partner(deal: Deal, partner: CapitalPartner) -> dict:
    """
    Score how well a partner matches a deal.
    Returns dict with score (0-100), match level, and reasons.
    """
    score = 0
    reasons = []
    blockers = []
    
    # Deal size check (blocker if outside range)
    if partner.min_deal_size > 0 and deal.deal_size < partner.min_deal_size:
        blockers.append(f"Deal ${deal.deal_size/1e6:.0f}M below min ${partner.min_deal_size/1e6:.0f}M")
    elif partner.max_deal_size > 0 and deal.deal_size > partner.max_deal_size:
        blockers.append(f"Deal ${deal.deal_size/1e6:.0f}M above max ${partner.max_deal_size/1e6:.0f}M")
    else:
        score += 20
        reasons.append(f"Deal size ${deal.deal_size/1e6:.0f}M in range")
    
    # Loan type check
    if partner.loan_types:
        if any(deal.loan_type.lower() in lt.lower() for lt in partner.loan_types):
            score += 25
            reasons.append(f"Does {deal.loan_type}")
        else:
            blockers.append(f"Doesn't do {deal.loan_type} (does: {', '.join(partner.loan_types)})")
    
    # Property type check
    if partner.property_types:
        if any(deal.property_type.lower() in pt.lower() for pt in partner.property_types):
            score += 20
            reasons.append(f"Does {deal.property_type}")
        else:
            blockers.append(f"Doesn't do {deal.property_type}")
    
    # Geography check
    if partner.geographies:
        location_lower = deal.location.lower()
        geo_match = any(
            geo.lower() in location_lower or 
            location_lower in geo.lower() or
            (geo.lower() == "national")
            for geo in partner.geographies
        )
        if geo_match:
            score += 15
            reasons.append(f"Covers {deal.location}")
        else:
            blockers.append(f"Doesn't cover {deal.location} (does: {', '.join(partner.geographies)})")
    
    # LTC check
    if partner.max_ltc > 0:
        if deal.target_ltc <= partner.max_ltc:
            score += 20
            reasons.append(f"Can do {deal.target_ltc}% LTC (max {partner.max_ltc}%)")
        else:
            blockers.append(f"Target {deal.target_ltc}% LTC exceeds max {partner.max_ltc}%")
    
    # Determine match level
    if blockers:
        match_level = "NO MATCH"
        score = 0
    elif score >= 80:
        match_level = "HIGH MATCH"
    elif score >= 50:
        match_level = "PARTIAL MATCH"
    else:
        match_level = "LOW MATCH"
    
    return {
        "partner": partner.name,
        "score": score,
        "match_level": match_level,
        "reasons": reasons,
        "blockers": blockers,
        "pricing": partner.typical_spread,
        "leverage_point": partner.leverage_point,
        "pricing_tier": partner.pricing_tier,
        "contact": partner.primary_contact,
        "notes": partner.program_notes
    }


def find_matches(deal: Deal, partners: List[CapitalPartner]) -> List[dict]:
    """Find and rank all matching partners for a deal."""
    matches = []
    
    for partner in partners:
        result = match_partner(deal, partner)
        matches.append(result)
    
    # Sort by score descending
    matches.sort(key=lambda x: x["score"], reverse=True)
    
    return matches


def print_matches(deal: Deal, matches: List[dict]):
    """Pretty print the matching results."""
    print("\n" + "=" * 70)
    print(f"CAPITAL PARTNER MATCHES: {deal.name}")
    print("=" * 70)
    print(f"Deal Size: ${deal.deal_size/1e6:.0f}M | {deal.property_type} | {deal.location}")
    print(f"Loan Type: {deal.loan_type} | Target LTC: {deal.target_ltc}%")
    print("=" * 70)
    
    # Group by match level
    high = [m for m in matches if m["match_level"] == "HIGH MATCH"]
    partial = [m for m in matches if m["match_level"] == "PARTIAL MATCH"]
    no_match = [m for m in matches if m["match_level"] == "NO MATCH"]
    
    if high:
        print("\n✅ HIGH MATCH:")
        for m in high:
            print(f"\n   {m['partner']} (Score: {m['score']})")
            print(f"      Pricing: {m['pricing']} | {m['pricing_tier']}")
            for r in m["reasons"]:
                print(f"      + {r}")
            if m["notes"]:
                print(f"      📝 {m['notes'][:80]}...")
    
    if partial:
        print("\n🟡 PARTIAL MATCH:")
        for m in partial:
            print(f"\n   {m['partner']} (Score: {m['score']})")
            print(f"      Pricing: {m['pricing']} | {m['pricing_tier']}")
            for r in m["reasons"]:
                print(f"      + {r}")
            for b in m["blockers"]:
                print(f"      - {b}")
    
    if no_match:
        print("\n❌ NO MATCH:")
        for m in no_match:
            print(f"   {m['partner']}: {', '.join(m['blockers'][:2])}")
    
    print("\n" + "=" * 70)


def create_deal_partner_entries(deal_name: str, matches: List[dict], top_n: int = 5):
    """Create Deal Partner entries in Monday.com for top matches."""
    
    if not DEAL_PARTNERS_BOARD_ID:
        print("❌ MONDAY_DEAL_PARTNERS_BOARD_ID not set in .env")
        return
    
    # Get top matches that aren't blockers
    top_matches = [m for m in matches if m["match_level"] != "NO MATCH"][:top_n]
    
    if not top_matches:
        print("No matches to create entries for.")
        return
    
    print(f"\nCreating {len(top_matches)} Deal Partner entries...")
    
    # For now, just print what would be created
    # Full implementation would use Monday API to create items in the Deal Partners board
    for m in top_matches:
        print(f"   Would create: {m['partner']} for {deal_name}")
        print(f"      Status: Not Started")
        print(f"      Match Score: {m['score']}")


# ============ DEMO MODE (no Monday.com connection) ============

def demo_partners() -> List[CapitalPartner]:
    """Return demo capital partners for testing without Monday.com."""
    return [
        CapitalPartner(
            name="Oaknorth",
            item_id="demo1",
            min_deal_size=20_000_000,
            max_deal_size=150_000_000,
            loan_types=["Construction", "Bridge"],
            property_types=["Multifamily", "Mixed-Use", "Office"],
            geographies=["NYC", "Tri-State", "National"],
            max_ltc=80,
            max_ltv=65,
            typical_spread="S+450-550",
            leverage_point="High (75%+)",
            pricing_tier="Premium",
            recourse="Non-Recourse",
            program_notes="Will go high leverage but prices wide. Good for deals needing max proceeds. Fast execution.",
            primary_contact="Max Saidman"
        ),
        CapitalPartner(
            name="Mesa West",
            item_id="demo2",
            min_deal_size=50_000_000,
            max_deal_size=300_000_000,
            loan_types=["Construction", "Bridge"],
            property_types=["Multifamily", "Office", "Industrial"],
            geographies=["National"],
            max_ltc=70,
            max_ltv=60,
            typical_spread="S+350-425",
            leverage_point="Mid (60-75%)",
            pricing_tier="Market",
            recourse="Non-Recourse",
            program_notes="Balance sheet lender. Competitive pricing. Conservative on basis.",
            primary_contact=""
        ),
        CapitalPartner(
            name="Bawag",
            item_id="demo3",
            min_deal_size=30_000_000,
            max_deal_size=200_000_000,
            loan_types=["Construction"],
            property_types=["Multifamily", "Mixed-Use"],
            geographies=["NYC", "Tri-State"],
            max_ltc=65,
            max_ltv=55,
            typical_spread="S+275-350",
            leverage_point="Low (≤60%)",
            pricing_tier="Aggressive",
            recourse="Non-Recourse",
            program_notes="European bank. Very aggressive pricing but lower leverage. Best for well-capitalized sponsors.",
            primary_contact="Eric Koefoed"
        ),
        CapitalPartner(
            name="Torchlight",
            item_id="demo4",
            min_deal_size=25_000_000,
            max_deal_size=150_000_000,
            loan_types=["Mezz", "Pref Equity"],
            property_types=["Multifamily", "Office", "Mixed-Use"],
            geographies=["National"],
            max_ltc=85,
            max_ltv=75,
            typical_spread="12-15%",
            leverage_point="High (75%+)",
            pricing_tier="Market",
            recourse="Non-Recourse",
            program_notes="Mezz/pref equity provider. Good for gap capital. Quick decisions.",
            primary_contact="Sydney Mas"
        ),
        CapitalPartner(
            name="MF1",
            item_id="demo5",
            min_deal_size=30_000_000,
            max_deal_size=100_000_000,
            loan_types=["Bridge"],
            property_types=["Multifamily"],
            geographies=["National"],
            max_ltc=75,
            max_ltv=70,
            typical_spread="S+375-450",
            leverage_point="Mid (60-75%)",
            pricing_tier="Market",
            recourse="Non-Recourse",
            program_notes="Multifamily specialist. Bridge only, no construction.",
            primary_contact="Sean Curtin"
        ),
        CapitalPartner(
            name="HPS",
            item_id="demo6",
            min_deal_size=50_000_000,
            max_deal_size=500_000_000,
            loan_types=["Construction", "Mezz"],
            property_types=["Multifamily", "Office", "Mixed-Use", "Industrial"],
            geographies=["National"],
            max_ltc=75,
            max_ltv=65,
            typical_spread="S+400-500",
            leverage_point="Mid (60-75%)",
            pricing_tier="Premium",
            recourse="Non-Recourse",
            program_notes="Large credit fund. Can do whole loan or mezz. Premium pricing but reliable execution.",
            primary_contact=""
        ),
    ]


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Match deals to capital partners")
    parser.add_argument("--deal", type=str, help="Deal name to match")
    parser.add_argument("--deal-size", type=float, help="Deal size in dollars")
    parser.add_argument("--property-type", type=str, default="Multifamily")
    parser.add_argument("--location", type=str, default="NYC")
    parser.add_argument("--loan-type", type=str, default="Construction")
    parser.add_argument("--ltc", type=float, default=75, help="Target LTC %")
    parser.add_argument("--demo", action="store_true", help="Use demo data instead of Monday.com")
    parser.add_argument("--create-entries", action="store_true", help="Create Deal Partner entries")
    
    args = parser.parse_args()
    
    # Build deal object
    deal = Deal(
        name=args.deal or "Test Deal",
        deal_size=args.deal_size or 100_000_000,
        property_type=args.property_type,
        location=args.location,
        loan_type=args.loan_type,
        target_ltc=args.ltc
    )
    
    # Get partners
    if args.demo:
        print("🔶 Running in DEMO mode with sample data")
        partners = demo_partners()
    else:
        print("📡 Fetching capital partners from Monday.com...")
        partners = get_capital_partners()
        
        if not partners:
            print("⚠️  No capital partners found in Monday.com. Running demo mode instead.")
            partners = demo_partners()
    
    print(f"Found {len(partners)} capital partners")
    
    # Find matches
    matches = find_matches(deal, partners)
    
    # Print results
    print_matches(deal, matches)
    
    # Optionally create Deal Partner entries
    if args.create_entries:
        create_deal_partner_entries(deal.name, matches)
    
    return matches


if __name__ == "__main__":
    main()
