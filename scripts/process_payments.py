import sys
import pandas as pd
from datetime import datetime, timedelta
from io import StringIO

def generate_payment_schedule(csv_data):
    # Read the CSV data
    df = pd.read_csv(StringIO(csv_data))
    
    # Clean the DataFrame
    # Remove summary rows (rows with numbers in Date column)
    df = df[df['Date'].str.contains('-', na=False)]
    
    # Convert date string to datetime object for sorting
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%m-%Y')
    
    # Initialize payment records list
    payment_records = []
    
    # Group by Party Name
    party_groups = df.groupby('Party Name')
    
    # Process each party's invoices
    for party_name, party_invoices in party_groups:
        # Sort invoices by date
        party_invoices = party_invoices.sort_values('Date')
        
        # Keep track of daily payments for each date
        daily_payments = {}
        
        # Process each invoice
        for _, invoice in party_invoices.iterrows():
            invoice_date = invoice['Date']
            invoice_number = invoice['Bill']
            invoice_amount = float(invoice['Amount'])
            
            # Initialize payment date to invoice date
            payment_date = invoice_date
            remaining_amount = invoice_amount
            
            # Process payments until the invoice is fully paid
            while remaining_amount > 0:
                # Initialize the daily payment if not already tracked
                if payment_date not in daily_payments:
                    daily_payments[payment_date] = 0
                
                # Calculate how much can be paid today
                payment_amount = min(remaining_amount, 20000 - daily_payments[payment_date])
                
                # If payment can be made today
                if payment_amount > 0:
                    daily_payments[payment_date] += payment_amount
                    remaining_amount -= payment_amount
                    
                    # Add payment record
                    payment_records.append({
                        'Party Name': party_name,
                        'Invoice Number': invoice_number,
                        'Invoice Date': invoice_date.strftime('%d-%m-%Y'),
                        'Invoice Amount': invoice_amount,
                        'Payment Date': payment_date.strftime('%d-%m-%Y'),
                        'Payment Amount': round(payment_amount, 2)
                    })
                
                # Move to the next day if more payment is needed
                if remaining_amount > 0:
                    payment_date = payment_date + timedelta(days=1)
    
    # Convert to DataFrame and return
    payment_df = pd.DataFrame(payment_records)
    return payment_df

if __name__ == '__main__':
    try:
        # Read input data from stdin
        input_data = sys.stdin.read()
        
        # Process the data
        result = generate_payment_schedule(input_data)

        # Output the result to stdout
        if not result.empty:
            print(result.to_csv(index=False))
        else:
            print("No payment records generated.", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error processing payments: {e}", file=sys.stderr)
        sys.exit(1)