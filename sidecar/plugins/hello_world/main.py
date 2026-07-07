def on_ready(ctx):
    print(f"[HelloWorld] Plugin ready! ID: {ctx['plugin_id']}")
    return {"greeting": "Hello from AIVO plugin system!"}
