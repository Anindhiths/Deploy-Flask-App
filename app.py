from flask import Flask, request, render_template, send_file, flash, redirect, url_for
import pandas as pd
import numpy as np
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import tempfile

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this to a random secret key
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # Check if file was uploaded
        if 'file' not in request.files:
            flash('No file selected')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            # Get weekly budget from form
            weekly_budget = float(request.form.get('weekly_budget', 3000))
            
            # Create temporary files
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_input:
                file.save(temp_input.name)
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_output:
                    try:
                        # Process the file
                        buy_txns, sell_txns = process_stock_data(temp_input.name, temp_output.name, weekly_budget)
                        
                        # Send the processed file
                        return send_file(temp_output.name, 
                                       as_attachment=True, 
                                       download_name='processed_stock_data.xlsx',
                                       mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                    
                    except Exception as e:
                        flash(f'Error processing file: {str(e)}')
                        return redirect(request.url)
                    finally:
                        # Clean up temporary files
                        try:
                            os.unlink(temp_input.name)
                            os.unlink(temp_output.name)
                        except:
                            pass
        else:
            flash('Invalid file type. Please upload CSV or Excel files only.')
            return redirect(request.url)
    
    return render_template('upload.html')

def process_stock_data(input_file, output_file, weekly_budget=3000):
    """
    Process stock data and generate buy signals based on weekly high breakouts
    Supports both CSV and Excel (.xlsx) formats for input and output files

    Args:
        input_file (str): Path to input CSV or Excel file
        output_file (str): Path to output CSV or Excel file
        weekly_budget (float): Weekly investment budget
    """

    # Determine file format and read accordingly
    input_ext = os.path.splitext(input_file)[1].lower()

    if input_ext == '.csv':
        df = pd.read_csv(input_file)
    elif input_ext in ['.xlsx', '.xls']:
        df = pd.read_excel(input_file)
    else:
        raise ValueError(f"Unsupported input file format: {input_ext}. Please use .csv, .xlsx, or .xls files.")

    # Convert Date column to datetime
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y')

    # Initialize tracking variables
    total_invested = 0
    total_quantity = 0
    buy_transactions = []
    sell_transactions = []
    current_holdings = 0  # Current quantity held
    total_profit = 0  # Total profit from all sales

    # Create output dataframe
    output_rows = []

    # Group data by weeks (assuming Monday starts the week)
    df['Week'] = df['Date'].dt.isocalendar().week
    df['Year'] = df['Date'].dt.year

    weeks = df.groupby(['Year', 'Week'])
    week_list = list(weeks)

    prev_week_max_high = 0

    for i, (week_key, week_data) in enumerate(week_list):
        week_data = week_data.sort_values('Date').reset_index(drop=True)
        current_week_max_high = week_data['HIGH'].max()

        # Check if we should buy this week
        buy_triggered = False
        sell_triggered = False
        buy_price = 0
        buy_quantity = 0
        buy_date_idx = -1
        sell_price = 0
        sell_quantity = 0
        sell_date_idx = -1

        if prev_week_max_high > 0:  # Skip first week as there's no previous week
            # Check each day in the current week
            for idx, row in week_data.iterrows():
                current_price = row['HIGH']  # Use HIGH as potential sell price

                # Check for sell signal first (if we have holdings)
                if current_holdings > 0 and not sell_triggered:
                    average_buy_price = total_invested / total_quantity if total_quantity > 0 else 0
                    if average_buy_price > 0:
                        profit_percentage = ((current_price - average_buy_price) / average_buy_price) * 100
                        if profit_percentage >= 20:  # 20% profit target
                            sell_triggered = True
                            sell_price = current_price
                            sell_quantity = current_holdings  # Sell all holdings
                            sell_date_idx = idx

                            # Update tracking variables for sale
                            sale_amount = sell_quantity * sell_price
                            cost_basis = sell_quantity * average_buy_price
                            profit = sale_amount - cost_basis
                            total_profit += profit

                            # Reset holdings after sale
                            current_holdings = 0
                            total_invested = 0
                            total_quantity = 0

                            sell_transactions.append({
                                'date': row['Date'],
                                'price': sell_price,
                                'quantity': sell_quantity,
                                'profit': profit,
                                'total_profit': total_profit
                            })
                            continue  # Don't buy on the same day we sell

                # Check for buy signal (only if no sell signal triggered)
                if row['HIGH'] > prev_week_max_high and not buy_triggered and not sell_triggered:
                    # Trigger buy
                    buy_triggered = True
                    buy_price = row['HIGH']
                    buy_quantity = round(weekly_budget / buy_price)
                    buy_date_idx = idx

                    # Update tracking variables
                    investment_amount = buy_quantity * buy_price
                    total_invested += investment_amount
                    total_quantity += buy_quantity
                    current_holdings += buy_quantity

                    # Calculate average price
                    if total_quantity > 0:
                        average_price = total_invested / total_quantity
                    else:
                        average_price = 0

                    buy_transactions.append({
                        'date': row['Date'],
                        'price': buy_price,
                        'quantity': buy_quantity,
                        'average': average_price,
                        'total_invested': total_invested
                    })
                    break

        # Add week data to output
        for idx, row in week_data.iterrows():
            output_row = {
                'Date': row['Date'].strftime('%d-%b-%y'),
                'Day': row['Date'].strftime('%A'),  # Generate day name from date
                'OPEN': row['OPEN'],
                'HIGH': row['HIGH'],
                'LOW': row['LOW'],
                'PREV. CLOSE': row['PREV. CLOSE'],
                'LTP': row['ltp'],
                'CLOSE': row['close'],
                'VWAP': row['vwap'],
                'Price:': '',
                'Value1': ''
            }

            # Add buy information if this is the buy day
            if buy_triggered and idx == buy_date_idx:
                output_row['Price:'] = 'Buy Price:'
                output_row['Value1'] = buy_price

            # Add sell information if this is the sell day
            if sell_triggered and idx == sell_date_idx:
                output_row['Price:'] = 'Sell Price:'
                output_row['Value1'] = sell_price

            output_rows.append(output_row)

        # Add buy transaction details after the buy day
        if buy_triggered:
            transaction = buy_transactions[-1]

            # Add quantity row
            output_rows.append({
                'Date': '', 'Day': '', 'OPEN': '', 'HIGH': '', 'LOW': '',
                'PREV. CLOSE': '', 'LTP': '', 'CLOSE': '', 'VWAP': '',
                'Price:': 'Quantity:', 'Value1': transaction['quantity']
            })

            # Add average row
            output_rows.append({
                'Date': '', 'Day': '', 'OPEN': '', 'HIGH': '', 'LOW': '',
                'PREV. CLOSE': '', 'LTP': '', 'CLOSE': '', 'VWAP': '',
                'Price:': 'Average:', 'Value1': round(transaction['average'], 2)
            })

            # Add total invested row
            output_rows.append({
                'Date': '', 'Day': '', 'OPEN': '', 'HIGH': '', 'LOW': '',
                'PREV. CLOSE': '', 'LTP': '', 'CLOSE': '', 'VWAP': '',
                'Price:': 'Total Invested:', 'Value1': round(transaction['total_invested'], 1)
            })

        # Add sell transaction details after the sell day
        if sell_triggered:
            transaction = sell_transactions[-1]

            # Add quantity row
            output_rows.append({
                'Date': '', 'Day': '', 'OPEN': '', 'HIGH': '', 'LOW': '',
                'PREV. CLOSE': '', 'LTP': '', 'CLOSE': '', 'VWAP': '',
                'Price:': 'Quantity:', 'Value1': transaction['quantity']
            })

            # Add profit row
            output_rows.append({
                'Date': '', 'Day': '', 'OPEN': '', 'HIGH': '', 'LOW': '',
                'PREV. CLOSE': '', 'LTP': '', 'CLOSE': '', 'VWAP': '',
                'Price:': 'Profit:', 'Value1': round(transaction['profit'], 2)
            })

            # Add total profit row
            output_rows.append({
                'Date': '', 'Day': '', 'OPEN': '', 'HIGH': '', 'LOW': '',
                'PREV. CLOSE': '', 'LTP': '', 'CLOSE': '', 'VWAP': '',
                'Price:': 'Total Profit:', 'Value1': round(transaction['total_profit'], 2)
            })

        # Add blank row after each week (except last week)
        if i < len(week_list) - 1:
            output_rows.append({
                'Date': '', 'Day': '', 'OPEN': '', 'HIGH': '', 'LOW': '',
                'PREV. CLOSE': '', 'LTP': '', 'CLOSE': '', 'VWAP': '',
                'Price:': '', 'Value1': ''
            })

        # Update previous week max high for next iteration
        prev_week_max_high = current_week_max_high

    # Add price information to first row
    if output_rows:
        output_rows[0]['Price:'] = 'Price:'
        output_rows[0]['Value1'] = weekly_budget

    # Create output DataFrame
    output_df = pd.DataFrame(output_rows)

    # Rename columns to match your output format
    output_df.columns = ['Date', 'Day', 'OPEN', 'HIGH', 'LOW', 'PREV. CLOSE',
                        'LTP', 'CLOSE', 'VWAP', '', '']

    # Save to file based on output file extension
    output_ext = os.path.splitext(output_file)[1].lower()

    if output_ext == '.csv':
        output_df.to_csv(output_file, index=False)
    elif output_ext in ['.xlsx', '.xls']:
        output_df.to_excel(output_file, index=False, engine='openpyxl')
    else:
        # Default to CSV if extension is not recognized
        output_file_csv = os.path.splitext(output_file)[0] + '.csv'
        output_df.to_csv(output_file_csv, index=False)
        print(f"Warning: Unrecognized output format. Saved as CSV: {output_file_csv}")

    # Print summary
    print(f"Processing complete!")
    print(f"Input file format: {input_ext.upper()}")
    print(f"Output file format: {output_ext.upper()}")
    print(f"Total buy transactions: {len(buy_transactions)}")
    print(f"Total sell transactions: {len(sell_transactions)}")
    print(f"Current holdings: {current_holdings} shares")
    if current_holdings > 0:
        print(f"Current investment: ₹{total_invested:.2f}")
        print(f"Average price: ₹{total_invested/total_quantity:.2f}")
    print(f"Total profit realized: ₹{total_profit:.2f}")

    return buy_transactions, sell_transactions

if __name__ == '__main__':
    app.run(debug=True)
