import json
import os
import re
import time
import requests
import math
import joblib
import pandasql
import pandas as pd
import numpy as np
import xgboost
import sklearn
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.metrics import classification_report, confusion_matrix, mean_absolute_error, mean_squared_error
from sklearn import metrics
from datetime import datetime

# Select whether or not to select the best model and/or to evaluate them.
model_selection  = False
model_evaluation = False

# Load dataset
df = pd.read_csv('/mnt/c/Developer/University/SML/sml-project-2023-manfredi-meneghin/datasets/join_dataset_smhi_zyla.csv')


# Due to a not optimal flight API, some data as "DepApGate", "TimeTrip" cannot be calculated in new data
# Furthermore, the following columns are dropped:
df.drop(columns={'trip_time', 'depApGate'}, inplace = True)

# Due to a disproportion between categories and flights features (too mant for too few), the future columns are dropped:
# When there will be more data, it will be interesting to add them to the model
df.drop(columns={'airlineIataCode', 'flightIataNumber', 'arrApIataCode'}, inplace = True)

# Some data are used as a key, but are not made to be variables of our model, furthermore are dropped:
# If there will be data coming from different airports, it will be interesting to add 'depApIataCode' as variable.
df.drop(columns={'status','depApIataCode', 'date'}, inplace = True)

# Some data should be casted to int64
convert_column = ['pressure','total_cloud', 'high_cloud', 'medium_cloud', 'low_cloud', 'sort_prep','humidity']
for col in convert_column:
    df = df.astype({col: 'int64'})

# Remove outliners in delay (depDelay > 120)
row_list = []
for row in range(df.shape[0]):
  if (df.at[row, 'depDelay'] > 120):
    row_list.append(row)
df.drop(row_list, inplace = True)
df.reset_index(inplace = True)
df.drop(columns={'index'}, inplace = True)

# Since total_cloud can summarize the others:
df.drop(columns={'high_cloud', 'medium_cloud', 'low_cloud'}, inplace = True)

# Since wind_speed can summarize gusts_wind:
df.drop(columns={'gusts_wind'}, inplace = True)

# Make wind_dir a categorical feature with numbers and not string labels
dir_dict = {'SW':0,'S':1,'SE':2,'E':3,'NE':4,'N':5,'NW':6,'W':7}
direction_list = []
for row in range(df.shape[0]):
    direction = df.at[row, 'wind_dir']
    number = dir_dict.get(direction)
    direction_list.append(number)
df.drop(columns={'wind_dir'}, inplace = True)
df['wind_dir'] = direction_list
    

# Instanciate a new model, create test set and dataset
model = xgboost.XGBRegressor(eta= 0.1, max_depth= 7, n_estimators= 38, subsample= 0.8)
train, test = train_test_split(df, test_size=0.2)
Xtrain = train.drop(columns={'depDelay'})
ytrain = train['depDelay']
Xtest  = test.drop(columns={'depDelay'})
ytest  = test['depDelay']

# Train and test the model
model.fit(Xtrain, ytrain)
y_pred = model.predict(Xtest)
model_metrics = [mean_absolute_error(ytest, y_pred), mean_squared_error(ytest, y_pred)]
print(f'Metrics: {model_metrics}')


if (model_selection):

    clf = xgboost.XGBRegressor()
    gbc = GridSearchCV(clf, param_grid = [])

    if (model_evaluation):
        train, eval = train_test_split(train, test_size = 0.125)
        Xtrain = train.drop(columns={'depDelay'})
        ytrain = train['depDelay']
        Xeval  = eval.drop(columns={'depDelay'})
        yeval  = eval['depDelay']

        eval_set = [(Xeval, yeval)]

        clf = xgboost.XGBRegressor(eval_metric='rmse', early_stopping_rounds=10)
        params = {'n_estimators': np.arange(3,40,5), 
                    'max_depth': np.arange(3,15,2), 
                    'eta': np.arange(0.1, 1.5, 0.2)}
    
    else:
        clf = xgboost.XGBRegressor()
        params = {'n_estimators': np.arange(3,40,5), 
                    'max_depth': np.arange(3,15,2), 
                    'eta': np.arange(0.1, 2.5, 0.7),
                    'subsample': [0.7, 0.8]}

        gbc = GridSearchCV(clf, param_grid = params, cv = 3, n_jobs=-1, verbose=3, scoring='neg_root_mean_squared_error')
        gbc.fit(Xtrain, ytrain, verbose = 0)
        cv = pd.DataFrame(gbc.cv_results_)

    print(cv.sort_values(by = 'rank_test_score').T)
    print(gbc.best_params_)


# Save the model


  