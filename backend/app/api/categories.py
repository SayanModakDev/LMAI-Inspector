from typing import List
from fastapi import APIRouter
from app.database import schemas

router = APIRouter()

@router.get("/categories", response_model=List[schemas.CategoryInfo])
def get_categories():
    """Get list of supported product categories for inspection."""
    return [
        schemas.CategoryInfo(
            name="FOOD",
            display_name="Food & Beverages",
            description="Packaged food, drinks, and dietary items regulated under FSSAI and Legal Metrology.",
            supported=True
        ),
        schemas.CategoryInfo(
            name="COSMETIC",
            display_name="Cosmetics & Personal Care",
            description="Skincare, haircare, and personal hygiene products regulated under Drugs & Cosmetics Rules and Legal Metrology.",
            supported=True
        ),
        schemas.CategoryInfo(name="HOUSEHOLD", display_name="Household & Cleaning", description="Cleaning and household packaged commodities; category-specific rules can be added through the rule matrix.", supported=True),
        schemas.CategoryInfo(name="PHARMACEUTICAL", display_name="Pharmaceutical & Healthcare", description="Healthcare packages; regulatory rules require separately verified configuration.", supported=True),
        schemas.CategoryInfo(name="ELECTRONICS", display_name="Electronics & Other Packaged Goods", description="Electronic and other packaged commodities using general rules.", supported=True),
        schemas.CategoryInfo(
            name="ALL",
            display_name="General Packaged Commodity",
            description="General rules applicable to all packaged commodities.",
            supported=True
        ),
    ]
