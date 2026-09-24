import ast
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Union

import numpy as np
import pandas as pd
from sqlalchemy import Engine, create_engine
from sqlalchemy.sql import text

ROOT_DIR = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT_DIR / "input_output" / "inputs"
OUTPUT_DIR = ROOT_DIR / "input_output" / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Create an SQLite database
DB_PATH = ROOT_DIR / "munder_difflin.db"
db_engine = create_engine(f"sqlite:///{DB_PATH}")

paper_supplies = [
    {"item_name": "A4 paper", "category": "paper", "unit_price": 0.05},
    {"item_name": "Letter-sized paper", "category": "paper", "unit_price": 0.06},
    {"item_name": "Cardstock", "category": "paper", "unit_price": 0.15},
    {"item_name": "Colored paper", "category": "paper", "unit_price": 0.10},
    {"item_name": "Glossy paper", "category": "paper", "unit_price": 0.20},
    {"item_name": "Matte paper", "category": "paper", "unit_price": 0.18},
    {"item_name": "Recycled paper", "category": "paper", "unit_price": 0.08},
    {"item_name": "Eco-friendly paper", "category": "paper", "unit_price": 0.12},
    {"item_name": "Poster paper", "category": "paper", "unit_price": 0.25},
    {"item_name": "Banner paper", "category": "paper", "unit_price": 0.30},
    {"item_name": "Kraft paper", "category": "paper", "unit_price": 0.10},
    {"item_name": "Construction paper", "category": "paper", "unit_price": 0.07},
    {"item_name": "Wrapping paper", "category": "paper", "unit_price": 0.15},
    {"item_name": "Glitter paper", "category": "paper", "unit_price": 0.22},
    {"item_name": "Decorative paper", "category": "paper", "unit_price": 0.18},
    {"item_name": "Letterhead paper", "category": "paper", "unit_price": 0.12},
    {"item_name": "Legal-size paper", "category": "paper", "unit_price": 0.08},
    {"item_name": "Crepe paper", "category": "paper", "unit_price": 0.05},
    {"item_name": "Photo paper", "category": "paper", "unit_price": 0.25},
    {"item_name": "Uncoated paper", "category": "paper", "unit_price": 0.06},
    {"item_name": "Butcher paper", "category": "paper", "unit_price": 0.10},
    {"item_name": "Heavyweight paper", "category": "paper", "unit_price": 0.20},
    {"item_name": "Standard copy paper", "category": "paper", "unit_price": 0.04},
    {"item_name": "Bright-colored paper", "category": "paper", "unit_price": 0.12},
    {"item_name": "Patterned paper", "category": "paper", "unit_price": 0.15},
    {"item_name": "Paper plates", "category": "product", "unit_price": 0.10},
    {"item_name": "Paper cups", "category": "product", "unit_price": 0.08},
    {"item_name": "Paper napkins", "category": "product", "unit_price": 0.02},
    {"item_name": "Disposable cups", "category": "product", "unit_price": 0.10},
    {"item_name": "Table covers", "category": "product", "unit_price": 1.50},
    {"item_name": "Envelopes", "category": "product", "unit_price": 0.05},
    {"item_name": "Sticky notes", "category": "product", "unit_price": 0.03},
    {"item_name": "Notepads", "category": "product", "unit_price": 2.00},
    {"item_name": "Invitation cards", "category": "product", "unit_price": 0.50},
    {"item_name": "Flyers", "category": "product", "unit_price": 0.15},
    {"item_name": "Party streamers", "category": "product", "unit_price": 0.05},
    {"item_name": "Decorative adhesive tape (washi tape)", "category": "product", "unit_price": 0.20},
    {"item_name": "Paper party bags", "category": "product", "unit_price": 0.25},
    {"item_name": "Name tags with lanyards", "category": "product", "unit_price": 0.75},
    {"item_name": "Presentation folders", "category": "product", "unit_price": 0.50},
    {"item_name": "Large poster paper (24x36 inches)", "category": "large_format", "unit_price": 1.00},
    {"item_name": "Rolls of banner paper (36-inch width)", "category": "large_format", "unit_price": 2.50},
    {"item_name": "100 lb cover stock", "category": "specialty", "unit_price": 0.50},
    {"item_name": "80 lb text paper", "category": "specialty", "unit_price": 0.40},
    {"item_name": "250 gsm cardstock", "category": "specialty", "unit_price": 0.30},
    {"item_name": "220 gsm poster paper", "category": "specialty", "unit_price": 0.35},
]


