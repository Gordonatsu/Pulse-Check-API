from fastapi import FastAPI, HTTPException
from pydantic import BaseModel # Handles validation for fastAPI
from contextlib import asynccontextmanager
import asyncio
import time


async def watchdog(): # Continuously checks if any of the remote devices have gone offline
    while True:
        current_time = time.time() # it grabs the exact current time (in Unix seconds) and saves it as a benchmark.
        for monitor_id, data in monitors.items():
            
            # Watchdog only triggers if the status is strictly "active"
            if data["status"] == "active" and current_time >= data["expires_at"]:
                data["status"] = "down"
                alert_log = {
                    "ALERT": f"Device {monitor_id} is down!", 
                    "time": current_time,
                    "email_sent_to": data["alert_email"]
                }
                print(alert_log)
                
        await asyncio.sleep(1)

# For synchronization and gracefull shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(watchdog())
    yield # tells FastAPI the setup is done and can open the server to the internet and start answering API requests
    task.cancel()

# Creates an instance of fastAPI
app = FastAPI(title="Pulse-Check API", lifespan=lifespan, summary="A lightweight, stateful dead-man's switch API built for CritMon Servers Inc.")

# In-memory database
monitors = {}

class MonitorCreate(BaseModel): # MonitorCreate inherits the BaseModel to parse, validate, and convert the JSON data sent by the client into a Python object. 
    id: str
    timeout: int
    alert_email: str

# Registering a Monitor
@app.post("/monitors", status_code=201)
async def create_monitor(monitor: MonitorCreate):
    monitors[monitor.id] = {
        "timeout": monitor.timeout,
        "alert_email": monitor.alert_email,
        "expires_at": time.time() + monitor.timeout,
        "status": "active"
    }
    return {"message": f"Monitor created for {monitor.id}", "timeout": monitor.timeout} # returns a JSON message object

# The Heartbeat (Reset & Un-pause)
@app.post("/monitors/{id}/heartbeat", status_code=200)
async def heartbeat(id: str):
    if id not in monitors:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    if monitors[id]["status"] == "down":
        raise HTTPException(status_code=400, detail="Device is down. Requires manual intervention.")
        
    # Restart the countdown AND ensure status is active (un-pauses if paused)
    monitors[id]["status"] = "active"
    monitors[id]["expires_at"] = time.time() + monitors[id]["timeout"]
    return {"message": f"Heartbeat received. Timer reset for {id}."} # returns a JSON message object

# The "Snooze" Button
@app.post("/monitors/{id}/pause", status_code=200)
async def pause_monitor(id: str):
    if id not in monitors:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    # Change status to paused so the watchdog ignores it
    monitors[id]["status"] = "paused"
    return {"message": f"Monitor {id} paused. No alerts will fire until next heartbeat."} # returns a JSON message object

# System Dashboard - to enable the CritMon admin to view current devices still alive
@app.get("/monitors", status_code=200)
async def get_all_monitors():
    """
    Returns a real-time snapshot of all monitors, their statuses, 
    and how much time is left before they trigger an alert.
    """
    dashboard = {}
    current_time = time.time()
    
    for m_id, data in monitors.items():
        # Calculate remaining time (only if active)
        if data["status"] == "active":
            time_left = max(0, int(data["expires_at"] - current_time))
        else:
            time_left = 0
            
        dashboard[m_id] = {
            "status": data["status"],
            "alert_email": data["alert_email"],
            "time_left_seconds": time_left
        }
        
    return dashboard

# print(monitors.items())