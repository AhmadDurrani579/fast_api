from fastapi import APIRouter

router = APIRouter(prefix="/expense", tags=["expense"])

CATEGORIES = [
    {"name": "Groceries", "icon": "🛒"},
    {"name": "Food", "icon": "🍽"},
    {"name": "Transport", "icon": "🚌"},
    {"name": "Health", "icon": "💊"},
    {"name": "Gifts", "icon": "🎁"},
    {"name": "Rent", "icon": "🏠"},
    {"name": "Utilities", "icon": "⚡"},
    {"name": "Entertainment", "icon": "🎉"},
    {"name": "Education", "icon": "📚"},
    {"name": "Insurance", "icon": "🛡"},
]

@router.get("/categories")
def get_categories():
    return {"status": True, "categories": CATEGORIES}