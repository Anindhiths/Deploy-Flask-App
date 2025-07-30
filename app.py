from flask import Flask, request, jsonify, send_file
import pandas as pd
import numpy as np
from datetime import datetime
import os
import io
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configure upload settings
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create uploads directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
        output_file = output_file_csv

    return buy_transactions, sell_transactions, output_file

@app.route("/")
def home():
    return """
    <h1>Stock Data Processor API</h1>
    <p>Welcome to the Stock Data Processing Service!</p>
    <h2>Available Endpoints:</h2>
    <ul>
        <li><strong>GET /</strong> - This home page</li>
        <li><strong>GET /api</strong> - API information</li>
        <li><strong>GET /turtle</strong> - Turtle endpoint</li>
        <li><strong>POST /process-stock</strong> - Process stock data file</li>
        <li><strong>GET /health</strong> - Health check</li>
    </ul>
    <h2>How to use /process-stock:</h2>
    <p>Send a POST request with:</p>
    <ul>
        <li><strong>file</strong>: CSV or Excel file containing stock data</li>
        <li><strong>weekly_budget</strong> (optional): Weekly investment budget (default: 3000)</li>
        <li><strong>output_format</strong> (optional): 'csv' or 'xlsx' (default: same as input)</li>
    </ul>
    """

@app.route("/api")
def api():
    return jsonify({
        "message": "Hello, API!",
        "version": "1.0",
        "endpoints": {
            "/": "Home page",
            "/api": "API information",
            "/turtle": "Turtle endpoint",
            "/process-stock": "Stock data processing endpoint",
            "/health": "Health check"
        }
    })

@app.route("/turtle")
def turtle():
    return "Hello, Turtle!"

@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    })

@app.route("/process-stock", methods=['POST'])
def process_stock():
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({"error": "Invalid file format. Please upload CSV, XLS, or XLSX files"}), 400
        
        # Get optional parameters
        weekly_budget = float(request.form.get('weekly_budget', 3000))
        output_format = request.form.get('output_format', '').lower()
        
        # Secure the filename
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save uploaded file
        file.save(input_path)
        
        # Determine output format
        if output_format not in ['csv', 'xlsx']:
            # Use same format as input
            input_ext = os.path.splitext(filename)[1].lower()
            output_format = 'xlsx' if input_ext in ['.xlsx', '.xls'] else 'csv'
        
        # Create output filename
        base_name = os.path.splitext(filename)[0]
        output_filename = f"{base_name}_processed.{output_format}"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        # Process the stock data
        buy_transactions, sell_transactions, actual_output_path = process_stock_data(
            input_path, output_path, weekly_budget
        )
        
        # Prepare response data
        buy_txns_data = []
        for txn in buy_transactions:
            buy_txns_data.append({
                'date': txn['date'].strftime('%d-%b-%y'),
                'price': txn['price'],
                'quantity': txn['quantity'],
                'average': round(txn['average'], 2),
                'total_invested': round(txn['total_invested'], 2)
            })
        
        sell_txns_data = []
        for txn in sell_transactions:
            sell_txns_data.append({
                'date': txn['date'].strftime('%d-%b-%y'),
                'price': txn['price'],
                'quantity': txn['quantity'],
                'profit': round(txn['profit'], 2),
                'total_profit': round(txn['total_profit'], 2)
            })
        
        # Calculate summary statistics
        total_profit = sum(txn['profit'] for txn in sell_transactions)
        current_holdings = 0
        total_invested = 0
        
        if buy_transactions and sell_transactions:
            # Calculate current holdings (if any remaining)
            total_bought = sum(txn['quantity'] for txn in buy_transactions)
            total_sold = sum(txn['quantity'] for txn in sell_transactions)
            current_holdings = total_bought - total_sold
            
            if current_holdings > 0:
                # Calculate current investment based on remaining holdings
                for txn in reversed(buy_transactions):
                    if current_holdings > 0:
                        total_invested += min(current_holdings, txn['quantity']) * txn['price']
                        current_holdings -= min(current_holdings, txn['quantity'])
        
        # Clean up input file
        os.remove(input_path)
        
        response_data = {
            "message": "Stock data processed successfully",
            "summary": {
                "total_buy_transactions": len(buy_transactions),
                "total_sell_transactions": len(sell_transactions),
                "total_profit_realized": round(total_profit, 2),
                "weekly_budget": weekly_budget,
                "output_format": output_format
            },
            "buy_transactions": buy_txns_data,
            "sell_transactions": sell_txns_data,
            "download_url": f"/download/{os.path.basename(actual_output_path)}"
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        # Clean up files in case of error
        if 'input_path' in locals() and os.path.exists(input_path):
            os.remove(input_path)
        if 'output_path' in locals() and os.path.exists(output_path):
            os.remove(output_path)
        
        return jsonify({"error": f"Error processing file: {str(e)}"}), 500

@app.route("/download/<filename>")
def download_file(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": f"Error downloading file: {str(e)}"}), 500

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large. Maximum size is 16MB"}), 413

if __name__ == "__main__":
    app.run(debug=True)
