from fastapi import FastAPI, HTTPException
from config import config, OutputMode

app = FastAPI()

@app.post("/switch_mode")
async def switch_mode(mode: str):
    if mode not in [OutputMode.WEB, OutputMode.VTUBER]:
        raise HTTPException(status_code=400, detail="无效的输出模式")
    
    config["output_mode"] = mode
    return {"success": True, "current_mode": mode}

@app.get("/current_mode")
async def get_current_mode():
    return {"mode": config["output_mode"]}