def generate_sample_inventory(paper_supplies_list: list, coverage: float = 0.4, seed: int = 137) -> pd.DataFrame:
    np.random.seed(seed)
    num_items = int(len(paper_supplies_list) * coverage)
    selected_indices = np.random.choice(range(len(paper_supplies_list)), size=num_items, replace=False)
    selected_items = [paper_supplies_list[i] for i in selected_indices]
    inventory = []
    for item in selected_items:
        inventory.append(
            {
                "item_name": item["item_name"],
                "category": item["category"],
                "unit_price": item["unit_price"],
                "current_stock": np.random.randint(200, 800),
                "min_stock_level": np.random.randint(50, 150),
            }
        )
    return pd.DataFrame(inventory)


def init_database(db_engine_instance: Engine, seed: int = 137) -> Engine:
    try:
        transactions_schema = pd.DataFrame(
            {
                "id": [],
                "item_name": [],
                "transaction_type": [],
                "units": [],
                "price": [],
                "transaction_date": [],
            }
        )
        transactions_schema.to_sql("transactions", db_engine_instance, if_exists="replace", index=False)

        initial_date = datetime(2025, 1, 1).isoformat()

        quote_requests_df = pd.read_csv(INPUT_DIR / "quote_requests.csv")
        quote_requests_df["id"] = range(1, len(quote_requests_df) + 1)
        quote_requests_df.to_sql("quote_requests", db_engine_instance, if_exists="replace", index=False)

        quotes_df = pd.read_csv(INPUT_DIR / "quotes.csv")
        quotes_df["request_id"] = range(1, len(quotes_df) + 1)
        quotes_df["order_date"] = initial_date
        if "request_metadata" in quotes_df.columns:
            request_metadata = quotes_df["request_metadata"].apply(
                lambda x: ast.literal_eval(x) if isinstance(x, str) else x
            )
            quotes_df = quotes_df.assign(
                request_metadata=request_metadata,
                job_type=request_metadata.apply(
                    lambda x: x.get("job_type", "") if isinstance(x, dict) else ""
                ),
                order_size=request_metadata.apply(
                    lambda x: x.get("order_size", "") if isinstance(x, dict) else ""
                ),
                event_type=request_metadata.apply(
                    lambda x: x.get("event_type", "") if isinstance(x, dict) else ""
                ),
            )

        quotes_df = quotes_df[["request_id", "total_amount", "quote_explanation", "order_date", "job_type", "order_size", "event_type"]]
        quotes_df.to_sql("quotes", db_engine_instance, if_exists="replace", index=False)

        inventory_df = generate_sample_inventory(paper_supplies, seed=seed)
        initial_transactions = [{
            "item_name": None,
            "transaction_type": "sales",
            "units": None,
            "price": 50000.0,
            "transaction_date": initial_date,
        }]
        for _, item in inventory_df.iterrows():
            initial_transactions.append(
                {
                    "item_name": item["item_name"],
                    "transaction_type": "stock_orders",
                    "units": item["current_stock"],
                    "price": item["current_stock"] * item["unit_price"],
                    "transaction_date": initial_date,
                }
            )
        pd.DataFrame(initial_transactions).to_sql("transactions", db_engine_instance, if_exists="append", index=False)
        inventory_df.to_sql("inventory", db_engine_instance, if_exists="replace", index=False)
        return db_engine_instance
    except Exception as exc:  # pragma: no cover - diagnostic path
        print(f"Error initializing database: {exc}")
        raise


def create_transaction(item_name: str, transaction_type: str, quantity: int, price: float, date: Union[str, datetime]) -> int:
    try:
        date_str = date.isoformat() if isinstance(date, datetime) else date
        if transaction_type not in {"stock_orders", "sales"}:
            raise ValueError("Transaction type must be 'stock_orders' or 'sales'")
        transaction = pd.DataFrame([
            {
                "item_name": item_name,
                "transaction_type": transaction_type,
                "units": quantity,
                "price": price,
                "transaction_date": date_str,
            }
        ])
        transaction.to_sql("transactions", db_engine, if_exists="append", index=False)
        result = pd.read_sql("SELECT last_insert_rowid() as id", db_engine)
        return int(result.iloc[0]["id"])
    except Exception as exc:  # pragma: no cover - diagnostic path
        print(f"Error creating transaction: {exc}")
        raise


def get_all_inventory(as_of_date: str) -> Dict[str, int]:
    query = """
        SELECT item_name,
               SUM(CASE
                   WHEN transaction_type = 'stock_orders' THEN units
                   WHEN transaction_type = 'sales' THEN -units
                   ELSE 0
               END) AS stock
        FROM transactions
        WHERE item_name IS NOT NULL
          AND transaction_date <= :as_of_date
        GROUP BY item_name
        HAVING stock > 0
    """
    result = pd.read_sql(query, db_engine, params={"as_of_date": as_of_date})
    return dict(zip(result["item_name"], result["stock"]))


