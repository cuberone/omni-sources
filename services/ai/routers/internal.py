"""Internal endpoints — for service-to-service calls only, not browser-exposed."""

import logging
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/memory/llm-config")
async def get_memory_llm_config(request: Request):
    """Return the active default LLM configuration for the memory service.

    Called by the memory service entrypoint at startup to discover which
    LLM provider/model/key mem0 should use — no credentials are hardcoded
    in the memory service image.
    """
    state = request.app.state
    models = getattr(state, "models", {})
    if not models:
        raise HTTPException(status_code=503, detail="No models configured")

    default_id = getattr(state, "default_model_id", None)
    provider = (
        models.get(default_id)
        if default_id
        else next(iter(models.values()), None)
    )
    if not provider:
        raise HTTPException(status_code=503, detail="No models configured")

    provider_type = getattr(provider, "provider_type", None)
    model_name = getattr(provider, "model_name", None)

    # Attempt to retrieve the API key from common provider attributes.
    api_key: str | None = None
    for attr in ("_api_key", "api_key", "_client"):
        val = getattr(provider, attr, None)
        if isinstance(val, str) and val:
            api_key = val
            break
        # AnthropicProvider stores it on _client.api_key
        if val is not None and hasattr(val, "api_key"):
            api_key = val.api_key
            break

    base_url: str | None = None
    for attr in ("_base_url", "base_url", "_api_url"):
        val = getattr(provider, attr, None)
        if isinstance(val, str) and val:
            base_url = val
            break

    return {
        "provider": provider_type,
        "model": model_name,
        "api_key": api_key,
        "base_url": base_url,
    }
