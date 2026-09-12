import pandas as pd
from typing import Dict, Any, Optional
from engine.candidate_evaluator import CandidatePlan

class DecisionExplainer:
    @staticmethod
    def generate_explanation(
        plan: CandidatePlan,
        request: Dict[str, Any],
        profile: Dict[str, Any],
        amount_safe_today: float,
        earliest_full_date: Optional[str]
    ) -> str:
        curr = profile['home_currency']
        min_bal = float(profile['minimum_balance_to_keep'])
        req_amt = float(request['requested_amount'])
        deadline_str = request['desired_completion_date']
        
        # Format currency amount
        def fmt(amt: float) -> str:
            if amt.is_integer():
                return f'{curr} {int(amt):,}'
            return f'{curr} {amt:,.2f}'
            
        def fmt_date(d_str: str) -> str:
            try:
                dt = pd.to_datetime(d_str)
                return dt.strftime('%d %B %Y').lstrip('0')
            except Exception:
                return d_str
                
        # 1. Full payment affordable now
        if plan.status == 'affordable_now' and plan.method == 'full_payment':
            return f'Pay {fmt(req_amt)} today. This leaves at least {fmt(min_bal)} available over the next 90 days.'
            
        # 2. Installments
        if plan.method == 'installments':
            parts = plan.plan_str.split('|')
            num_inst = len(parts)
            inst_amt = float(parts[0].split(':')[1])
            first_dt = parts[0].split(':')[0]
            return f'Use {num_inst} installments of {fmt(inst_amt)}, starting {fmt_date(first_dt)}. This leaves at least {fmt(min_bal)} available.'
            
        # 3. Partial payment
        if plan.method == 'partial_payment':
            parts = plan.plan_str.split('|')
            p1_amt = float(parts[0].split(':')[1])
            p2_amt = float(parts[1].split(':')[1])
            p2_date = parts[1].split(':')[0]
            return f'Pay {fmt(p1_amt)} today and the remaining {fmt(p2_amt)} on {fmt_date(p2_date)}. This completes the full request and keeps the {fmt(min_bal)} minimum protected.'
            
        # 4. Spending changes needed
        if plan.spending_changes != 'none':
            actions = plan.spending_changes.split('|')
            action_phrases = []
            for act in actions:
                if act.startswith('stop:'):
                    ev_id = act.split(':')[1]
                    action_phrases.append(f'stop {ev_id}')
                elif act.startswith('reduce_to:'):
                    _, ev_id, new_amt = act.split(':')
                    action_phrases.append(f'reduce {ev_id} to {fmt(float(new_amt))}')
            spending_text = ' and '.join(action_phrases).capitalize()
            return f'{spending_text}, then pay {fmt(req_amt)} today. This leaves at least {fmt(min_bal)} available.'
            
        # 5. Wait
        if plan.method == 'wait' and earliest_full_date:
            return f'Pay {fmt(req_amt)} in full on {fmt_date(earliest_full_date)}. Paying earlier would take the balance below the {fmt(min_bal)} minimum.'
            
        # 6. Not recommended
        if amount_safe_today > 0:
            return f'Do not proceed with the {fmt(req_amt)} request. Although {fmt(amount_safe_today)} is available today, the full amount cannot be completed safely within 90 days.'
        return f'Do not make this payment by {fmt_date(deadline_str)}. None of the available options keeps the {fmt(min_bal)} minimum protected.'
