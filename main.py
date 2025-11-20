import os
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from database import db, create_document, get_documents
from schemas import Customer, Lead, Feedback, Admin

app = FastAPI(title="Agency Leads Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Agency Leads Dashboard API"}


@app.get("/test")
def test_database():
    """Verify database connectivity and list collections"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    return response


# ----- Simple Customer Auth -----
class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    customer_id: str
    name: str


# NOTE: For demo purposes we implement a very simple token mechanism (no JWT)
# In production, use JWT with proper hashing and verification.


def get_customer_by_email(email: str) -> Optional[dict]:
    customers = db["customer"].find_one({"email": email}) if db else None
    return customers


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    customer = get_customer_by_email(payload.email)
    if not customer:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # For demo: store plain text password_hash during seeding; here we compare directly
    # Replace with proper hashing (bcrypt) if needed.
    if payload.password != customer.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = str(customer.get("_id"))  # naive token as customer id
    return LoginResponse(token=token, customer_id=token, name=customer.get("name", "User"))


# Dependency to get current customer from token header

def get_current_customer(authorization: Optional[str] = Header(default=None, alias="Authorization")):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.replace("Bearer ", "")
    try:
        oid = __import__("bson").ObjectId(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    customer = db["customer"].find_one({"_id": oid})
    if not customer:
        raise HTTPException(status_code=401, detail="Invalid token")
    return customer


# ----- Admin Auth -----
class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    token: str
    admin_id: str
    username: str
    role: str = "admin"


def ensure_default_admin():
    """Create default admin (admin/admin) if it doesn't exist. Safe no-op if DB unavailable."""
    try:
        if db is None:
            return
        existing = db["admin"].find_one({"username": "admin"})
        if not existing:
            data = Admin(username="admin", password_hash="admin", role="admin", is_active=True)
            create_document("admin", data)
    except Exception:
        # Don't crash app on startup if DB is unreachable
        pass


@app.on_event("startup")
async def startup_event():
    # best-effort admin seed; ignore failures
    ensure_default_admin()


@app.post("/admin/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    admin = db["admin"].find_one({"username": payload.username})
    if not admin or payload.password != admin.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = str(admin.get("_id"))
    return AdminLoginResponse(token=token, admin_id=token, username=admin.get("username", "admin"), role="admin")


def get_current_admin(authorization: Optional[str] = Header(default=None, alias="Authorization")):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.replace("Bearer ", "")
    try:
        oid = __import__("bson").ObjectId(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    admin = db["admin"].find_one({"_id": oid})
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid token")
    return admin


# Leads Endpoints
class LeadCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None


@app.post("/leads", response_model=dict)
def create_lead(payload: LeadCreate, customer: dict = Depends(get_current_customer)):
    data = Lead(
        customer_id=str(customer["_id"]),
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        source=payload.source,
    )
    inserted_id = create_document("lead", data)
    return {"id": inserted_id}


@app.get("/leads", response_model=List[dict])
def list_leads(customer: dict = Depends(get_current_customer)):
    docs = get_documents("lead", {"customer_id": str(customer["_id"])}, limit=100)
    # Convert ObjectId to str
    for d in docs:
        d["_id"] = str(d["_id"]) if "_id" in d else None
    return docs


# Feedback Endpoints
class FeedbackCreate(BaseModel):
    lead_id: str
    rating: Optional[int] = None
    disposition: Optional[str] = None
    comment: Optional[str] = None


@app.post("/feedback", response_model=dict)
def submit_feedback(payload: FeedbackCreate, customer: dict = Depends(get_current_customer)):
    # Ensure lead belongs to this customer
    lead = db["lead"].find_one({"_id": __import__("bson").ObjectId(payload.lead_id), "customer_id": str(customer["_id"])})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    data = Feedback(
        lead_id=payload.lead_id,
        customer_id=str(customer["_id"]),
        rating=payload.rating,
        disposition=payload.disposition or "follow_up",
        comment=payload.comment,
        submitted_at=datetime.now(timezone.utc),
    )
    inserted_id = create_document("feedback", data)
    return {"id": inserted_id}


@app.get("/feedback/{lead_id}", response_model=List[dict])
def get_feedback_for_lead(lead_id: str, customer: dict = Depends(get_current_customer)):
    # Ensure lead belongs to this customer
    lead = db["lead"].find_one({"_id": __import__("bson").ObjectId(lead_id), "customer_id": str(customer["_id"])})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    docs = get_documents("feedback", {"lead_id": lead_id, "customer_id": str(customer["_id"])}, limit=200)
    for d in docs:
        d["_id"] = str(d["_id"]) if "_id" in d else None
    return docs


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
