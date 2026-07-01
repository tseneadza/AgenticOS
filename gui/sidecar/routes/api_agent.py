"""Agent API endpoints (Phase 10 / NF-3, FR-53).

GET  /api/agent/models   — list available models (Anthropic + Ollama)
GET  /api/agent/active   — current active model
POST /api/agent/model    — switch active model
"""
from fastapi import APIRouter, HTTPException, Query
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/agent/models")
async def list_models():
    """List all available LLM models (cloud + local Ollama).

    Returns list of {id, provider, label, context_window, supports_tools, cost_per_mtok}.
    Cloud models priced, local models free ($0).
    """
    try:
        from core import llm
        models = llm.registry()

        result = []
        for model in models:
            result.append({
                "id": model.id,
                "provider": model.provider,
                "label": model.label,
                "context_window": model.context_window,
                "supports_tools": model.supports_tools,
                "cost_per_mtok": model.cost_per_mtok.get("input", 0.0)  # use input cost
            })

        return {"models": result}

    except Exception as e:
        logger.error(f"Error listing models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/agent/active")
async def get_active_model():
    """Return currently active model info + provider."""
    try:
        from core import llm

        active_id = llm.active_model()
        model_info = llm.get_model_info(active_id)

        if not model_info:
            raise HTTPException(status_code=404, detail=f"Model not found: {active_id}")

        return {
            "id": model_info.id,
            "provider": model_info.provider,
            "label": model_info.label,
            "is_local": model_info.is_local,
            "supports_tools": model_info.supports_tools,
            "cost_per_mtok": model_info.cost_per_mtok.get("input", 0.0),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting active model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/agent/model")
async def set_active_model(model_id: str = Query(..., description="Model ID to activate")):
    """Switch active model.

    Args:
        model_id: Model identifier (e.g., 'claude-3.5-sonnet', 'qwen2.5:7b-instruct')

    Returns:
        {success, active_model, message}
    """
    try:
        from core import llm

        # Validate model exists
        model_info = llm.get_model_info(model_id)
        if not model_info:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model: {model_id}. Run GET /api/agent/models to list available."
            )

        # Set it
        result = llm.set_active_model(model_id)

        return {
            "success": True,
            "active_model": result.id,
            "provider": result.provider,
            "message": f"Switched to {result.label}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting active model: {e}")
        raise HTTPException(status_code=500, detail=str(e))
