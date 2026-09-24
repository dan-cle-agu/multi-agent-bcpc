import re
from typing import Dict, List, Union

from .database import paper_supplies

ITEM_NAME_ALIASES = {
    "A4 paper": ["a4 paper", "a4 printer paper", "a4 size printer paper", "printer paper", "standard copy paper", "white printer paper", "white paper", "copy paper"],
    "Letter-sized paper": ["letter-sized paper", "letter size paper", "letter paper"],
    "Cardstock": ["cardstock", "heavy cardstock", "sturdy cardstock", "high-quality cardstock", "heavyweight cardstock", "card stock"],
    "Colored paper": ["colored paper", "colour paper", "assorted colored paper", "various colors", "colorful paper", "colorful construction paper", "coloured paper", "construction paper"],
    "Glossy paper": ["glossy paper", "high-quality glossy paper", "a4 glossy paper", "a3 glossy paper"],
    "Matte paper": ["matte paper", "a3 matte paper", "a4 matte paper"],
    "Recycled paper": ["recycled paper", "recycled cardstock", "recycled kraft paper", "100% recycled kraft paper"],
    "Poster paper": ["poster paper", "poster board", "poster boards", "large poster paper", "24 x 36"],
    "Banner paper": ["banner paper", "rolls of banner paper", "banner"],
    "Paper plates": ["paper plates", "plates"],
    "Paper cups": ["paper cups", "cups"],
    "Paper napkins": ["paper napkins", "napkins"],
    "Disposable cups": ["disposable cups"],
    "Table covers": ["table covers", "table cover"],
    "Envelopes": ["envelopes", "kraft paper envelopes"],
    "Sticky notes": ["sticky notes", "notes"],
    "Notepads": ["notepads", "notepad"],
    "Invitation cards": ["invitation cards", "cards", "invitation card"],
    "Flyers": ["flyers", "flyer"],
    "Party streamers": ["streamers", "party streamers", "roll of streamers"],
    "Decorative adhesive tape (washi tape)": ["decorative washi tape", "washi tape", "adhesive tape"],
    "Paper party bags": ["paper party bags", "paper bags", "bags"],
    "Name tags with lanyards": ["name tags", "lanyards", "name tags with lanyards"],
    "Presentation folders": ["presentation folders", "folders"],
    "Heavyweight paper": ["heavyweight paper", "heavyweight cardstock", "sturdy paper"],
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def resolve_item_name(request_phrase: str) -> str | None:
    normalized = normalize_text(request_phrase)
    for item_name, aliases in ITEM_NAME_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return item_name
    return None


def parse_requested_items(request_text: str) -> List[Dict[str, Union[str, int]]]:
    matches: List[Dict[str, Union[str, int]]] = []
    pattern = re.compile(
        r"(\d+(?:,\d{3})?)\s*(?:sheets?|reams?|rolls?|packets?|boxes?|pieces?|boards?|cards?|balloons?)\s+(?:of\s+)?([^,.;\n]+)",
        flags=re.IGNORECASE,
    )
    for quantity_text, phrase in pattern.findall(request_text):
        quantity = int(quantity_text.replace(",", ""))
        item_name = resolve_item_name(phrase)
        if item_name is None:
            continue
        matches.append({"item_name": item_name, "quantity": quantity})

    if not matches:
        fallback = normalize_text(request_text)
        for item_name in list(ITEM_NAME_ALIASES.keys()):
            if any(alias in fallback for alias in ITEM_NAME_ALIASES[item_name]):
                matches.append({"item_name": item_name, "quantity": 1})

    return matches


def calculate_quote(item_name: str, quantity: int) -> Dict[str, float]:
    item_record = next((item for item in paper_supplies if item["item_name"] == item_name), None)
    if item_record is None:
        raise ValueError(f"Unknown item: {item_name}")
    unit_price = float(item_record["unit_price"])
    if quantity >= 1000:
        discount_rate = 0.12
    elif quantity >= 500:
        discount_rate = 0.08
    elif quantity >= 200:
        discount_rate = 0.05
    else:
        discount_rate = 0.0

    subtotal = unit_price * quantity
    discount_amount = subtotal * discount_rate
    total = subtotal - discount_amount
    return {
        "unit_price": unit_price,
        "subtotal": round(subtotal, 2),
        "discount_rate": discount_rate,
        "discount_amount": round(discount_amount, 2),
        "total": round(total, 2),
    }
