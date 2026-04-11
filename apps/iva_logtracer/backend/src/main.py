import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add the apps directory and shared libs to sys.path
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent.parent.parent # The root of the whole repo
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Add shared libs
kibana_lib = project_root / "tools" / "python" / "libs" / "kibana"
if str(kibana_lib) not in sys.path:
    sys.path.insert(0, str(kibana_lib))

try:
    from .routers import logtracer, turn_analysis
    from .routers import websocket as ws_router
except ImportError:
    from routers import logtracer, turn_analysis
    from routers import websocket as ws_router

app = FastAPI(
    title="IVA LogTracer API",
    description="Backend for IVA Log Correlation and Tracing",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(logtracer.router, prefix="/api")
app.include_router(ws_router.router, prefix="/api")
app.include_router(turn_analysis.router, prefix="/api")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "iva-logtracer"}

if __name__ == "__main__":
    import os

    import uvicorn
    port = int(os.getenv("PORT", 8190))
    uvicorn.run(app, host="0.0.0.0", port=port)
