from fastapi import FastAPI,Request
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim
from fastapi.middleware.cors import CORSMiddleware
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
import re
import requests
import datetime
import pydantic
import motor.motor_asyncio

app = FastAPI()


origins = [
    "https://simple-smart-hub-client.netlify.app",
    "http://127.0.0.1:8000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


pydantic.json.ENCODERS_BY_TYPE[ObjectId] = str

client = motor.motor_asyncio.AsyncIOMotorClient("mongodb+srv://jeromewalters:devilswag@cluster0.bbcfvve.mongodb.net/")
db = client.iot_platform
Parameter_values = db['parameter_values']
ESP_values = db['ESP_vales']

#This gets the latitude and longitude 
geolocator = Nominatim(user_agent="MyApp")
location = geolocator.geocode("Hyderabad")

user_latitude = location.latitude
user_longitude = location.longitude
user_date = datetime.datetime.now().strftime('%Y-%m-%d')

def getsunset() :

    url = "https://sunrise-sunset-times.p.rapidapi.com/getSunriseAndSunset"

    querystring = {"date":user_date,"latitude":user_latitude,"longitude":user_longitude,"timeZoneId":"Jamaica"}

    headers = {
        "X-RapidAPI-Key": "2333ff7921msh39e6da691a378f7p185751jsn5f4263451f36",
        "X-RapidAPI-Host": "sunrise-sunset-times.p.rapidapi.com"
    }

    response = requests.get(url, headers=headers, params=querystring)
    sunsettime = datetime.datetime.strptime(response["sunset"],"%H:%M:%S")

    return sunsettime


regex = re.compile(r'((?P<hours>\d+?)h)?((?P<minutes>\d+?)m)?((?P<seconds>\d+?)s)?')

def parse_time(time_str):
    parts = regex.match(time_str)
    if not parts:
        return
    parts = parts.groupdict()
    time_params = {}
    for name, param in parts.items():
        if param:
            time_params[name] = int(param)
    return timedelta(**time_params)

@app.put("/settings")
async def temp_light_dur(request: Request):
    parameters = await request.json()
    temperature = parameters['user_temp']

    if parameters["user_light"] == "sunset":
        light = getsunset() 
    else:
        light = datetime.datetime.strptime(str(parameters["user_light"]),"%H:%M:%S")
    
    user_light = parse_time(parameters["light_duration"]) + light
    user_light_time = user_light.strftime("%H:%M:%S")  # Format time as HH:MM:SS

    exp_response = {
        "user_temp" : temperature,
        "user_light" : light.strftime("%H:%M:%S"),  # Format light as HH:MM:SS
        "light_time_off": user_light_time
    }

    obj = await Parameter_values.find().sort('_id', -1).limit(1).to_list(1)

    if obj:
        await Parameter_values.update_one({"_id": obj[0]["_id"]}, {"$set": exp_response})
        new_obj = await Parameter_values.find_one({"_id": obj[0]["_id"]})
    else:
        new = await Parameter_values.insert_one(exp_response)
        new_obj = await Parameter_values.find_one({"_id": new.inserted_id})

    return new_obj


@app.get("/graph")
async def graph(request: Request):
    size = int(request.query_params.get('size'))
    readings = await Parameter_values.find().to_list(size)
    ESP_values = []
    for reading in readings:
        temperature = reading.get("temperature")
        presence = reading.get("presence")
        present_time = reading.get("present_time")

        
        ESP_values.append({
            "temperature": temperature,
            "presence": presence,
            "datetime": present_time
        })
    return ESP_values

@app.put("/api/temperature")  #put requests
async def toggle(request: Request): 
    state = await request.json()  # Wait for request
    present_time = datetime.datetime.now()
    settings = await Parameter_values.find().to_list(1)
    user_temp = float(settings[0]["user_temp"]) 
    user_light = datetime.datetime.strptime(settings[0]["user_light"], "%H:%M:%S")
    light_timeoff = datetime.datetime.strptime(settings[0]["light_time_off"], "%H:%M:%S")

    state["light"] = (user_light.time() < present_time.time() < light_timeoff.time()) and (state["presence"])  # Compare the current time with sunset time and light time off to get a True or False result
    state["fan"] = (float(state["temperature"]) >= user_temp) and (state["presence"])  # Compare the temperature with user-defined temperature to get True or False result
    state["present_time"] = str(present_time)

    obj = await ESP_values.insert_one(state)
    new_obj = await ESP_values.find_one({"_id": obj.inserted_id}) 
    return new_obj, 204


@app.get("/api/state")
async def get_state():
  state = await ESP_values.find().sort("_id",-1).limit(1).to_list(1)
  
  if state == None:
    return  {
            "fan": False, 
            "light": False,
            "presence" : False,
            "present_time" : datetime.now()
            }
  return state[0]


 

 
