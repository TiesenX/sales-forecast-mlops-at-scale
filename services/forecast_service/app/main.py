import datetime
import contextlib
import pandas as pd
import logging
import pprint
from typing import List
from fastapi import FastAPI
from pydantic import BaseModel
from handlers.mlflow import MLflowHandler
from helpers import ForecastRequest, create_forecast_index

log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(format=log_format, level=logging.INFO)

# consider using in-memory db such as Redis or Memcache
# in production for reliability and scalability
handlers = {}
models = {}
MODEL_BASE_NAME = f"prophet-retail-forecaster-store-"


async def get_model(store_id: str):
    global models
    model_name = MODEL_BASE_NAME + f"{store_id}"
    if model_name not in models:
        models[model_name] = handlers["mlflow"].get_production_model(store_id=store_id)
    return models[model_name]


async def get_service_handlers():
    global handlers
    mlflow_handler = MLflowHandler()
    handlers["mlflow"] = mlflow_handler
    logging.info("Retrieving mlflow handler...")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    await get_service_handlers()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health", status_code=200)
async def health_check():
    return {
        "serviceStatus": "OK",
        "modelTrackingHealth": handlers["mlflow"].check_mlflow_health(),
    }


@app.post("/forecast", status_code=200)
async def forecast(forecast_request: List[ForecastRequest]):
    """
    Main route in the app for returning the forecast, steps are:

    1. iterate over forecast elements
    2. get model for each store, forecast request
    3. prepare forecast input time index
    4. perform forecast
    5. append to return object
    6. return
    """
    forecasts = []
    for item in forecast_request:
        model = await get_model(item.store_id)
        forecast_input = create_forecast_index(
            begin_date=item.begin_date, end_date=item.end_date
        )
        forecast_result = {}
        forecast_result["request"] = item.dict()
        model_pred = model.predict(forecast_input)[["ds", "yhat"]]
        model_pred = model_pred.rename(columns={"ds": "timestamp", "yhat": "value"})
        model_pred["value"] = model_pred["value"].astype(int)
        forecast_result["forecast"] = model_pred.to_dict("records")
        forecasts.append(forecast_result)
    return forecasts
