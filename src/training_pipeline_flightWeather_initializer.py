import json
import os
import joblib
import pandas as pd
import numpy as np
import xgboost
import hopsworks
from datetime import datetime
from hsml.schema import Schema
from hsml.model_schema import ModelSchema
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error


def uniform_dataframe_for_training(df):
    '''
    Given a dataset with the columns names extracted from the APIs data, return a dataset (dataframe)
    uniformed in order to be possible training a model on that
    '''
    df.drop(columns={'trip_time', 'dep_ap_gate', 'airline_iata_code', 'flight_iata_number', 
                     'arr_ap_iata_code', 'status','dep_ap_iata_code', 'date', 'high_cloud', 
                     'medium_cloud', 'low_cloud', 'gusts_wind'}, inplace=True)

    # Some data should be casted to int64
    convert_column = ['pressure','total_cloud', 'sort_prep','humidity']
    for col in convert_column:
        df = df.astype({col: 'int64'})

    # Remove outliners in delay (dep_delay > 120)
    row_list = []
    for row in range(df.shape[0]):
        if (df.at[row, 'dep_delay'] > 120):
            row_list.append(row)
    df.drop(row_list, inplace = True)
    df.reset_index(inplace = True)
    df.drop(columns={'index'}, inplace = True)

    # Make wind_dir a categorical feature with numbers and not string labels
    dir_dict = {'SW':0,'S':1,'SE':2,'E':3,'NE':4,'N':5,'NW':6,'W':7}
    direction_list = []
    for row in range(df.shape[0]):
        direction = df.at[row, 'wind_dir']
        number = dir_dict.get(direction)
        direction_list.append(number)
    df.drop(columns={'wind_dir'}, inplace = True)
    df['wind_dir'] = direction_list

    return df


def create_last_model_performance_dataframe_row(size, model_metrics):
    today_current_datetime   = datetime.now()
    today_formatted_datetime = today_current_datetime.strftime("%Y-%m-%d_%H:%M:%S")
    mae = model_metrics.get('mae')
    mse = model_metrics.get('mse')

    columns = ['timestamp','dateset_size','mae','mse']
    row_df = pd.DataFrame(columns=columns)
    row_df.loc[0] = [today_formatted_datetime, size, mae, mse]

    return row_df




# Connect to hopsworks and get data
hopsworks_api_key = os.environ['HOPSWORKS_API_KEY']
project = hopsworks.login(api_key_value = hopsworks_api_key)
fs = project.get_feature_store()
feature_group = fs.get_feature_group(name = 'flight_weather_dataset', version=1)


# Read data into dataframe and preprocess the dataset 
df = feature_group.read(dataframe_type='pandas')
df = uniform_dataframe_for_training(df)


##### MODEL TRAINING #####
model = xgboost.XGBRegressor(eta= 0.1, max_depth= 7, n_estimators= 38, subsample= 0.8)
train, test = train_test_split(df, test_size=0.2)
Xtrain = train.drop(columns={'dep_delay'})
ytrain = train['dep_delay']
Xtest  = test.drop(columns={'dep_delay'})
ytest  = test['dep_delay']

# Train and test the model
model.fit(Xtrain, ytrain)
y_pred = model.predict(Xtest)
model_metrics = {'mae' :mean_absolute_error(ytest, y_pred), 'mse': mean_squared_error(ytest, y_pred)}
print(f'\nTrained model metrics: {model_metrics}\n')



##### MODEL SAVING #####
mr = project.get_model_registry()
model_dir  = "model_dir"
file_name  = 'flight_weather_delay_model.pkl'

if os.path.isdir(model_dir) == False:
    os.mkdir(model_dir)
# Save the model
joblib.dump(model, os.path.join(model_dir, file_name))


# Specify the schema of the models' input/output using the features (Xtrain) and labels (ytrain)
input_schema = Schema(Xtrain)
output_schema = Schema(ytrain)
model_schema = ModelSchema(input_schema, output_schema)


# Since the model cannot be overwritten, use the get_model/set_model workaround to create a new version of the model
# and set is as the most updated
flight_weather_delay_model = mr.python.create_model(
    name="flight_weather_delay_model", 
    metrics={"mean_absolute_error" : model_metrics[0]},
    model_schema=model_schema,
    version = 1,
    description="XGBoost Regression model for flight departure delays, trained on flight info and weather info"
)


# Upload the model to the model registry
flight_weather_delay_model.save(model_dir)


performance_df_row = create_last_model_performance_dataframe_row(df.shape[0], model_metrics)
performance_fg     = fs.get_or_create_feature_group(
                        name="model_performance",
                        version=1,
                        primary_key=['timestamp'], 
                        description="Daily update of model performance")
performance_fg.insert(performance_df_row)



  