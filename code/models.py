from typing import Optional, List
from pydantic import BaseModel, Field

class FinancialProfile(BaseModel):
    user_id: str
    home_currency: str
    current_available_balance: float
    minimum_balance_to_keep: float
    financial_priorities: List[str] = Field(default_factory=list)
    expense_categories_to_protect: List[str] = Field(default_factory=list)
    expense_categories_user_is_willing_to_reduce: List[str] = Field(default_factory=list)
    expense_categories_user_is_willing_to_stop: List[str] = Field(default_factory=list)
    payment_methods_user_will_consider: List[str] = Field(default_factory=list)
    max_installment_months: Optional[float] = None

class FinancialEvent(BaseModel):
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str
    amount: float
    currency: str
    event_date: str
    settlement_date: str
    status: str
    linked_event_id: Optional[str] = None
    flexibility: str = 'fixed'
    minimum_allowed_amount: Optional[float] = None

class RequestItem(BaseModel):
    request_id: str
    user_id: str
    request_date: str
    request_type: str
    requested_amount: float
    desired_completion_date: str
    allows_partial_payment: bool
    request_text: str

class PaymentOption(BaseModel):
    payment_option_id: str
    request_id: str
    payment_method: str
    payment_amount: float
    number_of_payments: int
    first_payment_date: str
    payment_frequency_days: Optional[float] = None
    financing_fee: float = 0.0
    total_payable_amount: float

class PredictionOutput(BaseModel):
    request_id: str
    amount_safe_to_pay: float
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    earliest_date_for_full_payment: str
    spending_changes_needed: str
    decision_explanation: str
