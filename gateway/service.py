"""FastAPI Inference Gateway Service.

Provides a unified, privacy-preserving HTTP /generate endpoint for all 7 agents,
insulating the agent framework from local LLM serving details.
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from gateway.client import OllamaClient
from gateway.config import config
from gateway.schemas import GenerateRequest, GenerateResponse, HealthResponse
from web.dashboard import router as dashboard_router

app = FastAPI(
    title="RTL-Coder Local Inference Gateway & Dashboard",
    description="Privacy-preserving local inference gateway and interactive multi-agent hardware dashboard",
    version="1.0.0",
)

# Enable CORS for local client tools and web dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Dashboard & Management APIs
app.include_router(dashboard_router)

# Singleton Ollama client
ollama_client = OllamaClient()


@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check() -> HealthResponse:
    """Verifies that the inference gateway and local Ollama backend are operational."""
    connected, models = ollama_client.check_health()
    return HealthResponse(
        status="healthy" if connected else "degraded",
        ollama_connected=connected,
        primary_model=config.primary_model,
        available_models=models,
        host=config.host,
        port=config.port,
    )


@app.post("/generate", response_model=GenerateResponse, tags=["Inference"])
def generate(request: GenerateRequest) -> GenerateResponse:
    """Core endpoint: generates structured hardware collateral via local LLM."""
    response = ollama_client.generate(request)
    if not response.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=response.error_message or "Local LLM generation failed",
        )
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("gateway.service:app", host=config.host, port=config.port, reload=False)
