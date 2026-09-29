import re
from typing import Dict, List, Union

from .database import paper_supplies

ITEM_NAME_ALIASES = {
    "A4 paper": [
        "a4 printer paper", "a4 size printer paper", "a4 white printer paper",
        "a4 white paper", "a4 printing paper", "standard printer paper",
        "standard printing paper", "standard copy paper", "white printer paper",
        "white paper", "printer paper", "copy paper", "a4 paper",
    ],
    "Letter-sized paper": ["letter-sized paper", "letter size paper", "letter paper"],
    "Cardstock": [
        "high-quality white cardstock", "high quality cardstock", "heavy cardstock",
        "sturdy cardstock", "heavyweight cardstock", "card stock", "cardstock",
    ],
    "Colored paper": [
        "assorted colored paper", "colored paper", "colour paper", "colored sheets",
        "colourful paper", "colorful paper", "coloured paper",
    ],
    "Construction paper": ["colorful construction paper", "colored construction paper", "construction paper"],
    "Glossy paper": ["high-quality glossy paper", "glossy a4 paper", "a4 glossy paper", "glossy paper"],
    "Matte paper": ["matte a4 paper", "a4 matte paper", "matte paper"],
    "Recycled paper": ["recycled paper", "recycled kraft paper"],
    "Poster paper": ["colorful poster paper", "poster paper"],
    "Large poster paper (24x36 inches)": [
        "large poster paper", "poster boards", "poster board", "24 x 36 poster paper",
    ],
    "Banner paper": ["banner paper", "banner"],
    "Rolls of banner paper (36-inch width)": ["rolls of banner paper", "banner paper rolls"],
    "Paper plates": ["paper plates", "plates"],
    "Paper cups": ["paper cups", "cups"],
    "Paper napkins": ["paper napkins", "table napkins", "napkins"],
    "Disposable cups": ["disposable cups"],
    "Table covers": ["table covers", "table cover"],
    "Envelopes": ["kraft paper envelopes", "paper envelopes", "envelopes"],
    "Sticky notes": ["sticky notes"],
    "Notepads": ["notepads", "notepad"],
    "Invitation cards": ["invitation cards", "invitation card"],
    "Flyers": ["flyers", "flyer"],
    "Party streamers": ["party streamers", "streamers"],
    "Decorative adhesive tape (washi tape)": ["decorative washi tape", "washi tape"],
    "Paper party bags": ["paper party bags", "paper bags"],
    "Name tags with lanyards": ["name tags with lanyards", "name tags", "lanyards"],
    "Presentation folders": ["presentation folders", "folders"],
    "Heavyweight paper": ["heavyweight paper", "sturdy paper"],
}


def normalize_text(text: str) -> str:
    text = re.sub(r"\d+(?:\.\d+)?\s*(?:inches?|[\"'])?\s*[x×]\s*\d+(?:\.\d+)?\s*(?:inches?|[\"'])?", " ", text.lower())
    text = re.sub(r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def resolve_item_name(request_phrase: str) -> str | None:
    normalized = normalize_text(request_phrase)
    if re.search(r"\ba[35]\b", normalized):
        return None
    if "recycled cardstock" in normalized or "cardstock recycled" in normalized:
        return None

    matches = []
    for item_name, aliases in ITEM_NAME_ALIASES.items():
        for alias in aliases:
            normalized_alias = normalize_text(alias)
            if re.search(rf"\b{re.escape(normalized_alias)}\b", normalized):
                matches.append((len(normalized_alias), item_name))
    if matches:
        return max(matches)[1]

    for item in paper_supplies:
        normalized_name = normalize_text(item["item_name"])
        if normalized == normalized_name:
            return item["item_name"]
    return None


def parse_requested_items(request_text: str) -> List[Dict[str, Union[str, int]]]:
    cleaned_text = re.sub(
        r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b",
        " ",
        request_text,
        flags=re.IGNORECASE,
    )
    cleaned_text = re.sub(
        r"\d+(?:\.\d+)?\s*(?:inches?|[\"'])?\s*[x×]\s*\d+(?:\.\d+)?\s*(?:inches?|[\"'])?",
        " ",
        cleaned_text,
        flags=re.IGNORECASE,
    )
    quantity_pattern = re.compile(
        r"(?<![\w.])(?P<quantity>\d[\d,]*)(?![\d.])\s*(?:(?:sheets?|reams?|rolls?|packets?|boxes?|pieces?|boards?|cards?|units?)\s+)?(?:of\s+)?",
        flags=re.IGNORECASE,
    )
    quantity_matches = list(quantity_pattern.finditer(cleaned_text))
    requested_items: List[Dict[str, Union[str, int]]] = []

    for index, match in enumerate(quantity_matches):
        description_end = quantity_matches[index + 1].start() if index + 1 < len(quantity_matches) else len(cleaned_text)
        description = cleaned_text[match.end():description_end]
        description = re.split(
            r"[.;\n]|\b(?:please deliver|deliver(?:ed|y)? by|we need|i need|the supplies must|for (?:our|the|an) (?:upcoming )?(?:parade|reception|party|conference|assembly|exhibition|ceremony|concert|show|performance|demonstration))\b",
            description,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        description = re.sub(r"\(\s*\)", " ", description)
        description = re.sub(r",?\s+along with\s*$", "", description, flags=re.IGNORECASE)
        description = re.sub(r"\b(?:and|of)\s*$", "", description.strip(" ,:-\t"), flags=re.IGNORECASE)
        if not description:
            continue

        item_name = resolve_item_name(description)
        requested_items.append(
            {
                "item_name": item_name,
                "requested_name": re.sub(r"\s+", " ", description).strip(" ,:%-\t"),
                "quantity": int(match.group("quantity").replace(",", "")),
                "catalog_status": "in_catalog" if item_name else "not_in_catalog",
            }
        )

    return requested_items


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
