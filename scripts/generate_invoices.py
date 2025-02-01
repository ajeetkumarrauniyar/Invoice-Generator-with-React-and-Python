import sys
import json
import pandas as pd
import random
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

def format_rate(value):
    """Format rate to always show two decimal places."""
    return f"{float(value):.2f}"

def normalize_party_name(name):
    """Normalize the UNR- prefix in party names with robust handling of variations."""
    name = name.strip()
    standard_prefix = "UNR- "
    
    # List of possible prefix variations (case-insensitive)
    prefix_variations = [
        "UNR-", "UNR - ", "UNR ", "UNREGISTERED-", "UNREGISTERED - ",
        "UNREGISTERED", "UNR_", "UNR_ ", "UNR.", "UNR. ", "U.N.R-",
        "U.N.R", "U.N.R ", "U N R-", "U N R", "U N R "
    ]
    
    # Convert to uppercase for comparison
    name_upper = name.upper()
    
    # Remove any existing variations of the prefix
    for prefix in prefix_variations:
        if name_upper.startswith(prefix):
            # Get the name part after the prefix
            name = name[len(prefix):].strip()
            break
    
    # Add the standardized prefix
    return standard_prefix + name

class InvoiceGenerator:
    def __init__(self, start_date, end_date, start_invoice_number, min_rate, max_rate, min_margin, max_margin):
        self.start_date = datetime.strptime(start_date, '%Y-%m-%d')
        self.end_date = datetime.strptime(end_date, '%Y-%m-%d')
        self.min_rate = Decimal(str(min_rate))
        self.max_rate = Decimal(str(max_rate))
        self.min_margin = Decimal(str(min_margin))
        self.max_margin = Decimal(str(max_margin))
        self.min_invoice = Decimal("20000")
        self.max_invoice = Decimal("48000")
        self.global_invoice_counter = int(start_invoice_number)
        self.last_invoice_date = self.start_date

    def generate_invoice(self, remaining_balance):
        if remaining_balance < self.min_invoice:
            return None

        days_increment = random.randint(1, 10)
        next_date = min(
            self.last_invoice_date + timedelta(days=days_increment), self.end_date
        )
        self.last_invoice_date = next_date

        max_possible = min(self.max_invoice, remaining_balance)
        min_possible = max(self.min_invoice, Decimal("1"))

        invoice_value = Decimal(
            str(random.uniform(float(min_possible), float(max_possible)))
        ).quantize(Decimal("1."), rounding=ROUND_HALF_UP)

        rate = Decimal(
            str(random.uniform(float(self.min_rate), float(self.max_rate)))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        quantity = (invoice_value / rate).quantize(
            Decimal("1."), rounding=ROUND_HALF_UP
        )
        
        margin_percentage = Decimal(
            str(random.uniform(float(self.min_margin), float(self.max_margin)))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        sale_rate = (rate * (1 + margin_percentage / 100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        invoice_month = next_date.strftime("%b").upper()
        invoice_no = f"{invoice_month}-{self.global_invoice_counter:03d}"
        self.global_invoice_counter += 1

        return {
            "invoice_no": invoice_no,
            "quantity": quantity,
            "rate": rate,
            "sale_rate": sale_rate,
            "margin_percentage": margin_percentage,
            "invoice_value": invoice_value,
            "date": next_date,
            "remaining_balance": remaining_balance - invoice_value,
        }

def generate_all_invoices(party_data, start_date, end_date, start_invoice_number, product_name, min_rate, max_rate, min_margin, max_margin):
    generator = InvoiceGenerator(start_date, end_date, start_invoice_number, min_rate, max_rate, min_margin, max_margin)
    all_results = []

    active_parties = []
    for party_name, balance in party_data.items():
        remaining = Decimal(str(balance))
        if remaining >= generator.min_invoice:
            # Normalize party name here
            normalized_name = normalize_party_name(party_name)
            active_parties.append({"name": normalized_name, "remaining": remaining})

    while active_parties:
        idx = random.randint(0, len(active_parties) - 1)
        current_party = active_parties.pop(idx)

        invoice = generator.generate_invoice(current_party["remaining"])

        if invoice is not None:
            all_results.append(
                {
                    "Invoice Date": invoice["date"].strftime("%d-%m-%Y"),
                    "Invoice No": invoice["invoice_no"],
                    "Party Name": current_party["name"],
                    "Product": product_name,
                    "Quantity (kg)": int(invoice["quantity"]),
                    "Pur. Rate (₹/kg)": format_rate(invoice["rate"]),
                    "Invoice Value (₹)": float(invoice["invoice_value"]),
                    "Sale Rate (₹/kg)": format_rate(invoice["sale_rate"]),
                    "Margin (%)": format_rate(invoice["margin_percentage"]),
                    "Balance Remaining (₹)": float(invoice["remaining_balance"]),
                }
            )

            current_party["remaining"] = invoice["remaining_balance"]

            if current_party["remaining"] >= generator.min_invoice:
                active_parties.append(current_party)

    return pd.DataFrame(all_results)

def main():
    if len(sys.argv) != 10:
        print(f"Error: Incorrect number of arguments. Expected 10, got {len(sys.argv)}", file=sys.stderr)
        sys.exit(1)

    start_date = sys.argv[1]
    end_date = sys.argv[2]
    start_invoice_number = sys.argv[3]
    party_data_file = sys.argv[4]
    product_name = sys.argv[5]
    min_rate = float(sys.argv[6])
    max_rate = float(sys.argv[7])
    min_margin = float(sys.argv[8])
    max_margin = float(sys.argv[9])

    try:
        # Read party data from CSV
        with open(party_data_file, 'r') as f:
            party_data = {}
            for line_number, line in enumerate(f, 1):
                try:
                    if ',' in line:
                        name, balance = line.strip().split(',')
                        name = name.strip()
                        balance = float(balance.strip())
                        if balance <= 0:
                            print(f"Warning: Skipping line {line_number}, balance must be positive: {line.strip()}", file=sys.stderr)
                            continue
                        party_data[name] = balance
                except ValueError as e:
                    print(f"Warning: Skipping invalid line {line_number}: {line.strip()}", file=sys.stderr)
                    continue

        if not party_data:
            print("Error: No valid party data found in the input file", file=sys.stderr)
            sys.exit(1)

        # Generate invoices
        df = generate_all_invoices(
            party_data,
            start_date,
            end_date,
            start_invoice_number,
            product_name,
            min_rate,
            max_rate,
            min_margin,
            max_margin
        )

        # Sort by invoice number
        df["Month"] = df["Invoice No"].str[:3]
        df["Invoice Number"] = df["Invoice No"].str[4:].astype(int)

        month_order = {
            "APR": 1, "MAY": 2, "JUN": 3, "JUL": 4, "AUG": 5, "SEP": 6,
            "OCT": 7, "NOV": 8, "DEC": 9, "JAN": 10, "FEB": 11, "MAR": 12
        }
        df["Month Order"] = df["Month"].map(month_order)
        df = df.sort_values(by=["Month Order", "Invoice Number"]).drop(
            columns=["Month", "Month Order", "Invoice Number"]
        )

        # Output as CSV to stdout
        df.to_csv(sys.stdout, index=False)

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main() 