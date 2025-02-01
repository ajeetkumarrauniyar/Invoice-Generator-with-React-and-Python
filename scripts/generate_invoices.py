import sys
import json
import pandas as pd
import random
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import traceback

def format_rate(value):
    """Format rate to always show two decimal places."""
    return f"{float(value):.2f}"

def normalize_party_name(name):
    """Normalize the UNR- prefix in party names with robust handling of variations and ensure name is uppercase."""
    try:
        name = str(name).strip()
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
        
        # Convert the name part to uppercase and add the standardized prefix
        return standard_prefix + name.upper()
    except Exception as e:
        print(f"Error normalizing party name '{name}': {str(e)}", file=sys.stderr)
        return name

class InvoiceGenerator:
    def __init__(self, start_date, end_date, start_invoice_number, min_rate, max_rate, min_margin, max_margin):
        try:
            self.start_date = datetime.strptime(start_date, '%Y-%m-%d')
            self.end_date = datetime.strptime(end_date, '%Y-%m-%d')
            
            if self.start_date > self.end_date:
                raise ValueError("Start date must be before end date")
                
            self.min_rate = Decimal(str(min_rate))
            self.max_rate = Decimal(str(max_rate))
            
            if self.min_rate > self.max_rate:
                raise ValueError("Minimum rate must be less than maximum rate")
                
            self.min_margin = Decimal(str(min_margin))
            self.max_margin = Decimal(str(max_margin))
            
            if self.min_margin > self.max_margin:
                raise ValueError("Minimum margin must be less than maximum margin")
                
            self.min_invoice = Decimal("20000")
            self.max_invoice = Decimal("48000")
            self.global_invoice_counter = int(start_invoice_number)
            self.last_invoice_date = self.start_date
        except ValueError as e:
            raise ValueError(f"Invalid input parameters: {str(e)}")
        except Exception as e:
            raise Exception(f"Error initializing InvoiceGenerator: {str(e)}")

    def generate_invoice(self, remaining_balance):
        try:
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
        except Exception as e:
            print(f"Error generating invoice: {str(e)}", file=sys.stderr)
            return None

def generate_all_invoices(party_data, start_date, end_date, start_invoice_number, product_name, min_rate, max_rate, min_margin, max_margin):
    try:
        generator = InvoiceGenerator(start_date, end_date, start_invoice_number, min_rate, max_rate, min_margin, max_margin)
        all_results = []

        active_parties = []
        for party_name, balance in party_data.items():
            try:
                remaining = Decimal(str(balance))
                if remaining >= generator.min_invoice:
                    normalized_name = normalize_party_name(party_name)
                    active_parties.append({"name": normalized_name, "remaining": remaining})
            except Exception as e:
                print(f"Error processing party {party_name}: {str(e)}", file=sys.stderr)
                continue

        if not active_parties:
            raise ValueError("No valid parties with sufficient balance found")

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

        if not all_results:
            raise ValueError("No invoices could be generated with the given parameters")

        return pd.DataFrame(all_results)
    except Exception as e:
        print(f"Error in generate_all_invoices: {str(e)}\n{traceback.format_exc()}", file=sys.stderr)
        raise

def main():
    try:
        if len(sys.argv) != 10:
            raise ValueError(f"Incorrect number of arguments. Expected 10, got {len(sys.argv)}")

        start_date = sys.argv[1]
        end_date = sys.argv[2]
        start_invoice_number = sys.argv[3]
        party_data_file = sys.argv[4]
        product_name = sys.argv[5]
        min_rate = float(sys.argv[6])
        max_rate = float(sys.argv[7])
        min_margin = float(sys.argv[8])
        max_margin = float(sys.argv[9])

        # Read party data from CSV
        party_data = {}
        try:
            with open(party_data_file, 'r') as f:
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
        except Exception as e:
            raise Exception(f"Error reading party data file: {str(e)}")

        if not party_data:
            raise ValueError("No valid party data found in the input file")

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
        print(f"Error: {str(e)}\n{traceback.format_exc()}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main() 