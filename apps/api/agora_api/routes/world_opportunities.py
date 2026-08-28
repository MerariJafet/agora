"""World opportunity market routes."""

from fastapi import APIRouter, Request, Response

from agora_api.world_opportunities import build_opportunity_market

router = APIRouter(prefix="/v1/world", tags=["world"])


@router.get("/opportunities", response_model=None)
async def world_opportunities(request: Request, response: Response) -> dict | Response:
    market = build_opportunity_market()
    etag = f'W/"{market["market_hash"][:32]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=304,
            headers={"etag": etag, "cache-control": "public, max-age=60"},
        )
    response.headers["etag"] = etag
    response.headers["cache-control"] = "public, max-age=60, must-revalidate"
    return market
