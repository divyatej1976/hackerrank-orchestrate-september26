import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional
from itertools import combinations

class CandidatePlan:
    def __init__(
        self,
        method: str,
        status: str,
        plan_str: str,
        total_amount: float,
        first_date: str,
        num_payments: int,
        option_id: Optional[str] = None,
        spending_changes: str = 'none',
        completes_by_deadline: bool = True
    ):
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
        return f'<CandidatePlan {self.method} {self.status} amt={self.total_amount} changes={self.spending_changes} deadline={self.completes_by_deadline}>'

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
        flexible_occurrences: List[Dict[str, Any]],
        flexible_catalog: List[Dict[str, Any]]
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
        max_inst_months = float(max_inst_months) if (pd.notna(max_inst_months) and max_inst_months is not None) else 0.0
            
        # --- 1. Full Payment (No spending changes) ---
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
            
        # --- 2. Installment Options ---
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
                opt_id = str(opt['payment_option_id'])
                
                inst_dates = [f_date + timedelta(days=i * freq) for i in range(num_p)]
                last_inst_date = inst_dates[-1]
                
                # Check that NO installment payment is silently omitted:
                # All installment dates must be simulated
                pay_sched = {d: p_amt for d in inst_dates}
                
                # Extend daily deltas if installment schedule extends past current dictionary
                sim_deltas = dict(daily_deltas)
                for d in inst_dates:
                    if d not in sim_deltas:
                        sim_deltas[d] = 0.0
                        
                traj = self.sim.simulate_trajectory(start_bal, sim_deltas, payment_schedule=pay_sched)
                min_b = min(b for _, b in traj)
                
                if min_b >= min_bal - 1e-4:
                    plan_parts = [
                        d.strftime('%Y-%m-%d') + ':' + (str(int(p_amt)) if p_amt.is_integer() else f'{p_amt:.2f}')
                        for d in inst_dates
                    ]
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
                    
        # --- 3. Partial Payment ---
        allows_partial = str(request.get('allows_partial_payment', 'false')).lower() in ['true', '1']
        if (
            allows_partial and
            'partial_payment' in allowed_methods and
            0 < amount_safe_today < req_amount - 1e-4
        ):
            p1_amt = round(amount_safe_today, 2)
            p2_amt = round(req_amount - p1_amt, 2)
            reduced_start_bal = start_bal - p1_amt
            next_day = req_date + timedelta(days=1)
            
            # Find earliest safe date specifically for remainder amount after p1 has been paid
            rem_safe_date = self.sim.find_earliest_safe_date_for_amount(
                starting_balance=reduced_start_bal,
                min_balance=min_bal,
                amount=p2_amt,
                daily_deltas=daily_deltas,
                req_date=req_date,
                start_from_date=next_day
            )
            
            if rem_safe_date is not None:
                rem_dt = pd.to_datetime(rem_safe_date)
                if rem_dt <= desired_deadline:
                    p1 = f'{req_date_str}:{int(p1_amt) if p1_amt.is_integer() else p1_amt:.2f}'
                    p2 = f'{rem_safe_date}:{int(p2_amt) if p2_amt.is_integer() else p2_amt:.2f}'
                    
                    pay_sched = {req_date: p1_amt, rem_dt: p2_amt}
                    sim_deltas = dict(daily_deltas)
                    if rem_dt not in sim_deltas:
                        sim_deltas[rem_dt] = 0.0
                    traj = self.sim.simulate_trajectory(start_bal, sim_deltas, payment_schedule=pay_sched)
                    if min(b for _, b in traj) >= min_bal - 1e-4:
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
                    
        # --- 4. Flexible Spending Adjustments (1, 2, or 3 distinct modifications) ---
        if amount_safe_today < req_amount - 1e-4 and flexible_catalog and 'full_payment' in allowed_methods:
            willing_stop = parse_list(profile.get('expense_categories_user_is_willing_to_stop'))
            willing_reduce = parse_list(profile.get('expense_categories_user_is_willing_to_reduce'))
            protect = parse_list(profile.get('expense_categories_to_protect'))
            
            # Form allowable individual actions per event_id
            possible_actions = []
            for item in flexible_catalog:
                cat = item['category']
                if cat in protect:
                    continue
                ev_id = item['event_id']
                flex = item['flexibility']
                amt = item['amount']
                min_amt = item['minimum_allowed_amount']
                
                if (flex in ['stoppable', 'reducible_or_stoppable']) and (cat in willing_stop):
                    possible_actions.append(('stop', ev_id, amt, f'stop:{ev_id}'))
                    
                if (flex in ['reducible', 'reducible_or_stoppable']) and (cat in willing_reduce) and (min_amt is not None):
                    savings = amt - min_amt
                    if savings > 0:
                        change_str = f'reduce_to:{ev_id}:{int(min_amt) if min_amt.is_integer() else min_amt:.2f}'
                        possible_actions.append(('reduce_to', ev_id, savings, change_str, min_amt))
                        
            # Sort actions by savings potential descending
            possible_actions.sort(key=lambda a: a[2], reverse=True)
            
            # Generate valid combinations of 1, 2, and 3 actions (mutually exclusive event_ids)
            valid_combos = []
            for k in [1, 2, 3]:
                for combo in combinations(possible_actions, k):
                    event_ids = [act[1] for act in combo]
                    if len(set(event_ids)) == len(event_ids):
                        valid_combos.append(combo)
                        
            # Test combinations in order of fewest changes, then highest savings
            valid_combos.sort(key=lambda c: (len(c), -sum(act[2] for act in c)))
            
            for combo in valid_combos:
                adj_deltas = dict(daily_deltas)
                changes_strs = []
                action_by_eid = {act[1]: act for act in combo}
                
                # Apply changes directly to concrete flexible occurrences
                for occ in flexible_occurrences:
                    eid = occ['event_id']
                    if eid in action_by_eid:
                        act = action_by_eid[eid]
                        o_date = occ['date']
                        if act[0] == 'stop':
                            adj_deltas[o_date] += occ['amount']
                        elif act[0] == 'reduce_to':
                            new_amt = act[4]
                            savings = occ['amount'] - new_amt
                            adj_deltas[o_date] += savings
                            
                for act in combo:
                    changes_strs.append(act[3])
                    
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
                    break  # Found best minimal-change valid combination
                    
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
            num_payments=999,
            option_id='payment_option_none',
            spending_changes='none',
            completes_by_deadline=False
        ))
        
        return candidates
