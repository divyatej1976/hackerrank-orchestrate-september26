import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional

class CandidatePlan:
    def __init__(self, method: str, status: str, plan_str: str, total_amount: float, first_date: str, num_payments: int, option_id: Optional[str] = None, spending_changes: str = 'none', completes_by_deadline: bool = True):
        self.method = method
        self.status = status
        self.plan_str = plan_str
        self.total_amount = total_amount
        self.first_date = first_date
        self.num_payments = num_payments
        self.option_id = option_id or 'zzz'
        self.spending_changes = spending_changes
        self.completes_by_deadline = completes_by_deadline
        
    def __repr__(self):
        return f'<CandidatePlan {self.method} {self.status} amt={self.total_amount} changes={self.spending_changes}>'

def parse_list(val) -> List[str]:
    if pd.isna(val) or not val:
        return []
    if isinstance(val, str):
        return [x.strip() for x in val.split('|') if x.strip()]
    return list(val)

class PlanEvaluator:
    def __init__(self, simulator):
        self.sim = simulator
        
    def evaluate_all_candidates(
        self,
        profile: Dict[str, Any],
        request: Dict[str, Any],
        options_df: pd.DataFrame,
        daily_deltas: Dict[pd.Timestamp, float],
        amount_safe_today: float,
        earliest_full_date: Optional[str],
        flexible_expenses: List[Dict[str, Any]]
    ) -> List[CandidatePlan]:
        candidates: List[CandidatePlan] = []
        
        req_id = request['request_id']
        req_date = pd.to_datetime(request['request_date'])
        req_date_str = request['request_date']
        req_amount = float(request['requested_amount'])
        desired_deadline = pd.to_datetime(request['desired_completion_date'])
        start_bal = float(profile['current_available_balance'])
        min_bal = float(profile['minimum_balance_to_keep'])
        
        allowed_methods = parse_list(profile.get('payment_methods_user_will_consider'))
        max_inst_months = profile.get('max_installment_months')
        if pd.isna(max_inst_months) or max_inst_months is None:
            max_inst_months = 0
        else:
            max_inst_months = float(max_inst_months)
            
        # --- 1. Candidate Full Payment (No spending changes) ---
        if 'full_payment' in allowed_methods and amount_safe_today >= req_amount - 1e-4:
            candidates.append(CandidatePlan(
                method='full_payment',
                status='affordable_now',
                plan_str=f'{req_date_str}:{int(req_amount) if req_amount.is_integer() else req_amount:.2f}',
                total_amount=req_amount,
                first_date=req_date_str,
                num_payments=1,
                option_id='payment_option_00',
                spending_changes='none',
                completes_by_deadline=(req_date <= desired_deadline)
            ))
            
        # --- 2. Candidate Installment Options ---
        req_options = options_df[options_df['request_id'] == req_id]
        if 'installments' in allowed_methods and max_inst_months > 0:
            for _, opt in req_options.iterrows():
                if opt['payment_method'] != 'installments':
                    continue
                num_p = int(opt['number_of_payments'])
                if num_p > max_inst_months:
                    continue
                    
                p_amt = float(opt['payment_amount'])
                f_date = pd.to_datetime(opt['first_payment_date'])
                freq = int(opt['payment_frequency_days']) if pd.notna(opt['payment_frequency_days']) else 30
                tot_amt = float(opt['total_payable_amount'])
                opt_id = opt['payment_option_id']
                
                inst_dates = [f_date + timedelta(days=i * freq) for i in range(num_p)]
                last_inst_date = inst_dates[-1]
                
                pay_sched = {d: p_amt for d in inst_dates if d in daily_deltas}
                traj = self.sim.simulate_trajectory(start_bal, daily_deltas, payment_schedule=pay_sched)
                
                min_b = min(b for _, b in traj)
                if min_b >= min_bal - 1e-4:
                    plan_parts = [d.strftime('%Y-%m-%d') + ':' + (str(int(p_amt)) if p_amt.is_integer() else f'{p_amt:.2f}') for d in inst_dates]
                    candidates.append(CandidatePlan(
                        method='installments',
                        status='affordable_with_plan',
                        plan_str='|'.join(plan_parts),
                        total_amount=tot_amt,
                        first_date=f_date.strftime('%Y-%m-%d'),
                        num_payments=num_p,
                        option_id=opt_id,
                        spending_changes='none',
                        completes_by_deadline=(last_inst_date <= desired_deadline)
                    ))
                    
        # --- 3. Candidate Partial Payment ---
        allows_partial = bool(request['allows_partial_payment'])
        if allows_partial and 'partial_payment' in allowed_methods:
            if 0 < amount_safe_today < req_amount and earliest_full_date is not None:
                efd = pd.to_datetime(earliest_full_date)
                if efd <= desired_deadline:
                    rem_amt = req_amount - amount_safe_today
                    p1 = f'{req_date_str}:{int(amount_safe_today) if amount_safe_today.is_integer() else amount_safe_today:.2f}'
                    p2 = f'{earliest_full_date}:{int(rem_amt) if rem_amt.is_integer() else rem_amt:.2f}'
                    candidates.append(CandidatePlan(
                        method='partial_payment',
                        status='affordable_with_plan',
                        plan_str=f'{p1}|{p2}',
                        total_amount=req_amount,
                        first_date=req_date_str,
                        num_payments=2,
                        option_id='payment_option_partial',
                        spending_changes='none',
                        completes_by_deadline=True
                    ))
                    
        # --- 4. Candidate Flexible Spending Adjustments ---
        if amount_safe_today < req_amount - 1e-4 and flexible_expenses and 'full_payment' in allowed_methods:
            willing_stop = parse_list(profile.get('expense_categories_user_is_willing_to_stop'))
            willing_reduce = parse_list(profile.get('expense_categories_user_is_willing_to_reduce'))
            protect = parse_list(profile.get('expense_categories_to_protect'))
            
            stoppable = [e for e in flexible_expenses if e['category'] in willing_stop and e['category'] not in protect]
            reducible = [e for e in flexible_expenses if e['category'] in willing_reduce and e['category'] not in protect and e['minimum_allowed_amount'] is not None]
            
            adjustment_combos = []
            for s in stoppable:
                adjustment_combos.append([('stop', s)])
            for r in reducible:
                adjustment_combos.append([('reduce_to', r)])
            for s in stoppable:
                for r in reducible:
                    if s['event_id'] != r['event_id']:
                        adjustment_combos.append([('stop', s), ('reduce_to', r)])
                        
            for combo in adjustment_combos:
                adj_deltas = dict(daily_deltas)
                changes_strs = []
                for action, item in combo:
                    ev_id = item['event_id']
                    amt = item['amount']
                    if action == 'stop':
                        changes_strs.append(f'stop:{ev_id}')
                        dom = item['last_date'].day
                        for d in adj_deltas:
                            if d.day == dom:
                                adj_deltas[d] += amt
                    elif action == 'reduce_to':
                        new_amt = item['minimum_allowed_amount']
                        changes_strs.append(f'reduce_to:{ev_id}:{int(new_amt) if new_amt.is_integer() else new_amt:.2f}')
                        diff = amt - new_amt
                        dom = item['last_date'].day
                        for d in adj_deltas:
                            if d.day == dom:
                                adj_deltas[d] += diff
                                
                adj_safe = self.sim.calculate_amount_safe_to_pay(start_bal, min_bal, req_amount, adj_deltas)
                if adj_safe >= req_amount - 1e-4:
                    candidates.append(CandidatePlan(
                        method='full_payment',
                        status='affordable_with_plan',
                        plan_str=f'{req_date_str}:{int(req_amount) if req_amount.is_integer() else req_amount:.2f}',
                        total_amount=req_amount,
                        first_date=req_date_str,
                        num_payments=1,
                        option_id='payment_option_adjusted',
                        spending_changes='|'.join(changes_strs),
                        completes_by_deadline=(req_date <= desired_deadline)
                    ))
                    break
                    
        # --- 5. Candidate Wait ---
        if 'full_payment' in allowed_methods and earliest_full_date is not None:
            efd = pd.to_datetime(earliest_full_date)
            candidates.append(CandidatePlan(
                method='wait',
                status='affordable_later',
                plan_str=f'{earliest_full_date}:{int(req_amount) if req_amount.is_integer() else req_amount:.2f}',
                total_amount=req_amount,
                first_date=earliest_full_date,
                num_payments=1,
                option_id='payment_option_wait',
                spending_changes='none',
                completes_by_deadline=(efd <= desired_deadline)
            ))
            
        # --- 6. Fallback: Not Recommended ---
        candidates.append(CandidatePlan(
            method='not_recommended',
            status='not_affordable',
            plan_str='none',
            total_amount=float('inf'),
            first_date='9999-12-31',
            num_payments=0,
            option_id='payment_option_none',
            spending_changes='none',
            completes_by_deadline=False
        ))
        
        return candidates
