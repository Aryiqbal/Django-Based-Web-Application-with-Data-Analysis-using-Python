from datetime import datetime
import MetaTrader5 as mt
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import pmdarima as pm
import statsmodels.api as sm
from flask import Flask, render_template, request
from io import BytesIO
import base64
from keras.models import Sequential
from keras.layers import LSTM, Dense
from flask import jsonify
import io
import sys
import re

app = Flask(__name__)

def arima_predict(training_data, testing_data):
    autoarima_model = pm.auto_arima(training_data, seasonal=False, suppress_warnings=True)
    best_pdq = autoarima_model.order

    model_predictions = []
    for i in range(len(testing_data)):
        model = sm.tsa.ARIMA(training_data, order=best_pdq)
        model_fit = model.fit()
        output = model_fit.forecast(steps=1)
        yhat = output[0]
        model_predictions.append(yhat)
        actual_test_value = testing_data[i]
        training_data.append(actual_test_value)

    return model_predictions, model_fit.summary().as_text()
def lstm_predict(training_data, testing_data):
    # Save the original standard output
    original_stdout = sys.stdout
    # Redirect standard output to capture the summary
    sys.stdout = io.StringIO()

    # Reshape training data
    X_train = np.array(training_data).reshape(-1, 1, 1)
    y_train = np.array(training_data[1:]).reshape(-1, 1, 1)  # Shifted by one for sequence prediction

    # Ensure X_train and y_train have the same length
    min_length = min(X_train.shape[0], y_train.shape[0])
    X_train = X_train[:min_length]
    y_train = y_train[:min_length]
   
    # Define LSTM model
    model = Sequential()
    model.add(LSTM(50, activation='relu', input_shape=(1, 1)))
    model.add(Dense(1))
    model.compile(optimizer='adam', loss='mse')

    # Train LSTM model
    model_fit = model.fit(X_train, y_train, epochs=100, verbose=0)

    # Prepare testing data for prediction
    X_test = np.array(testing_data).reshape(-1, 1, 1)

    # Make predictions
    model_predictions = model.predict(X_test)

    # Get a summary of the model architecture
    sys.stdout.seek(0)  # Move the pointer to the beginning of the StringIO object
    model_summary_raw = sys.stdout.read()  # Read the captured output as a string

    # Remove formatting characters using regular expressions
    model_summary = re.sub(r'\x1b\[[0-9;]*m', '', model_summary_raw)

    # Restore the original standard output
    sys.stdout = original_stdout

    return model_predictions, model_summary


def predict(symbol, model_type):
    data = {}

    # Initialize MetaTrader5
    mt.initialize()

    # Credentials for MetaTrader5 demo account
    login = 10001610777
    password = 'Td@oQj5f'
    server = 'MetaQuotes-Demo'
    mt.login(login, password, server)

    # Define symbol and timeframe
    data["symbol"] = symbol
    timeframe = mt.TIMEFRAME_D1
    date_from = datetime(2023, 2, 15)
    date_to = datetime(2024, 2, 5)

    # Get data from MetaTrader5
    mt_data = pd.DataFrame(mt.copy_rates_range(symbol, timeframe, date_from, date_to))
    mt_data['time'] = pd.to_datetime(mt_data['time'], unit='s')
    mt_data.set_index('time', inplace=True)

    # Train Test Split
    to_row = int(len(mt_data) * 0.9)
    training_data = list(mt_data[0:to_row]['close'])
    testing_data = list(mt_data[to_row:]['close'])

    # Extract last closing price
    last_closing_price = mt_data.iloc[-1]['close']

    if model_type == 'ARIMA' or model_type == 'arima':
        model_predictions, model_summary = arima_predict(training_data, testing_data)
    elif model_type == 'LSTM' or model_type == 'lstm':
        model_predictions, model_summary = lstm_predict(training_data, testing_data)
        # model_summary = "LSTM model summary not available"


    data["model_summary"] = model_summary
    data["mape"] = np.mean(np.abs(np.array(model_predictions) - np.array(testing_data)) / np.abs(testing_data))
    data["last_closing_price"] = last_closing_price
    data["Final_Prediction"] =  model_predictions[-1]
    # Plot predictions
    plt.figure(figsize=(10, 6))
    plt.plot(mt_data.index[to_row:], model_predictions, color='blue', marker='o', linestyle='dashed',
             label='Currency Predicted Price')
    plt.plot(mt_data.index[to_row:], testing_data, color='red', marker='o', label='Currency Actual Price')
    plt.title('Currency Price Prediction')
    plt.xlabel('Date')
    plt.ylabel('Price')
    plt.legend()
    data["next_prediction"] =  model_predictions[+1]
    # Save the prediction plot to BytesIO object
    prediction_plot_buffer = BytesIO()
    plt.savefig(prediction_plot_buffer, format='png')
    prediction_plot_buffer.seek(0)

    # Convert the prediction plot to base64 string
    prediction_plot_base64 = base64.b64encode(prediction_plot_buffer.getvalue()).decode('utf-8')
    data["prediction_plot"] = prediction_plot_base64

    # Plot MT5 data
    plt.figure(figsize=(10, 6))
    plt.plot(mt_data.index, mt_data['close'])
    plt.xlabel('Date')
    plt.ylabel('Closing Prices')
    plt.title('MT5 Closing Prices')
    plt.legend(['MT5 Closing Prices'])

    # Save the MT5 plot to BytesIO object
    mt5_plot_buffer = BytesIO()
    plt.savefig(mt5_plot_buffer, format='png')
    mt5_plot_buffer.seek(0)

    # Convert the MT5 plot to base64 string
    mt5_plot_base64 = base64.b64encode(mt5_plot_buffer.getvalue()).decode('utf-8')
    data["mt5_plot"] = mt5_plot_base64
    

    return data

@app.route('/prediction', methods=['GET', 'POST'])
def prediction():
    if request.method == 'POST':
        symbol = request.form['symbol']
        model_type = request.form['model_type']
    else:
        symbol = 'XAUUSD'  # Default symbol
        model_type = 'ARIMA'  # Default model
    data = predict(symbol, model_type)
    return render_template('prediction.html', data=data)

if __name__ == '__main__':
    app.run(debug=True)
