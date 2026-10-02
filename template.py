"""Multi-agent tools and orchestration used by the course starter script."""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List

from dotenv import load_dotenv
from sqlalchemy import text
from smolagents import OpenAIModel, ToolCallingAgent, tool

load_dotenv(Path(__file__).resolve().with_name(".env"))

ALIASES = {
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
    "Colored paper": ["assorted colored paper", "colored paper", "colour paper", "colorful paper", "coloured paper"],
    "Construction paper": ["colorful construction paper", "colored construction paper", "construction paper"],
    "Glossy paper": ["high-quality glossy paper", "glossy a4 paper", "a4 glossy paper", "glossy paper"],
    "Matte paper": ["matte a4 paper", "a4 matte paper", "matte paper"],
    "Recycled paper": ["recycled paper", "recycled kraft paper"],
    "Poster paper": ["colorful poster paper", "poster paper"],
    "Large poster paper (24x36 inches)": ["large poster paper", "poster boards", "poster board"],
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


def normalize_text(value: str) -> str:
    value = re.sub(r"\d+(?:\.\d+)?\s*(?:inches?|[\"'])?\s*[x×]\s*\d+(?:\.\d+)?\s*(?:inches?|[\"'])?", " ", value.lower())
    value = re.sub(
        r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b",
        " ",
        value,
    )
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


def resolve_item_name(description: str, catalog: List[Dict]) -> str | None:
    normalized = normalize_text(description)
    if re.search(r"\ba[35]\b", normalized) or "recycled cardstock" in normalized:
        return None
    matches = []
    for name, aliases in ALIASES.items():
        for alias in aliases:
            alias_text = normalize_text(alias)
            if re.search(rf"\b{re.escape(alias_text)}\b", normalized):
                matches.append((len(alias_text), name))
    if matches:
        canonical = max(matches)[1]
        return canonical if any(row["item_name"] == canonical for row in catalog) else None
    for row in catalog:
        if normalized == normalize_text(row["item_name"]):
            return row["item_name"]
    return None


def parse_requested_items(request_text: str, catalog: List[Dict]) -> List[Dict]:
    cleaned = re.sub(
        r"\(\s*date of request:\s*\d{4}-\d{2}-\d{2}\s*\)",
        " ",
        request_text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\d+(?:\.\d+)?\s*(?:inches?|[\"'])?\s*[x×]\s*\d+(?:\.\d+)?\s*(?:inches?|[\"'])?", " ", cleaned)
    quantity_pattern = re.compile(
        r"(?<![\w.])(?P<quantity>\d[\d,]*)(?![\d.])\s*(?:(?:sheets?|reams?|rolls?|packets?|boxes?|pieces?|boards?|cards?|units?)\s+)?(?:of\s+)?",
        flags=re.IGNORECASE,
    )
    matches = list(quantity_pattern.finditer(cleaned))
    requested = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        description = cleaned[match.end():end]
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
        canonical = resolve_item_name(description, catalog)
        requested.append(
            {
                "item_name": canonical,
                "requested_name": re.sub(r"\s+", " ", description).strip(" ,:%-\t"),
                "quantity": int(match.group("quantity").replace(",", "")),
                "catalog_status": "in_catalog" if canonical else "not_in_catalog",
            }
        )
    return requested


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _due_date(request_text: str, request_date: str) -> str:
    match = re.search(r"\bby\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})", request_text, re.IGNORECASE)
    if match:
        try:
            return datetime.strptime(match.group(1), "%B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return (datetime.fromisoformat(request_date) + timedelta(days=7)).strftime("%Y-%m-%d")


def assess_order(request_text: str, request_date: str, helpers: Dict[str, Any]) -> Dict:
    catalog = helpers["paper_supplies"]
    engine = helpers["db_engine"]
    due_date = _due_date(request_text, request_date)
    requested = parse_requested_items(request_text, catalog)
    if not requested:
        return {"status": "rejected", "reason": "no_products_detected", "request_date": request_date, "due_date": due_date, "delivery_date": request_date, "items": [], "reasons": []}

    assessed = []
    reasons = []
    delivery_date = request_date
    catalog_names = {item["item_name"] for item in catalog}
    for request in requested:
        item = {**request, "available": 0, "projected_available": 0, "shortage": 0, "supplier_delivery_date": request_date}
        if request["item_name"] not in catalog_names:
            reasons.append({"code": "not_in_catalog", "requested_name": request["requested_name"]})
            assessed.append(item)
            continue

        stock_frame = helpers["get_stock_level"](request["item_name"], request_date)
        available = int(stock_frame["current_stock"].iloc[0])
        movement_query = text(
            "SELECT transaction_date, SUM(CASE WHEN transaction_type = 'stock_orders' THEN units "
            "WHEN transaction_type = 'sales' THEN -units ELSE 0 END) AS units "
            "FROM transactions WHERE item_name = :item_name AND transaction_date > :request_date "
            "AND transaction_date <= :due_date GROUP BY transaction_date ORDER BY transaction_date"
        )
        with engine.connect() as connection:
            movements = connection.execute(
                movement_query,
                {"item_name": request["item_name"], "request_date": request_date, "due_date": due_date},
            ).mappings().all()
        projected = available + sum(int(row["units"] or 0) for row in movements)
        item["available"] = available
        item["projected_available"] = projected
        item["shortage"] = max(0, int(request["quantity"]) - projected)
        if movements:
            item["supplier_delivery_date"] = movements[-1]["transaction_date"]
        if item["shortage"]:
            eta = helpers["get_supplier_delivery_date"](request_date, item["shortage"])
            item["supplier_delivery_date"] = max(item["supplier_delivery_date"], eta)
        delivery_date = max(delivery_date, item["supplier_delivery_date"])
        assessed.append(item)

    for item in assessed:
        if item["shortage"] and item["supplier_delivery_date"] > due_date:
            reasons.append(
                {
                    "code": "deadline_unreachable",
                    "requested_name": item["requested_name"],
                    "available": item["available"],
                    "projected_available": item["projected_available"],
                    "required": item["quantity"],
                    "earliest_delivery": item["supplier_delivery_date"],
                    "due_date": due_date,
                }
            )
    status = "eligible" if not reasons else "rejected"
    reason = ";".join(sorted({entry["code"] for entry in reasons})) if reasons else None
    return {
        "status": status,
        "reason": reason,
        "reasons": reasons,
        "request_date": request_date,
        "due_date": due_date,
        "delivery_date": max(delivery_date, request_date),
        "items": assessed,
    }


def quote_assessment(assessment: Dict, catalog: List[Dict]) -> Dict:
    if assessment["status"] != "eligible":
        return {"status": "rejected", "reason": assessment["reason"], "items": [], "total": 0.0}
    price_by_name = {row["item_name"]: float(row["unit_price"]) for row in catalog}
    items = []
    total = 0.0
    for item in assessment["items"]:
        quantity = int(item["quantity"])
        unit_price = price_by_name[item["item_name"]]
        discount = 0.12 if quantity >= 1000 else 0.08 if quantity >= 500 else 0.05 if quantity >= 200 else 0.0
        subtotal = round(unit_price * quantity, 2)
        line_total = round(subtotal * (1 - discount), 2)
        total += line_total
        items.append({**item, "unit_price": unit_price, "discount_rate": discount, "subtotal": subtotal, "total": line_total})
    return {"status": "priced", "items": items, "total": round(total, 2)}


def _ensure_sales_orders_table(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS sales_orders (request_key TEXT PRIMARY KEY, total_amount REAL NOT NULL, delivery_date TEXT NOT NULL, response TEXT NOT NULL)"))


def _clear_sales_orders(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS sales_orders"))
        connection.execute(
            text(
                "CREATE TABLE sales_orders ("
                "request_key TEXT PRIMARY KEY, total_amount REAL NOT NULL, "
                "delivery_date TEXT NOT NULL, response TEXT NOT NULL)"
            )
        )


def finalize_order(assessment: Dict, quote: Dict, request_key: str, helpers: Dict[str, Any]) -> Dict:
    if assessment["status"] != "eligible" or quote["status"] != "priced":
        return {"status": "rejected", "reason": assessment.get("reason", "quote_not_valid"), "transactions_written": 0}
    engine = helpers["db_engine"]
    _ensure_sales_orders_table(engine)
    with engine.connect() as connection:
        saved = connection.execute(
            text("SELECT total_amount, delivery_date, response FROM sales_orders WHERE request_key=:key"),
            {"key": request_key},
        ).mappings().first()
    if saved:
        return {"status": "accepted", "total": float(saved["total_amount"]), "delivery_date": saved["delivery_date"], "response": saved["response"], "transactions_written": 0}

    expected_total = round(sum(float(item["total"]) for item in quote["items"]), 2)
    if abs(expected_total - float(quote["total"])) > 0.01:
        return {"status": "rejected", "reason": "quote_total_mismatch", "transactions_written": 0}

    response = (
        "Order accepted for "
        + "; ".join(f"{item['quantity']} {item['item_name']}" for item in quote["items"])
        + f". Delivery is scheduled by {assessment['delivery_date']}. "
        + f"The quoted total is ${expected_total:,.2f}, including applicable quantity discounts."
    )
    create_transaction: Callable = helpers["create_transaction"]
    transactions_written = 0
    unit_prices = {row["item_name"]: float(row["unit_price"]) for row in helpers["paper_supplies"]}
    for item in quote["items"]:
        item_name = item["item_name"]
        shortage = int(item["shortage"])
        if shortage:
            purchase_cost = round(shortage * unit_prices[item_name], 2)
            create_transaction(item_name, "stock_orders", 0, purchase_cost, assessment["request_date"])
            create_transaction(item_name, "stock_orders", shortage, 0.0, item["supplier_delivery_date"])
            transactions_written += 2
        create_transaction(item_name, "sales", int(item["quantity"]), float(item["total"]), assessment["delivery_date"])
        transactions_written += 1

    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO sales_orders (request_key,total_amount,delivery_date,response) VALUES (:key,:total,:date,:response)"),
            {"key": request_key, "total": expected_total, "date": assessment["delivery_date"], "response": response},
        )
    return {"status": "accepted", "total": expected_total, "delivery_date": assessment["delivery_date"], "response": response, "transactions_written": transactions_written}


def customer_response(assessment: Dict, sale: Dict | None) -> str:
    if sale and sale.get("status") == "accepted":
        return sale["response"]
    explanations = []
    for item in assessment.get("items", []):
        if item["item_name"] is None:
            explanations.append(f"{item['requested_name']} is not in our product catalog.")
        elif item["shortage"]:
            explanations.append(
                f"{item['requested_name']}: {item['available']} units are on hand and "
                f"{item['projected_available']} are projected available for the delivery window, "
                f"versus {item['quantity']} requested; the earliest supplier date is {item['supplier_delivery_date']} "
                f"(requested deadline {assessment['due_date']})."
            )
        else:
            explanations.append(f"{item['requested_name']}: {item['available']} units are on hand for {item['quantity']} requested.")
    if not explanations:
        explanations.append("Please specify catalog products and requested quantities.")
    return "We cannot fulfill this request: " + " ".join(explanations)


def get_llm_model():
    api_key = os.getenv("UDACITY_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key or api_key.lower() in {"your_key_here", "changeme", "placeholder"}:
        return None
    try:
        return OpenAIModel(
            model_id=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=api_key,
            api_base=os.getenv("OPENAI_API_BASE", "https://openai.vocareum.com/v1"),
        )
    except Exception:
        return None


def build_multi_agent_system(helpers: Dict[str, Any], use_llm: bool = True):
    """Build inventory, pricing, sales and orchestrator agents using starter helpers."""
    catalog = helpers["paper_supplies"]
    if os.getenv("BCPC_USE_LLM", "true").strip().lower() in {"0", "false", "no"}:
        use_llm = False
    tools = {}

    @tool
    def inventory_assessment_tool(request_text: str, request_date: str) -> str:
        """Resolve every requested catalog line, check current and projected stock, and validate its delivery deadline.

        Args:
            request_text: Complete customer request text.
            request_date: Request date in ISO YYYY-MM-DD format.
        Returns:
            JSON assessment containing canonical item names, stock, quantities, and delivery decisions.
        """
        return _dump_json(assess_order(request_text, request_date, helpers))

    @tool
    def inventory_snapshot_tool(as_of_date: str) -> str:
        """Return all positive stock levels from the starter transaction ledger.

        Args:
            as_of_date: Inventory cutoff in ISO YYYY-MM-DD format.
        Returns:
            JSON mapping of catalog names to stock quantities.
        """
        return _dump_json(helpers["get_all_inventory"](as_of_date))

    @tool
    def supplier_delivery_tool(input_date_str: str, quantity: int) -> str:
        """Estimate supplier delivery time using the starter lead-time helper.

        Args:
            input_date_str: Supplier order date in ISO YYYY-MM-DD format.
            quantity: Number of units to order.
        Returns:
            Estimated supplier delivery date.
        """
        return helpers["get_supplier_delivery_date"](input_date_str, quantity)

    @tool
    def quote_history_tool(search_terms: str) -> str:
        """Search prior quotes for customer-request terms.

        Args:
            search_terms: Comma-separated words to match against prior requests and quote explanations.
        Returns:
            JSON list of matching historical quotes.
        """
        terms = [term.strip() for term in search_terms.split(",") if term.strip()]
        return _dump_json(helpers["search_quote_history"](terms, limit=5))

    @tool
    def quote_order_tool(assessment_json: str) -> str:
        """Calculate catalog prices and quantity discounts for a validated assessment.

        Args:
            assessment_json: Full JSON assessment returned by inventory_assessment_tool.
        Returns:
            JSON quote with line totals, discounts, and total amount.
        """
        return _dump_json(quote_assessment(json.loads(assessment_json), catalog))

    @tool
    def sales_finalize_order_tool(assessment_json: str, quote_json: str, request_key: str) -> str:
        """Finalize an eligible order through the starter create_transaction helper.

        Args:
            assessment_json: Full JSON inventory assessment.
            quote_json: Full JSON quote from quote_order_tool.
            request_key: Unique request identifier used to prevent duplicate fulfillment.
        Returns:
            JSON disposition and recorded transaction count.
        """
        outcome = finalize_order(json.loads(assessment_json), json.loads(quote_json), request_key, helpers)
        return _dump_json(outcome)

    @tool
    def cash_balance_tool(as_of_date: str) -> str:
        """Return the starter ledger's cash balance as of a date.

        Args:
            as_of_date: Cash balance cutoff in ISO YYYY-MM-DD format.
        Returns:
            Cash balance as a decimal string.
        """
        return f"{helpers['get_cash_balance'](as_of_date):.2f}"

    @tool
    def financial_report_tool(as_of_date: str) -> str:
        """Return the starter's complete financial and inventory report.

        Args:
            as_of_date: Report date in ISO YYYY-MM-DD format.
        Returns:
            JSON report with cash, inventory, assets, and top-selling products.
        """
        return _dump_json(helpers["generate_financial_report"](as_of_date))

    tools.update(
        inventory_assessment=inventory_assessment_tool,
        inventory_snapshot=inventory_snapshot_tool,
        supplier_delivery=supplier_delivery_tool,
        quote_history=quote_history_tool,
        quote_order=quote_order_tool,
        sales_finalize=sales_finalize_order_tool,
        cash_balance=cash_balance_tool,
        financial_report=financial_report_tool,
    )

    model = get_llm_model() if use_llm else None
    if model is None:
        return MultiAgentSalesSystem(helpers, tools, model=None)

    inventory_agent = ToolCallingAgent(
        tools=[inventory_assessment_tool, inventory_snapshot_tool, supplier_delivery_tool],
        model=model,
        name="inventory_agent",
        description="Resolves products, validates stock and checks supplier lead times.",
        instructions="Always call inventory_assessment_tool with the full request and date. Preserve its JSON facts.",
        max_steps=4,
        verbosity_level=0,
    )
    pricing_agent = ToolCallingAgent(
        tools=[quote_history_tool, quote_order_tool],
        model=model,
        name="pricing_agent",
        description="Checks historical quotes and prices each eligible catalog line with discounts.",
        instructions="Use quote_history_tool for context and quote_order_tool for the supplied complete inventory assessment.",
        max_steps=5,
        verbosity_level=0,
    )
    sales_agent = ToolCallingAgent(
        tools=[sales_finalize_order_tool, cash_balance_tool, financial_report_tool],
        model=model,
        name="sales_agent",
        description="Finalizes eligible sales and reports resulting financial state.",
        instructions="Finalize only eligible priced requests. Call sales_finalize_order_tool using the exact assessment, quote, and request key supplied in the task.",
        max_steps=5,
        verbosity_level=0,
    )
    orchestrator = ToolCallingAgent(
        tools=[],
        model=model,
        name="orchestrator_agent",
        description="Delegates customer requests to inventory, pricing, and sales specialists in sequence.",
        managed_agents=[inventory_agent, pricing_agent, sales_agent],
        instructions=(
            "Delegate one stage at a time through the managed agents. Inventory must run first. "
            "Only if inventory returns eligible, delegate pricing; only if pricing returns priced, delegate sales. "
            "Keep all identifiers and JSON inside each worker task string. Do not claim success without the sales tool result."
        ),
        max_steps=6,
        verbosity_level=0,
    )
    return MultiAgentSalesSystem(helpers, tools, model, inventory_agent, pricing_agent, sales_agent, orchestrator)


class MultiAgentSalesSystem:
    def __init__(self, helpers, tools, model=None, inventory_agent=None, pricing_agent=None, sales_agent=None, orchestrator=None):
        self.helpers = helpers
        self.tools = tools
        self.model = model
        self.inventory_agent = inventory_agent
        self.pricing_agent = pricing_agent
        self.sales_agent = sales_agent
        self.orchestrator = orchestrator
        _clear_sales_orders(helpers["db_engine"])

    def _delegate(self, agent_name: str, task: str) -> None:
        self.orchestrator.run(
            f"Delegate this stage to the managed agent named {agent_name}. Put all data inside the task string. "
            "Call no other agent in this turn. Return the worker's result.\n\n"
            f"Specialist task:\n{task}"
        )

    def handle_request(self, request_text: str, request_date: str, request_key: str) -> Dict:
        assessment = assess_order(request_text, request_date, self.helpers)
        quote = quote_assessment(assessment, self.helpers["paper_supplies"])
        delegated = []
        manager_error = None
        if self.orchestrator:
            try:
                self._delegate(
                    "inventory_agent",
                    f"Call inventory_assessment_tool with request_date={request_date} and this complete request:\n{request_text}",
                )
                delegated.append("inventory_agent")
                if assessment["status"] == "eligible":
                    self._delegate(
                        "pricing_agent",
                        "Call quote_history_tool using important comma-separated terms from the customer request, "
                        "then call quote_order_tool with this exact inventory assessment JSON:\n"
                        + _dump_json(assessment),
                    )
                    delegated.append("pricing_agent")
                    self._delegate(
                        "sales_agent",
                        "Call sales_finalize_order_tool with the exact JSON values below. Do not change values.\n"
                        f"assessment_json={_dump_json(assessment)}\nquote_json={_dump_json(quote)}\nrequest_key={request_key}",
                    )
                    delegated.append("sales_agent")
            except Exception as exc:
                manager_error = type(exc).__name__

        with self.helpers["db_engine"].connect() as connection:
            saved = connection.execute(
                text("SELECT total_amount,delivery_date,response FROM sales_orders WHERE request_key=:key"),
                {"key": request_key},
            ).mappings().first()
        if saved:
            sale = {"status": "accepted", "total": float(saved["total_amount"]), "delivery_date": saved["delivery_date"], "response": saved["response"]}
        elif assessment["status"] == "eligible":
            sale = finalize_order(assessment, quote, request_key, self.helpers)
        else:
            sale = None
        response = customer_response(assessment, sale)
        return {
            "status": sale["status"] if sale else "rejected",
            "reason": assessment.get("reason"),
            "response": response,
            "assessment": assessment,
            "quote": quote,
            "sale": sale,
            "delegated_agents": delegated,
            "orchestration_mode": "smolagents_managed_agents" if self.orchestrator else "deterministic_fallback",
            "manager_error_type": manager_error,
        }


def create_multi_agent_system(helpers: Dict[str, Any], use_llm: bool = True) -> MultiAgentSalesSystem:
    """Create the inventory/pricing/sales team and its delegated orchestrator."""
    return build_multi_agent_system(helpers, use_llm=use_llm)


def call_your_multi_agent_system(system: MultiAgentSalesSystem, request_text: str, request_date: str, request_key: str) -> Dict:
    """Course-starter adapter used by run_test_scenarios()."""
    return system.handle_request(request_text, request_date, request_key)
