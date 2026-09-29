import json
import os
from typing import List
import re
from datetime import datetime, timedelta
from typing import Dict, List
from dotenv import load_dotenv
from smolagents import OpenAIModel, ToolCallingAgent, tool

from .database import create_transaction, generate_financial_report, get_cash_balance, get_stock_level
from sqlalchemy import text
from .pricing import ITEM_NAME_ALIASES, calculate_quote, normalize_text, parse_requested_items
from .database import (
    create_transaction,
    db_engine,
    generate_financial_report,
    get_cash_balance,
    get_stock_level,
    get_supplier_delivery_date,
    paper_supplies,
)
from .pricing import calculate_quote, parse_requested_items


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


def check_item_stock(item_name: str, quantity: int, as_of_date: str):
    stock_df = get_stock_level(item_name, as_of_date)
    available = int(stock_df["current_stock"].iloc[0]) if not stock_df.empty else 0
    return {"item_name": item_name, "available": available, "required": quantity, "sufficient": available >= quantity}


def assess_order(request_text: str, request_date: str) -> Dict:
    request_items = parse_requested_items(request_text)
    due_match = re.search(
        r"\bby\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})",
        request_text,
        flags=re.IGNORECASE,
    )
    if due_match:
        try:
            due_date = datetime.strptime(due_match.group(1).strip(), "%B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            due_date = (datetime.fromisoformat(request_date) + timedelta(days=7)).strftime("%Y-%m-%d")
    else:
        due_date = (datetime.fromisoformat(request_date) + timedelta(days=7)).strftime("%Y-%m-%d")

    if not request_items:
        return {
            "status": "rejected",
            "reason": "no_products_detected",
            "request_date": request_date,
            "due_date": due_date,
            "items": [],
        }

    catalog_names = {item["item_name"] for item in paper_supplies}
    assessed_items = []
    reasons = []
    latest_delivery = request_date
    for item in request_items:
        item_name = item["item_name"]
        assessed = {
            **item,
            "available": 0,
            "shortage": 0,
            "supplier_delivery_date": request_date,
        }
        if item_name is None or item_name not in catalog_names:
            reasons.append({"code": "not_in_catalog", "requested_name": item["requested_name"]})
            assessed_items.append(assessed)
            continue

        stock = check_item_stock(item_name, int(item["quantity"]), request_date)
        assessed["available"] = stock["available"]
        with db_engine.connect() as connection:
            future_movements = connection.execute(
                text(
                    "SELECT transaction_date, SUM(CASE "
                    "WHEN transaction_type = 'stock_orders' THEN units "
                    "WHEN transaction_type = 'sales' THEN -units ELSE 0 END) AS units "
                    "FROM transactions WHERE item_name = :item_name "
                    "AND transaction_date > :request_date AND transaction_date <= :due_date "
                    "GROUP BY transaction_date ORDER BY transaction_date"
                ),
                {
                    "item_name": item_name,
                    "request_date": request_date,
                    "due_date": due_date,
                },
            ).mappings().all()
        projected_stock = stock["available"] + sum(int(movement["units"] or 0) for movement in future_movements)
        assessed["projected_available"] = projected_stock
        assessed["shortage"] = max(0, stock["required"] - projected_stock)
        if future_movements:
            assessed["supplier_delivery_date"] = future_movements[-1]["transaction_date"]
        if assessed["shortage"]:
            supplier_date = get_supplier_delivery_date(request_date, assessed["shortage"])
            assessed["supplier_delivery_date"] = max(assessed["supplier_delivery_date"], supplier_date)
        latest_delivery = max(latest_delivery, assessed["supplier_delivery_date"])
        assessed_items.append(assessed)

    for item in assessed_items:
        if item["shortage"] and item["supplier_delivery_date"] > due_date:
            reasons.append(
                {
                    "code": "deadline_unreachable",
                    "item_name": item["item_name"],
                    "requested_name": item["requested_name"],
                    "available": item["available"],
                    "required": item["quantity"],
                    "earliest_delivery": item["supplier_delivery_date"],
                    "due_date": due_date,
                }
            )

    status = "eligible" if not reasons else "rejected"
    return {
        "status": status,
        "reason": None if status == "eligible" else ";".join(sorted({reason["code"] for reason in reasons})),
        "reasons": reasons,
        "request_date": request_date,
        "due_date": due_date,
        "delivery_date": max(latest_delivery, request_date),
        "items": assessed_items,
    }


def quote_assessment(assessment: Dict) -> Dict:
    if assessment["status"] != "eligible":
        return {"status": "rejected", "reason": assessment["reason"], "items": [], "total": 0.0}
    quoted_items = []
    total = 0.0
    for item in assessment["items"]:
        quote = calculate_quote(item["item_name"], int(item["quantity"]))
        total += quote["total"]
        quoted_items.append({**item, "quote": quote})
    return {"status": "priced", "items": quoted_items, "total": round(total, 2)}


def finalize_order(assessment: Dict, quote: Dict, request_key: str) -> Dict:
    if assessment["status"] != "eligible" or quote["status"] != "priced":
        return {"status": "rejected", "reason": assessment.get("reason", "quote_not_valid"), "transactions_written": 0}

    with db_engine.connect() as connection:
        existing = connection.execute(
            text("SELECT status, total_amount, delivery_date, response FROM sales_orders WHERE request_key = :key"),
            {"key": request_key},
        ).mappings().first()
    if existing:
        return {
            "status": existing["status"],
            "total": float(existing["total_amount"]),
            "delivery_date": existing["delivery_date"],
            "response": existing["response"],
            "transactions_written": 0,
            "idempotent_replay": True,
        }

    expected_total = round(sum(item["quote"]["total"] for item in quote["items"]), 2)
    if abs(expected_total - float(quote["total"])) > 0.01:
        return {"status": "rejected", "reason": "quote_total_mismatch", "transactions_written": 0}

    delivery_date = assessment["delivery_date"]
    response = (
        f"Order accepted. The requested catalog items can be delivered by {delivery_date}. "
        f"The quoted total is ${expected_total:,.2f}, including applicable quantity discounts."
    )
    transaction_rows = []
    for item in quote["items"]:
        item_name = item["item_name"]
        quantity = int(item["quantity"])
        shortage = int(item["shortage"])
        unit_price = next(product["unit_price"] for product in paper_supplies if product["item_name"] == item_name)
        if shortage:
            transaction_rows.append(
                {
                    "item_name": item_name,
                    "transaction_type": "stock_orders",
                    "units": 0,
                    "price": round(shortage * float(unit_price), 2),
                    "transaction_date": assessment["request_date"],
                    "request_key": request_key,
                }
            )
            transaction_rows.append(
                {
                    "item_name": item_name,
                    "transaction_type": "stock_orders",
                    "units": shortage,
                    "price": 0.0,
                    "transaction_date": item["supplier_delivery_date"],
                    "request_key": request_key,
                }
            )
        transaction_rows.append(
            {
                "item_name": item_name,
                "transaction_type": "sales",
                "units": quantity,
                "price": float(item["quote"]["total"]),
                "transaction_date": delivery_date,
                "request_key": request_key,
            }
        )

    with db_engine.begin() as connection:
        for row in transaction_rows:
            connection.execute(
                text(
                    "INSERT INTO transactions "
                    "(item_name, transaction_type, units, price, transaction_date, request_key) "
                    "VALUES (:item_name, :transaction_type, :units, :price, :transaction_date, :request_key)"
                ),
                row,
            )
        connection.execute(
            text(
                "INSERT INTO sales_orders (request_key, status, total_amount, delivery_date, response) "
                "VALUES (:request_key, 'accepted', :total, :delivery_date, :response)"
            ),
            {
                "request_key": request_key,
                "total": expected_total,
                "delivery_date": delivery_date,
                "response": response,
            },
        )
    return {
        "status": "accepted",
        "total": expected_total,
        "delivery_date": delivery_date,
        "response": response,
        "transactions_written": len(transaction_rows),
        "idempotent_replay": False,
    }


def customer_response(assessment: Dict, quote: Dict, sale: Dict | None = None) -> str:
    if assessment["status"] == "eligible" and sale and sale["status"] == "accepted":
        item_summary = "; ".join(
            f"{item['quantity']} {item['item_name']}" for item in assessment["items"]
        )
        return (
            f"Order accepted for {item_summary}. Delivery is scheduled by {sale['delivery_date']}. "
            f"The quoted total is ${sale['total']:,.2f}, including applicable quantity discounts."
        )

    explanations = []
    for item in assessment.get("items", []):
        requested_name = item["requested_name"]
        if item["item_name"] is None:
            explanations.append(f"{requested_name} is not in our product catalog.")
            continue

        quantity = int(item["quantity"])
        available_now = int(item["available"])
        projected = int(item.get("projected_available", available_now))
        shortage = int(item["shortage"])
        if shortage:
            if item["supplier_delivery_date"] > assessment["due_date"]:
                explanations.append(
                    f"{requested_name}: {available_now} are currently on hand and {projected} are projected "
                    f"to remain available for this delivery window, versus {quantity} requested; "
                    f"replenishment is estimated for {item['supplier_delivery_date']}, after the requested deadline "
                    f"of {assessment['due_date']}."
                )
            else:
                explanations.append(
                    f"{requested_name}: {available_now} are currently on hand and {projected} are projected "
                    f"to remain available for this delivery window, versus {quantity} requested; "
                    f"the estimated replenishment date is {item['supplier_delivery_date']}."
                )
        else:
            explanations.append(
                f"{requested_name}: {available_now} are currently on hand for {quantity} requested."
            )

    if not explanations:
        explanations.append("The requested products or quantities could not be identified; please clarify the items and amounts.")
    return "We cannot fulfill this request: " + " ".join(explanations)


def process_rule_order(request_text: str, request_date: str, request_key: str) -> Dict:
    assessment = assess_order(request_text, request_date)
    quote = quote_assessment(assessment)
    sale = finalize_order(assessment, quote, request_key) if assessment["status"] == "eligible" else None
    return {
        "status": sale["status"] if sale else "rejected",
        "response": customer_response(assessment, quote, sale),
        "assessment": assessment,
        "quote": quote,
        "sale": sale,
    }


def build_rule_response(request_text: str, request_date: str, request_key: str = "rule-request") -> str:
    return process_rule_order(request_text, request_date, request_key)["response"]


@tool
def inventory_check_tool(item_name: str, quantity: int, as_of_date: str) -> str:
    """Check stock availability for a requested item.

    Args:
        item_name (str): The exact item name from the catalog to check.
        quantity (int): The number of units requested.
        as_of_date (str): The date at which inventory should be evaluated.
    Returns:
        str: A JSON string summarizing the stock state.
    """
    return json.dumps(check_item_stock(item_name, quantity, as_of_date), ensure_ascii=False)


@tool
def inventory_assessment_tool(request_text: str, request_date: str) -> str:
    """Validate every requested product against the catalog, ledger stock, and requested deadline.

    Args:
        request_text (str): The complete customer request.
        request_date (str): The request date in ISO format.
    Returns:
        str: A JSON inventory assessment with catalog matches, quantities, stock, and supplier dates.
    """
    return json.dumps(assess_order(request_text, request_date), ensure_ascii=False)


@tool
def inventory_snapshot_tool(as_of_date: str) -> str:
    """Return the current inventory snapshot for all items as of a date.

    Args:
        as_of_date (str): The date to use for snapshot evaluation.
    Returns:
        str: A JSON string containing the inventory snapshot.
    """
    from .database import get_all_inventory

    return json.dumps(get_all_inventory(as_of_date), ensure_ascii=False)


@tool
def supplier_delivery_tool(input_date_str: str, quantity: int) -> str:
    """Estimate supplier delivery date from a start date and order size.

    Args:
        input_date_str (str): The starting ISO date.
        quantity (int): Number of units being purchased.
    Returns:
        str: Estimated delivery date.
    """
    from .database import get_supplier_delivery_date

    return get_supplier_delivery_date(input_date_str, quantity)


@tool
def cash_balance_tool(as_of_date: str) -> str:
    """Return the company cash balance as of a given date.

    Args:
        as_of_date (str): The date to evaluate.
    Returns:
        str: A numeric cash balance string.
    """
    return str(get_cash_balance(as_of_date))


@tool
def financial_report_tool(as_of_date: str) -> str:
    """Return the business financial report as of the requested date.

    Args:
        as_of_date (str): The date to evaluate.
    Returns:
        str: A JSON string with financial and inventory totals.
    """
    return json.dumps(generate_financial_report(as_of_date), ensure_ascii=False)


@tool
def quote_history_tool(search_terms: List[str], limit: int = 5) -> str:
    """Search the historical quote database for matching patterns.

    Args:
        search_terms (List[str]): Keywords to search for.
        limit (int, optional): Maximum number of matches to return.
    Returns:
        str: A JSON string containing the quote history.
    """
    from .database import search_quote_history

    return json.dumps(search_quote_history(search_terms, limit=limit), ensure_ascii=False)


@tool
def sales_finalize_order_tool(inventory_report_json: str, quote_json: str, request_key: str) -> str:
    """Commit an eligible and priced order to the transaction ledger exactly once.

    Args:
        inventory_report_json (str): The complete JSON output from inventory_assessment_tool.
        quote_json (str): The complete JSON output from quote_order_tool.
        request_key (str): A stable unique key for this request to prevent duplicate sales.
    Returns:
        str: A JSON order disposition including its delivery date and ledger write count.
    """
    try:
        result = finalize_order(json.loads(inventory_report_json), json.loads(quote_json), request_key)
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        result = {"status": "rejected", "reason": "invalid_order_data", "transactions_written": 0}
    return json.dumps(result, ensure_ascii=False)


@tool
def quote_price_tool(item_name: str, quantity: int) -> str:
    """Compute the price for an item and quantity using the business discount schedule.

    Args:
        item_name (str): Name of the item to price.
        quantity (int): Quantity requested.
    Returns:
        str: A JSON string with the quote details.
    """
    return json.dumps(calculate_quote(item_name, quantity), ensure_ascii=False)


@tool
def quote_order_tool(inventory_report_json: str) -> str:
    """Price every catalog item in an eligible inventory assessment.

    Args:
        inventory_report_json (str): The full JSON output from inventory_assessment_tool.
    Returns:
        str: A JSON quote with per-item discounts and a validated order total.
    """
    try:
        result = quote_assessment(json.loads(inventory_report_json))
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        result = {"status": "rejected", "reason": "invalid_inventory_report", "items": [], "total": 0.0}
    return json.dumps(result, ensure_ascii=False)


def build_multi_agent_system():
    model = get_llm_model()
    if model is None:
        return {}
    inventory_agent = ToolCallingAgent(
        tools=[inventory_assessment_tool, inventory_check_tool, inventory_snapshot_tool, supplier_delivery_tool],
        model=model,
        name="inventory_agent",
        description="Checks inventory and supplier lead times before authorizing a sale.",
        instructions="Use inventory_assessment_tool for each complete customer order. Report its JSON findings without changing quantities or item mappings.",
        max_steps=5,
        verbosity_level=0,
    )
    quote_agent = ToolCallingAgent(
        tools=[quote_order_tool],
        model=model,
        name="pricing_agent",
        description="Looks up historical pricing and computes a quote with discounts.",
        instructions="Use quote_order_tool on the complete inventory assessment JSON. Do not price rejected or unsupported orders.",
        max_steps=5,
        verbosity_level=0,
    )
    sales_agent = ToolCallingAgent(
        tools=[sales_finalize_order_tool, financial_report_tool],
        model=model,
        name="sales_agent",
        description="Finalizes accepted orders and updates financial state.",
        instructions="Finalize only with sales_finalize_order_tool, passing the original assessment, quote, and request key unchanged. Never claim success unless the tool returns accepted.",
        max_steps=5,
        verbosity_level=0,
    )
    orchestrator = ToolCallingAgent(
        tools=[],
        model=model,
        name="orchestrator_agent",
        description="Coordinates inventory checks, quote generation, and sales finalization for customer requests.",
        managed_agents=[inventory_agent, quote_agent, sales_agent],
        instructions=(
            "You manage three specialist agents. For every request, delegate first to inventory_agent and wait for its full JSON assessment. "
            "If and only if its status is eligible, delegate the unchanged assessment to pricing_agent and wait for the quote. "
            "If and only if the quote status is priced, delegate both unchanged JSON results and the supplied request key to sales_agent. "
            "Do not answer from guesses, do not bypass a specialist, and do not claim an order was accepted unless sales_agent confirms it. "
            "If inventory reports an unsupported product or a missed deadline, stop and explain that specific reason."
        ),
        max_steps=12,
        verbosity_level=0,
    )
    return {"inventory_agent": inventory_agent, "pricing_agent": quote_agent, "sales_agent": sales_agent, "orchestrator": orchestrator}


def _delegated_agents(orchestrator) -> List[str]:
    delegated = set()
    for step in getattr(getattr(orchestrator, "memory", None), "steps", []):
        for call in getattr(step, "tool_calls", []) or []:
            name = getattr(call, "name", None)
            if name is None and isinstance(call, dict):
                name = call.get("name")
            if name in {"inventory_agent", "pricing_agent", "sales_agent"}:
                delegated.add(name)
    return sorted(delegated)


def _successful_agent_tools(agent) -> List[str]:
    successful = set()
    for step in getattr(getattr(agent, "memory", None), "steps", []):
        if getattr(step, "error", None) is not None:
            continue
        for call in getattr(step, "tool_calls", []) or []:
            name = getattr(call, "name", None)
            if name:
                successful.add(name)
    return sorted(successful)


def _saved_order(request_key: str) -> Dict | None:
    with db_engine.connect() as connection:
        order = connection.execute(
            text("SELECT status, total_amount, delivery_date, response FROM sales_orders WHERE request_key = :key"),
            {"key": request_key},
        ).mappings().first()
    if not order:
        return None
    return {
        "status": order["status"],
        "total": float(order["total_amount"]),
        "delivery_date": order["delivery_date"],
        "response": order["response"],
        "transactions_written": 0,
        "idempotent_replay": True,
    }


def run_multi_agent_system(request_text: str, request_date: str, request_key: str = "sample-request") -> Dict:
    assessment = assess_order(request_text, request_date)
    quote = quote_assessment(assessment)
    agents = build_multi_agent_system()
    orchestration_mode = "rule_fallback"
    delegated_agents: List[str] = []
    worker_tool_calls: Dict[str, List[str]] = {}
    expected_agents = ["inventory_agent"]
    if assessment["status"] == "eligible":
        expected_agents.extend(["pricing_agent", "sales_agent"])
    manager_error = None
    try:
        if agents:
            orchestrator = agents["orchestrator"]
            inventory_task = (
                "Call inventory_assessment_tool exactly once with the following complete customer request and request date. "
                "Return the full tool JSON unchanged.\n"
                f"Request date: {request_date}\nCustomer request: {request_text}"
            )
            pricing_task = (
                "Call quote_order_tool exactly once with this complete inventory assessment JSON and return the full tool JSON unchanged:\n"
                f"{json.dumps(assessment, ensure_ascii=False)}"
            )
            sales_task = (
                "Call sales_finalize_order_tool exactly once using these exact values. Do not modify either JSON string. "
                "Return the full tool JSON unchanged.\n"
                f"Inventory assessment JSON: {json.dumps(assessment, ensure_ascii=False)}\n"
                f"Quote JSON: {json.dumps(quote, ensure_ascii=False)}\n"
                f"Request key: {request_key}"
            )
            delegation_tasks = [("inventory_agent", inventory_task)]
            if assessment["status"] == "eligible":
                delegation_tasks.extend(
                    [
                        ("pricing_agent", pricing_task),
                        ("sales_agent", sales_task),
                    ]
                )
            delegated_seen = set()
            for agent_name, worker_task in delegation_tasks:
                orchestrator.run(
                    f"Delegate this stage exactly once to the managed agent named {agent_name}. "
                    "Managed agents accept only a task string and optional additional_args. Put request keys and business data inside the task text; "
                    "never pass them as separate managed-agent arguments. "
                    "Call no other agent in this turn. Wait for that agent and return its result without replacing it with your own decision.\n"
                    f"Request key: {request_key}\nRequest date: {request_date}\n"
                    f"Original customer request:\n{request_text}\n\nSpecialist task:\n{worker_task}"
                )
                delegated_seen.update(_delegated_agents(orchestrator))
                worker_tool_calls[agent_name] = _successful_agent_tools(agents[agent_name])
            delegated_agents = sorted(delegated_seen)
            orchestration_mode = "smolagents_managed_agents"
    except Exception as exc:
        manager_error = type(exc).__name__

    sale = _saved_order(request_key)
    if assessment["status"] == "eligible" and sale is None:
        sale = finalize_order(assessment, quote, request_key)
    response = customer_response(assessment, quote, sale)
    status = sale["status"] if sale else "rejected"
    required_tool_by_agent = {
        "inventory_agent": "inventory_assessment_tool",
        "pricing_agent": "quote_order_tool",
        "sales_agent": "sales_finalize_order_tool",
    }
    successful_stages = {
        agent_name
        for agent_name in expected_agents
        if required_tool_by_agent[agent_name] in worker_tool_calls.get(agent_name, [])
    }
    return {
        "status": status,
        "response": response,
        "reason": assessment.get("reason"),
        "assessment": assessment,
        "quote": quote,
        "sale": sale,
        "orchestration_mode": orchestration_mode,
        "delegated_agents": delegated_agents,
        "worker_tool_calls": worker_tool_calls,
        "delegation_complete": (
            set(expected_agents).issubset(delegated_agents)
            and set(expected_agents).issubset(successful_stages)
        ) if agents and manager_error is None else False,
        "manager_error_type": manager_error,
    }
