from fastapi import APIRouter, HTTPException, Query

from app.core.resolve import resolve_link

router = APIRouter(prefix="/api", tags=["resolve"])


@router.get("/resolve")
async def resolve(url: str = Query(..., description="Platform linki veya kanal adi")):
    r = resolve_link(url)
    if r is None:
        raise HTTPException(status_code=400, detail="Link taninamadi")
    return r.to_dict()