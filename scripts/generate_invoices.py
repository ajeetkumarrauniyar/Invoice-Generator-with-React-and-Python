import sys
import json
import pandas as pd
import random
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import traceback

# def generate_indian_business_name():
#     """Generate a realistic Indian business name."""
#     business_types = [
#         "TRADERS", "ENTERPRISES", "INDUSTRIES", "AGRO", "TRADING CO", 
#         "& SONS", "& COMPANY", "CORPORATION", "BUSINESS", "VENTURES"
#     ]
     
#     common_prefixes = [
#         "SHRI", "SRI", "JAI", "OM", "NEW", "ROYAL", "NATIONAL", "INDIAN",
#         "GOLDEN", "SUPREME"
#     ] 
    
#     indian_surnames = [
#         "KUMAR", "SINGH", "SHARMA", "VERMA", "GUPTA", "PATEL", "REDDY",
#         "SHAH", "MEHTA", "JAIN", "AGARWAL", "SINHA", "RAO", "MISHRA"
#     ]

#     name_type = random.randint(1, 3)
    
#     if name_type == 1:
#         # Format: PREFIX SURNAME BUSINESS_TYPE
#         return f"{random.choice(common_prefixes)} {random.choice(indian_surnames )} {random.choice(business_types)}"
#     elif name_type == 2:
#         # Format: SURNAME BUSINESS_TYPE
#         return f"{random.choice(indian_surnames)} {random.choice(business_types)}"
#     else:
#         # Format: PREFIX BUSINESS_TYPE
#         return f"{random.choice( common_prefixes)} {random.choice(business_types)}"

def generate_bihar_farmer_name():
    """Generate a realistic Bihar farmer name."""
    first_names = [
        'Harinder', 'Vinod', 'Ajay', 'Lalan', 'Madan', 'Manish', 'Ramesh', 
        'Suresh', 'Dinesh', 'Rajesh', 'Sanjay', 'Naveen', 'Ashok', 'Vijay', 
        'Ravi', 'Mukesh', 'Amit', 'Rahul', 'Santosh', 'Naresh'
    ]
    
    last_names = [
        'Sahu', 'Tiwari', 'Prasad', 'Jaiswal', 'Kumar', 'Singh', 'Yadav', 
        'Mishra', 'Pandey', 'Verma', 'Gupta', 'Maurya', 'Patel', 'Dubey'
    ]
    
    return f"{random.choice(first_names)} {random.choice(last_names)}"

# def generate_indian_business_names(count=10):
#     """Generate multiple Indian business names."""
#     return [generate_indian_business_name() for _ in range(count)]

def generate_bihar_farmer_names(count=10):
    """Generate multiple Bihar farmer names."""
    return [generate_bihar_farmer_name() for _ in range(count)]

