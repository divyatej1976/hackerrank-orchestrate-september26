import re
import pandas as pd
from typing import List, Optional
from config import REQUIRED_OUTPUT_COLUMNS

def validate_output_dataframe(df: pd.DataFrame, requests_df: pd.DataFrame) -> List[str]:
    '''
    Performs comprehensive syntactic and semantic validation of the output DataFrame
    against all rules, invariants, and constraints specified in problem_statement.md.
    '''
    errors = []
    
    # 1. Column presence and order
    if list(df.columns) != REQUIRED_OUTPUT_COLUMNS:
        errors.append(f'Columns mismatch. Expected {REQUIRED_OUTPUT_COLUMNS}, got {list(df.columns)}')
        
    # 2. Row count matches
    if len(df) != len(requests_df):
        errors.append(f'Row count mismatch. Expected {len(requests_df)}, got {len(df)}')
        
    # 3. Request IDs match in exact order
    if list(df['request_id']) != list(requests_df['request_id']):
        errors.append('Request IDs do not match requests.csv in order')
        
    # Build requests lookup
    req_map = {r['request_id']: r.to_dict() for _, r in requests_df.iterrows()}
    
    allowed_status = {'affordable_now', 'affordable_with_plan', 'affordable_later', 'not_affordable'}
    allowed_methods = {'full_payment', 'partial_payment', 'installments', 'wait', 'not_recommended'}
    
    for idx, row in df.iterrows():
        rid = str(row['request_id'])
        req = req_map.get(rid)
        if not req:
            errors.append(f'Row {idx}: unknown request_id {rid}')
            continue
            
        req_amt = float(req['requested_amount'])
        req_date = str(req['request_date'])
        allows_partial = str(req.get('allows_partial_payment', 'false')).lower() in ['true', '1']
        
        amt_safe = float(row['amount_safe_to_pay'])
        status_val = str(row['affordability_status']).strip()
        method_val = str(row['recommended_payment_method']).strip()
        plan_str = str(row['payment_plan']).strip()
        earliest_val = str(row['earliest_date_for_full_payment']).strip() if pd.notna(row['earliest_date_for_full_payment']) else ''
        changes_str = str(row['spending_changes_needed']).strip()
        expl = str(row['decision_explanation']).strip()
        
        # Invariant: 0 <= amount_safe_to_pay <= requested_amount
        if not (0 <= amt_safe <= req_amt + 1e-4):
            errors.append(f'Row {idx} ({rid}): amount_safe_to_pay {amt_safe} not in [0, {req_amt}]')
            
        # Enum checks
        if status_val not in allowed_status:
            errors.append(f'Row {idx} ({rid}): invalid affordability_status: {status_val}')
            
        if method_val not in allowed_methods:
            errors.append(f'Row {idx} ({rid}): invalid recommended_payment_method: {method_val}')
            
        # Status & Method Consistency
        if status_val == 'affordable_now' and method_val != 'full_payment':
            errors.append(f'Row {idx} ({rid}): status is affordable_now but method is {method_val}')
            
        if status_val == 'affordable_later' and method_val != 'wait':
            errors.append(f'Row {idx} ({rid}): status is affordable_later but method is {method_val}')
            
        if status_val == 'not_affordable' and method_val != 'not_recommended':
            errors.append(f'Row {idx} ({rid}): status is not_affordable but method is {method_val}')
            
        if status_val == 'affordable_with_plan' and method_val not in ['installments', 'partial_payment', 'full_payment']:
            errors.append(f'Row {idx} ({rid}): status is affordable_with_plan but method is {method_val}')
            
        # Partial payment constraints
        if method_val == 'partial_payment':
            if not allows_partial:
                errors.append(f'Row {idx} ({rid}): recommended partial_payment but allows_partial_payment is False')
            if amt_safe <= 0 or amt_safe >= req_amt - 1e-4:
                errors.append(f'Row {idx} ({rid}): partial_payment requires 0 < amount_safe_to_pay < requested_amount, got safe={amt_safe}, req={req_amt}')
                
        # Earliest date for full payment
        if status_val == 'affordable_now' and earliest_val != req_date:
            errors.append(f'Row {idx} ({rid}): affordable_now requires earliest_date_for_full_payment == request_date ({req_date}), got {earliest_val}')
            
        if status_val == 'not_affordable' and earliest_val != '':
            errors.append(f'Row {idx} ({rid}): not_affordable requires empty earliest_date_for_full_payment, got {earliest_val}')
            
        if earliest_val:
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', earliest_val):
                errors.append(f'Row {idx} ({rid}): invalid date format for earliest_date_for_full_payment: {earliest_val}')
                
        # Spending changes validation (at most 3 distinct modifications)
        if changes_str != 'none':
            mods = [m.strip() for m in changes_str.split('|') if m.strip()]
            if len(mods) > 3:
                errors.append(f'Row {idx} ({rid}): spending_changes_needed has {len(mods)} items (max allowed: 3)')
            mod_events = []
            for m in mods:
                if m.startswith('stop:'):
                    ev_id = m.split(':')[1]
                    mod_events.append(ev_id)
                elif m.startswith('reduce_to:'):
                    parts = m.split(':')
                    if len(parts) == 3:
                        mod_events.append(parts[1])
                    else:
                        errors.append(f'Row {idx} ({rid}): invalid reduce_to syntax: {m}')
                else:
                    errors.append(f'Row {idx} ({rid}): invalid spending change syntax: {m}')
                    
            if len(set(mod_events)) != len(mod_events):
                errors.append(f'Row {idx} ({rid}): duplicate/conflicting modifications on same event: {changes_str}')
                
        # Payment plan formatting and chronological order
        if method_val == 'not_recommended':
            if plan_str != 'none':
                errors.append(f'Row {idx} ({rid}): not_recommended requires plan none, got {plan_str}')
        else:
            if plan_str == 'none':
                errors.append(f'Row {idx} ({rid}): recommended {method_val} but plan is none')
            else:
                payments = [p.strip() for p in plan_str.split('|') if p.strip()]
                prev_date = None
                for p in payments:
                    p_match = re.match(r'^(\d{4}-\d{2}-\d{2}):([\d\.]+)$', p)
                    if not p_match:
                        errors.append(f'Row {idx} ({rid}): invalid payment entry syntax: {p}')
                    else:
                        p_date = p_match.group(1)
                        if prev_date and p_date < prev_date:
                            errors.append(f'Row {idx} ({rid}): payment dates not chronological: {plan_str}')
                        prev_date = p_date
                        
                if method_val == 'partial_payment' and len(payments) != 2:
                    errors.append(f'Row {idx} ({rid}): partial_payment requires exactly 2 payments, got {len(payments)}')
                    
        # Explanation presence
        if len(expl) < 10:
            errors.append(f'Row {idx} ({rid}): decision_explanation is missing or too short')
            
    return errors
