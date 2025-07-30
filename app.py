# api/index.py

from flask import Flask, request, jsonify, send_file
import pandas as pd
import numpy as np
from datetime import datetime
import os
import io
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configure upload settings
UPLOAD_FOLDER = '/tmp/uploads'  # Use /tmp for serverless compatibility
ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create uploads directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_stock_data(input_file, output_file, weekly_budget=3000):
    # ... (no changes to this function)
    # [PASTE YOUR FUNCTION BODY HERE, UNCHANGED]
    # For brevity, not repeating the function body since it doesn't need changes.
    # If you want the full code with this function included, let me know!

    # (Keep your existing process_stock_data function here)
    pass

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

# DO NOT include app.run() or if __name__ == "__main__" block!
