"""
Database Schemas for Agency Leads Dashboard

Each Pydantic model represents a collection in MongoDB.
Collection name is the lowercase of the class name.
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal
from datetime import datetime


class Customer(BaseModel):
    """
    Customers collection schema
    Collection: "customer"
    """
    name: str = Field(..., description="Company or contact name")
    email: EmailStr = Field(..., description="Login email")
    password_hash: str = Field(..., description="Hashed password")
    is_active: bool = Field(True, description="Whether account is active")


class Lead(BaseModel):
    """
    Leads generated for customers
    Collection: "lead"
    """
    customer_id: str = Field(..., description="Owner customer id as string")
    name: str = Field(..., description="Lead full name")
    email: Optional[EmailStr] = Field(None, description="Lead email")
    phone: Optional[str] = Field(None, description="Lead phone")
    source: Optional[str] = Field(None, description="Acquisition source")
    status: Literal["new", "contacted", "qualified", "unqualified", "follow_up"] = "new"
    notes: Optional[str] = None


class Feedback(BaseModel):
    """
    Feedback given by customers per lead
    Collection: "feedback"
    """
    lead_id: str = Field(..., description="Lead id as string")
    customer_id: str = Field(..., description="Customer id as string")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Qualification rating 1-5")
    disposition: Literal["qualified", "unqualified", "follow_up", "wrong_number", "no_response"] = "follow_up"
    comment: Optional[str] = None
    submitted_at: Optional[datetime] = None
