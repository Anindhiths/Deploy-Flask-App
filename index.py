# api/index.py

import os
import tempfile
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import numpy as np
from datetime import datetime

app = FastAPI()

# Allow CORS for local dev/testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def process_stock_data(input_file, output_file, weekly_budget=3000):
    input_ext = os.path.splitext(input_file)[1].lower()
    if input_ext == '.csv':
        df = pd.read_csv(input_file)
    elif input_ext in ['.xlsx', '.xls']:
        df = pd.read_excel(input_file)
    else:
        raise ValueError(f"Unsupported input file format: {input_ext}. Please use .csv, .xlsx, or .xls files.")

    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y')
    total_invested = 0
    total_quantity = 0
    buy_transactions = []
    sell_transactions = []
    current_holdings = 0
    total_profit = 0
    output_rows = []
    df['Week'] = df['Date'].dt.isocalendar().week
    df['Year'] = df['Date'].dt.year
    weeks = df.groupby(['Year', 'Week'])
    week_list = list(weeks)
    prev_week_max_high = 0

    for i, (week_key, week_data) in enumerate(week_list):
        week_data = week_data.sort_values('Date').reset_index(drop=True)
        current_week_max_high = week_data['HIGH'].max()
        buy_triggered = False
        sell_triggered = False
        buy_price = 0
        buy_quantity = 0
        buy_date_idx = -1
        sell_price = 0
        sell_quantity = 0
        sell_date_idx = -1

        if prev_week_max_high > 0:
            for idx, row in week_data.iterrows():
                current_price = row['HIGH']
                if current_holdings > 0 and not sell_triggered:
                    average_buy_price = total_invested / total_quantity if total_quantity > 0 else 0
                    if average_buy_price > 0:
                        profit_percentage = ((current_price - average_buy_price) / average_buy_price) * 100
                        if profit_percentage >= 20:
                            sell_triggered = True
                            sell_price = current_price
                            sell_quantity = current_holdings
                            sell_date_idx = idx
                            sale_amount = sell_quantity * sell_price
                            cost_basis = sell_quantity * average_buy_price
                            profit = sale_amount - cost_basis
                            total_profit += profit
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
                            continue
                if row['HIGH'] > prev_week_max_high and not buy_triggered and not sell_triggered:
                    buy_triggered = True
                    buy_price = row['HIGH']
                    buy_quantity = round(weekly_budget / buy_price)
                    buy_date_idx = idx
                    investment_amount = buy_quantity * buy_price
                    total_invested += investment_amount
                    total_quantity += buy_quantity
                    current_holdings += buy_quantity
                    average_price = total_invested / total_quantity if total_quantity > 0 else 0
                    buy_transactions.append({
                        'date': row['Date'],
                        'price': buy_price,
                        'quantity': buy_quantity,
                        'average': average_price,
                        'total_invested': total_invested
                    })
                    break

        for idx, row in week_data.iterrows():
            output_row = {
                'Date': row['Date'].strftime('%d-%b-%y'),
                'Day': row['Date'].strftime('%A'),
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
            if buy_triggered and idx == buy_date_idx:
                output_row['Price:'] = 'Buy Price:'
                output_row['Value1'] = buy_price
            if sell_triggered and idx == sell_date_idx:
                output_row['Price:'] = 'Sell Price:'
                output_row['Value1'] = sell_price
            output_rows.append(output_row)
        if buy_triggered:
            transaction = buy_transactions[-1]
            output_rows.append({
                'Date': '', 'Day': '', 'OPEN': '', 'HIGH': '', 'LOW': '',
                'PREV. CLOSE': '', 'LTP': '', 'CLOSE': '', 'VWAP': '',
                'Price:': 'Quantity:', 'Value1': transaction['quantity']
            })
            output_rows.append({
                'Date': '', 'Day': '', 'OPEN': '', 'HIGH': '', 'LOW': '',
                'PREV. CLOSE': '', 'LTP': '', 'CLOSE': '', 'VWAP': '',
                'Price:': 'Average:', 'Value1': round(transaction['average'], 2)
            })
            output_rows.append({
                'Date': '', 'Day': '', 'OPEN': '', 'HIGH': '', 'LOW': '',
                'PREV. CLOSE': '', 'LTP': '', 'CLOSE': '', 'VWAP': '',
                'Price:': 'Total Invested:', 'Value1': round(transaction['total_invested'], 1)
            })
        if sell_triggered:
            transaction = sell_transactions[-1]
            output_rows.append({
                'Date': '', 'Day': '', 'OPEN': '', 'HIGH': '', 'LOW': '',
                'PREV. CLOSE': '', 'LTP': '', 'CLOSE': '', 'VWAP': '',
                'Price:': 'Quantity:', 'Value1': transaction['quantity']
            })
            output_rows.append({
                'Date': '', 'Day': '', 'OPEN': '', 'HIGH': '', 'LOW': '',
                'PREV. CLOSE': '', 'LTP': '', 'CLOSE': '', 'VWAP': '',
                'Price:': 'Profit:', 'Value1': round(transaction['profit'], 2)
            })
            output_rows.append({
                'Date': '', 'Day': '', 'OPEN': '', 'HIGH': '', 'LOW': '',
                'PREV. CLOSE': '', 'LTP': '', 'CLOSE': '', 'VWAP': '',
                'Price:': 'Total Profit:', 'Value1': round(transaction['total_profit'], 2)
            })
        if i < len(week_list) - 1:
            output_rows.append({
                'Date': '', 'Day': '', 'OPEN': '', 'HIGH': '', 'LOW': '',
                'PREV. CLOSE': '', 'LTP': '', 'CLOSE': '', 'VWAP': '',
                'Price:': '', 'Value1': ''
            })
        prev_week_max_high = current_week_max_high

    if output_rows:
        output_rows[0]['Price:'] = 'Price:'
        output_rows[0]['Value1'] = weekly_budget

    output_df = pd.DataFrame(output_rows)
    output_df.columns = ['Date', 'Day', 'OPEN', 'HIGH', 'LOW', 'PREV. CLOSE',
                        'LTP', 'CLOSE', 'VWAP', '', '']

    output_ext = os.path.splitext(output_file)[1].lower()
    if output_ext == '.csv':
        output_df.to_csv(output_file, index=False)
    elif output_ext in ['.xlsx', '.xls']:
        output_df.to_excel(output_file, index=False, engine='openpyxl')
    else:
        output_file_csv = os.path.splitext(output_file)[0] + '.csv'
        output_df.to_csv(output_file_csv, index=False)
    return output_file

@app.post("/process/")
async def process(
    file: UploadFile = File(...),
    weekly_budget: float = Form(3000)
):
    # Save uploaded file to a temp file in /tmp
    input_suffix = os.path.splitext(file.filename)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=input_suffix, dir="/tmp") as temp_input:
        temp_input.write(await file.read())
        temp_input.flush()
        input_path = temp_input.name

    # Prepare output file path in /tmp
    output_suffix = '.xlsx' if input_suffix in ['.xlsx', '.xls'] else '.csv'
    with tempfile.NamedTemporaryFile(delete=False, suffix=output_suffix, dir="/tmp") as temp_output:
        output_path = temp_output.name

    try:
        result_path = process_stock_data(input_path, output_path, weekly_budget)
        filename = f"processed_{file.filename.rsplit('.',1)[0]}{output_suffix}"
        return FileResponse(
            result_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if output_suffix == '.xlsx' else "text/csv"
        )
    except Exception as e:
        print("Error:", str(e))  # This will show up in Vercel logs
        return JSONResponse(status_code=400, content={"error": str(e)})
    finally:
        try:
            os.remove(input_path)
        except Exception:
            pass

# Health check
@app.get("/")
def root():
    return {"message": "Stock data processor is running."}
