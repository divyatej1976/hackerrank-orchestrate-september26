import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

class FinancialSimulator:
    def __init__(self, forecast_days: int = 90):
        self.forecast_days = forecast_days
        
    def simulate_trajectory(self, starting_balance: float, daily_deltas: Dict[pd.Timestamp, float], payment_schedule: Optional[Dict[pd.Timestamp, float]] = None) -> List[Tuple[pd.Timestamp, float]]:
        '''
        Simulates daily closing balances over the forecast period.
        payment_schedule is a map from date to outgoing payment amount.
        '''
        sorted_dates = sorted(daily_deltas.keys())
        trajectory = []
        c_bal = starting_balance
        
        for d in sorted_dates:
            c_bal += daily_deltas[d]
            if payment_schedule and d in payment_schedule:
                c_bal -= payment_schedule[d]
            trajectory.append((d, c_bal))
            
        return trajectory
        
    def calculate_amount_safe_to_pay(self, starting_balance: float, min_balance: float, requested_amount: float, daily_deltas: Dict[pd.Timestamp, float]) -> float:
        '''
        Calculates the maximum amount safe to pay today (request_date) before optional spending changes.
        amount_safe = min(requested_amount, max(0, min_{t}(Balance(t)) - min_balance))
        '''
        traj = self.simulate_trajectory(starting_balance, daily_deltas)
        min_bal_in_traj = min(b for _, b in traj)
        safe = max(0.0, min_bal_in_traj - min_balance)
        return min(requested_amount, safe)
        
    def find_earliest_date_for_full_payment(self, starting_balance: float, min_balance: float, requested_amount: float, daily_deltas: Dict[pd.Timestamp, float], req_date: pd.Timestamp) -> Optional[str]:
        '''
        Finds the earliest calendar date where paying requested_amount in full is safe across the subsequent forecast period.
        '''
        # If already safe today:
        if self.calculate_amount_safe_to_pay(starting_balance, min_balance, requested_amount, daily_deltas) >= requested_amount:
            return req_date.strftime('%Y-%m-%d')
            
        sorted_dates = sorted(daily_deltas.keys())
        
        # Test each date as a candidate full payment date
        for cand_date in sorted_dates:
            if cand_date < req_date:
                continue
            # Test paying full requested_amount on cand_date
            cand_payment = {cand_date: requested_amount}
            traj = self.simulate_trajectory(starting_balance, daily_deltas, payment_schedule=cand_payment)
            
            # Check if all balances from cand_date onwards are >= min_balance
            valid = True
            for d, bal in traj:
                if d >= cand_date:
                    if bal < min_balance - 1e-4:
                        valid = False
                        break
            if valid:
                return cand_date.strftime('%Y-%m-%d')
                
        return None