def generate_party_dataset(total_amount, party_limit):
    """Generate a dictionary of parties with balanced distribution of the total amount."""
    try:
        if total_amount <= 0 or party_limit <= 0:
            raise ValueError("Total amount and party limit must be positive")
            
        if party_limit > total_amount:
            raise ValueError("Party limit cannot be greater than total amount")
            
        num_parties = int((total_amount + party_limit - 1) // party_limit)# Round up division
        
        # Generate party names with realistic Indian business names
        used_names = set()
        party_data = {}

        for i in range(num_parties):
            # Generate unique business name
            while True:
                party_name = generate_bihar_farmer_name()
                if party_name not in used_names:
                    used_names.add(party_name)
                    break
            
            
            # For the last party, adjust the balance to match total_amount exactly
            if i == num_parties - 1:
                remaining = total_amount - (party_limit * (num_parties - 1))
                party_data[party_name] = float(remaining)
            else:
                party_data[party_name] = float(party_limit)
                
        return party_data
    except Exception as e:
        raise Exception(f"Error generating party dataset: {str(e)}")

def format_rate(value):
    """Format rate to always show two decimal places."""
    return f"{float(value):.2f}"

def normalize_party_name(name):
    """Normalize the UNR- prefix in party names with robust handling of variations and ensure name is uppercase."""
    try:
        name = str(name).strip()
        standard_prefix = "UNR-"
        
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
                
            self.min_invoice = Decimal("20000") # Minimum invoice value
            self.max_invoice = Decimal("48000") # Maximum invoice value
            self.global_invoice_counter = int(start_invoice_number)
            self.last_invoice_date = self.start_date
            
             # Initialize date ranges with weighted distribution
            self.available_dates = []
            current_date = self.start_date
            while current_date <= self.end_date:
                # Higher weights for mid-month dates, lower for month start/end
                day_of_month = current_date.day
                if 5 <= day_of_month <= 25:
                    weight = random.randint(2, 5)  # More invoices in mid-month
                else:
                    weight = random.randint(1, 3)  # Fewer invoices at month edges
                    
                self.available_dates.extend([current_date] * weight)
                current_date += timedelta(days=1)
            
             # Sort dates to maintain chronological order
            self.available_dates.sort()
            
        except ValueError as e:
            raise ValueError(f"Invalid input parameters: {str(e)}")
        except Exception as e:
            raise Exception(f"Error initializing InvoiceGenerator: {str(e)}")

    def get_next_date(self):
        """Get the next available date, ensuring chronological order."""
        if not self.available_dates:
            return self.last_invoice_date
        
        # Find all dates that are after the last invoice date
        valid_dates = [d for d in self.available_dates if d >= self.last_invoice_date]
        
        if not valid_dates:
            return self.last_invoice_date
            
        # Pick the earliest available date from valid dates
        next_date = valid_dates[0]
        self.available_dates.remove(next_date)
        self.last_invoice_date = next_date
        
        return next_date

    def generate_invoice(self, remaining_balance):
        try:
            if remaining_balance < self.min_invoice:
                return None

            next_date = self.get_next_date()

            # First generate a random rate
            rate = Decimal(
                str(random.uniform(float(self.min_rate), float(self.max_rate)))
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # Calculate min and max possible quantities based on invoice constraints
            min_quantity = (self.min_invoice / rate).quantize(Decimal("1."), rounding=ROUND_HALF_UP)
            max_quantity = (min(self.max_invoice, remaining_balance) / rate).quantize(
                Decimal("1."), rounding=ROUND_HALF_UP
            )

            if min_quantity > max_quantity:
                # Adjust rate if quantity constraints cannot be met
                rate = Decimal(
                    str(random.uniform(float(self.min_rate), float(self.max_rate)))
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                min_quantity = (self.min_invoice / rate).quantize(Decimal("1."), rounding=ROUND_HALF_UP)
                max_quantity = (min(self.max_invoice, remaining_balance) / rate).quantize(
                    Decimal("1."), rounding=ROUND_HALF_UP
                )

            # Generate random quantity
            quantity = Decimal(
                str(random.uniform(float(min_quantity), float(max_quantity)))
            ).quantize(Decimal("1."), rounding=ROUND_HALF_UP)

            # Calculate invoice value and round to nearest hundred
            invoice_value = (rate * quantity).quantize(
                Decimal("100."), rounding=ROUND_HALF_UP
            )

            # Validate invoice value constraints
            if invoice_value < self.min_invoice or invoice_value > self.max_invoice:
                # Adjust quantity to meet invoice value constraints
                quantity = (self.min_invoice / rate).quantize(Decimal("1."), rounding=ROUND_HALF_UP)
                invoice_value = (rate * quantity).quantize(
                    Decimal("100."), rounding=ROUND_HALF_UP
                )

            # Generate margin and sale rate
            margin_percentage = Decimal(
                str(random.uniform(float(self.min_margin), float(self.max_margin)))
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            
            sale_rate = (rate * (1 + margin_percentage / 100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            # Generate invoice number
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
                        "Pur. Rate (Rs./kg)": format_rate(invoice["rate"]),
                        "Invoice Value (Rs.)": float(invoice["invoice_value"]),
                        "Sale Rate (Rs./kg)": format_rate(invoice["sale_rate"]),
                        "Margin (%)": format_rate(invoice["margin_percentage"]),
                        "Balance Remaining (Rs.)": float(invoice["remaining_balance"]),
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
        # Check if we're using the party data file or generating new data
        if len(sys.argv) == 12 and sys.argv[4] == "--generate":
            # Auto-generate mode
            start_date = sys.argv[1]
            end_date = sys.argv[2]
            start_invoice_number = sys.argv[3]
            total_amount = float(sys.argv[5])
            party_limit = float(sys.argv[6])
            product_name = sys.argv[7]
            min_rate = float(sys.argv[8])
            max_rate = float(sys.argv[9])
            min_margin = float(sys.argv[10])
            max_margin = float(sys.argv[11])
            
            # Generate party data
            party_data = generate_party_dataset(total_amount, party_limit)

        elif len(sys.argv) == 10:
            # Manual party data file mode
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
        else:
            raise ValueError("Invalid number of arguments. Use either:\n" +
                           "1. Auto-generate mode: 11 arguments (with --generate)\n" +
                           "2. Manual file mode: 9 arguments (with party data file)")

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