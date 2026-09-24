import json
import os
from typing import List

from dotenv import load_dotenv
from smolagents import OpenAIModel, ToolCallingAgent, tool

from .database import create_transaction, generate_financial_report, get_cash_balance, get_stock_level
from .pricing import ITEM_NAME_ALIASES, calculate_quote, normalize_text, parse_requested_items

load_dotenv()


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


def build_rule_response(request_text: str, request_date: str) -> str:
    request_items = parse_requested_items(request_text)
    if not request_items:
        return (
            "Unable to fulfill this request because the item names in the message do not match the company's catalog. "
            "Please provide the exact paper items and quantities to continue."
        )

    due_date = None
    due_date_pattern = __import__("re").search(
        r"(?:deliver(?:ed|y)?(?:\s+by)?|need(?:s)?(?:\s+these)?\s+supplies\s+by|by)\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})",
        request_text,
        flags=__import__("re").IGNORECASE,
    )
    if due_date_pattern:
        date_text = due_date_pattern.group(1)
        for fmt in ("%B %d, %Y", "%b %d, %Y"):
            try:
                import datetime

                due_date = datetime.datetime.strptime(date_text.strip(), fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue
    if due_date is None:
        import datetime

        due_date = (datetime.datetime.fromisoformat(request_date) + __import__("datetime").timedelta(days=7)).strftime("%Y-%m-%d")

    total_required_qty = sum(int(item["quantity"]) for item in request_items)
    shortage_items = []
    order_total = 0.0
    for item in request_items:
        item_name = str(item["item_name"])
        quantity = int(item["quantity"])
        availability = check_item_stock(item_name, quantity, request_date)
        if not availability["sufficient"]:
            shortage = quantity - int(availability["available"])
            shortage_items.append(
                {
                    "item_name": item_name,
                    "required": quantity,
                    "available": int(availability["available"]),
                    "shortage": shortage,
                }
            )
        quote = calculate_quote(item_name, quantity)
        order_total += quote["total"]

    if shortage_items:
        feasible = True
        for item in shortage_items:
            if item["shortage"] > 0:
                candidate_date = __import__("datetime").datetime.fromisoformat(request_date)
                supplier_eta = __import__("datetime").timedelta(days=4 if item["shortage"] <= 1000 else 7)
                if (candidate_date + supplier_eta).strftime("%Y-%m-%d") > due_date:
                    feasible = False
                    reject_name = item["item_name"]
                    reject_available = item["available"]
                    reject_required = item["required"]
                    return (
                        f"Request cannot be fulfilled on {request_date} because {reject_name} is below the required quantity. "
                        f"Available stock: {reject_available} units; requested: {reject_required} units. "
                        f"The order is rejected until inventory is replenished or an alternative item is approved."
                    )
        if feasible:
            request_summary = "; ".join(f"{item['item_name']} x{int(item['quantity'])}" for item in request_items)
            response = (
                f"Order accepted for {request_date}. The requested mix ({request_summary}) was placed on a restock plan to meet the deadline. "
                f"Estimated total value: ${order_total:,.2f}. The quote reflects the applied quantity discount and supplier readiness. "
                f"Delivery target is {due_date}."
            )
            for item in request_items:
                item_name = str(item["item_name"])
                quantity = int(item["quantity"])
                availability = check_item_stock(item_name, quantity, request_date)
                shortage = max(0, quantity - int(availability["available"]))
                if shortage > 0:
                    from .database import paper_supplies as catalog

                    unit_price = next((entry["unit_price"] for entry in catalog if entry["item_name"] == item_name), 0)
                    create_transaction(
                        item_name=item_name,
                        transaction_type="stock_orders",
                        quantity=shortage,
                        price=shortage * float(unit_price),
                        date=request_date,
                    )
                quote = calculate_quote(item_name, quantity)
                create_transaction(
                    item_name=item_name,
                    transaction_type="sales",
                    quantity=quantity,
                    price=quote["total"],
                    date=request_date,
                )
            return response

    request_summary = "; ".join(f"{item['item_name']} x{int(item['quantity'])}" for item in request_items)
    response = (
        f"Order accepted for {request_date}. The requested mix ({request_summary}) is available in stock and matches catalog products. "
        f"Estimated total value: ${order_total:,.2f}. The quote reflects the applied quantity discount and inventory readiness. "
        f"Delivery is estimated for {__import__('datetime').datetime.fromisoformat(request_date) + __import__('datetime').timedelta(days=4)}."
    )
    for item in request_items:
        item_name = str(item["item_name"])
        quantity = int(item["quantity"])
        quote = calculate_quote(item_name, quantity)
        create_transaction(item_name=item_name, transaction_type="sales", quantity=quantity, price=quote["total"], date=request_date)
    return response


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
def sales_finalize_tool(item_name: str, quantity: int, quote_total: float, request_date: str) -> str:
    """Finalize a sale when stock, price and delivery conditions are valid.

    Args:
        item_name (str): The item to be sold.
        quantity (int): Requested number of units.
        quote_total (float): Final price for the order.
        request_date (str): Sale date.
    Returns:
        str: A JSON string describing the disposition of the sale.
    """
    stock = check_item_stock(item_name, quantity, request_date)
    if not stock["sufficient"]:
        return json.dumps({"status": "rejected", "reason": "insufficient_stock", "available": stock["available"], "required": quantity})
    create_transaction(item_name=item_name, transaction_type="sales", quantity=quantity, price=float(quote_total), date=request_date)
    return json.dumps({"status": "accepted", "item_name": item_name, "quantity": quantity, "total": float(quote_total)})


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


def build_multi_agent_system():
    model = get_llm_model()
    if model is None:
        return {}
    inventory_agent = ToolCallingAgent(
        tools=[inventory_check_tool, inventory_snapshot_tool, supplier_delivery_tool],
        model=model,
        name="inventory_agent",
        description="Checks inventory and supplier lead times before authorizing a sale.",
    )
    quote_agent = ToolCallingAgent(
        tools=[quote_history_tool, quote_price_tool, cash_balance_tool],
        model=model,
        name="pricing_agent",
        description="Looks up historical pricing and computes a quote with discounts.",
    )
    sales_agent = ToolCallingAgent(
        tools=[sales_finalize_tool, financial_report_tool],
        model=model,
        name="sales_agent",
        description="Finalizes accepted orders and updates financial state.",
    )
    orchestrator = ToolCallingAgent(
        tools=[inventory_check_tool, inventory_snapshot_tool, quote_history_tool, quote_price_tool, sales_finalize_tool, financial_report_tool],
        model=model,
        name="orchestrator_agent",
        description="Coordinates inventory checks, quote generation, and sales finalization for customer requests.",
    )
    return {"inventory_agent": inventory_agent, "pricing_agent": quote_agent, "sales_agent": sales_agent, "orchestrator": orchestrator}


def run_multi_agent_system(request_text: str, request_date: str) -> str:
    agents = build_multi_agent_system()
    if not agents:
        return build_rule_response(request_text, request_date)
    orchestrator = agents["orchestrator"]
    try:
        system_prompt = (
            "You are the orchestrator for Beaver's Choice Paper Company. "
            "First verify inventory for each product; if insufficient, reject with a reason. "
            "Then calculate a quote using the pricing logic. "
            "Finally finalize the sale only when stock is sufficient and the order can meet the delivery requirement. "
            "Return a brief customer-facing response with rationale."
        )
        result = orchestrator.run(f"{system_prompt}\nCustomer request: {request_text}\nRequest date: {request_date}")
        if isinstance(result, str):
            return result
        return str(result)
    except Exception:
        return build_rule_response(request_text, request_date)
