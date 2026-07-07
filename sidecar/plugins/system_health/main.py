import psutil

alerts_history = []

def on_metrics(ctx):
    cpu = ctx.get("cpu_percent", 0)
    mem = ctx.get("memory_percent", 0)
    disk = ctx.get("disk_percent", 0)
    temp = getattr(psutil, "sensors_temperatures", lambda: {})()
    cpu_temp = "N/A"
    if "cpu_thermal" in temp:
        cpu_temp = f"{temp['cpu_thermal'][0].current}°C"
    elif "coretemp" in temp:
        cpu_temp = f"{temp['coretemp'][0].current}°C"
    return {"cpu_temp": cpu_temp, "checks": {"cpu": cpu, "memory": mem, "disk": disk}}

def on_schedule(ctx):
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory().percent
    if cpu > 95 or mem > 95:
        alerts_history.append({"cpu": cpu, "memory": mem, "time": str(ctx.get("now", ""))})
        if len(alerts_history) > 10:
            alerts_history.pop(0)
        return {"alert": True, "actions": ["close heavy apps"]}
    return {"alert": False}