def get_stock_level(item_name: str, as_of_date: Union[str, datetime]) -> pd.DataFrame:
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.isoformat()
    stock_query = """
        SELECT item_name,
               COALESCE(SUM(CASE
                   WHEN transaction_type = 'stock_orders' THEN units
                   WHEN transaction_type = 'sales' THEN -units
                   ELSE 0
               END), 0) AS current_stock
        FROM transactions
        WHERE item_name = :item_name
          AND transaction_date <= :as_of_date
    """
    return pd.read_sql(stock_query, db_engine, params={"item_name": item_name, "as_of_date": as_of_date})


def get_supplier_delivery_date(input_date_str: str, quantity: int) -> str:
    print(f"FUNC (get_supplier_delivery_date): Calculating for qty {quantity} from date string '{input_date_str}'")
    try:
        input_date_dt = datetime.fromisoformat(input_date_str.split("T")[0])
    except (ValueError, TypeError):
        print(f"WARN (get_supplier_delivery_date): Invalid date format '{input_date_str}', using today as base.")
        input_date_dt = datetime.now()

    if quantity <= 10:
        days = 0
    elif quantity <= 100:
        days = 1
    elif quantity <= 1000:
        days = 4
    else:
        days = 7

    delivery_date_dt = input_date_dt + timedelta(days=days)
    return delivery_date_dt.strftime("%Y-%m-%d")


def get_cash_balance(as_of_date: Union[str, datetime]) -> float:
    try:
        if isinstance(as_of_date, datetime):
            as_of_date = as_of_date.isoformat()
        transactions = pd.read_sql(
            "SELECT * FROM transactions WHERE transaction_date <= :as_of_date",
            db_engine,
            params={"as_of_date": as_of_date},
        )
        if not transactions.empty:
            total_sales = transactions.loc[transactions["transaction_type"] == "sales", "price"].sum()
            total_purchases = transactions.loc[transactions["transaction_type"] == "stock_orders", "price"].sum()
            return float(total_sales - total_purchases)
        return 0.0
    except Exception as exc:  # pragma: no cover - diagnostic path
        print(f"Error getting cash balance: {exc}")
        return 0.0


def generate_financial_report(as_of_date: Union[str, datetime]) -> Dict:
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.isoformat()
    cash = get_cash_balance(as_of_date)
    inventory_df = pd.read_sql("SELECT * FROM inventory", db_engine)
    inventory_value = 0.0
    inventory_summary = []
    for _, item in inventory_df.iterrows():
        stock_info = get_stock_level(item["item_name"], as_of_date)
        stock = stock_info["current_stock"].iloc[0]
        item_value = stock * item["unit_price"]
        inventory_value += item_value
        inventory_summary.append(
            {
                "item_name": item["item_name"],
                "stock": stock,
                "unit_price": item["unit_price"],
                "value": item_value,
            }
        )
    top_sales_query = """
        SELECT item_name, SUM(units) as total_units, SUM(price) as total_revenue
        FROM transactions
        WHERE transaction_type = 'sales' AND transaction_date <= :date
        GROUP BY item_name
        ORDER BY total_revenue DESC
        LIMIT 5
    """
    top_sales = pd.read_sql(top_sales_query, db_engine, params={"date": as_of_date})
    return {
        "as_of_date": as_of_date,
        "cash_balance": cash,
        "inventory_value": inventory_value,
        "total_assets": cash + inventory_value,
        "inventory_summary": inventory_summary,
        "top_selling_products": top_sales.to_dict(orient="records"),
    }


def search_quote_history(search_terms: List[str], limit: int = 5) -> List[Dict]:
    conditions = []
    params = {}
    for i, term in enumerate(search_terms):
        param_name = f"term_{i}"
        conditions.append(
            f"(LOWER(qr.response) LIKE :{param_name} OR LOWER(q.quote_explanation) LIKE :{param_name})"
        )
        params[param_name] = f"%{term.lower()}%"
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query = f"""
        SELECT qr.response AS original_request,
               q.total_amount,
               q.quote_explanation,
               q.job_type,
               q.order_size,
               q.event_type,
               q.order_date
        FROM quotes q
        JOIN quote_requests qr ON q.request_id = qr.id
        WHERE {where_clause}
        ORDER BY q.order_date DESC
        LIMIT {limit}
    """
    with db_engine.connect() as conn:
        result = conn.execute(text(query), params)
        return [dict(row._mapping) for row in result]
