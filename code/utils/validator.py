import pandas as pd
from typing import List
from config import REQUIRED_OUTPUT_COLUMNS

def validate_output_dataframe(df: pd.DataFrame, requests_df: pd.DataFrame) -> List[str]:
    errors = []
    
    # 1. Column presence and order
    if list(df.columns) != REQUIRED_OUTPUT_COLUMNS:
        errors.append(f'Columns mismatch. Expected {REQUIRED_OUTPUT_COLUMNS}, got {list(df.columns)}')
        
    # 2. Row count matches
    if len(df) != len(requests_df):
        errors.append(f'Row count mismatch. Expected {len(requests_df)}, got {len(df)}')
        
    # 3. Request IDs match
    if list(df['request_id']) != list(requests_df['request_id']):
        errors.append('Request IDs do not match requests.csv in order')
        
    # 4. Values validity
    allowed_status = {'affordable_now', 'affordable_with_plan', 'affordable_later', 'not_affordable'}
    allowed_methods = {'full_payment', 'partial_payment', 'installments', 'wait', 'not_recommended'}
    
    req_lookup = dict(zip(requests_df['request_id'], requests_df['requested_amount']))
    
    for idx, row in df.iterrows():
        rid = row['request_id']
        amt_safe = row['amount_safe_to_pay']
        req_amt = req_lookup.get(rid, 0.0)
        status_val = str(row['affordability_status'])
        method_val = str(row['recommended_payment_method'])
        
        # Invariant: 0 <= amount_safe_to_pay <= requested_amount
        if not (0 <= amt_safe <= req_amt + 1e-4):
            errors.append(f'Row {idx} ({rid}): amount_safe_to_pay {amt_safe} not in [0, {req_amt}]')
            
        if status_val not in allowed_status:
            errors.append(f'Row {idx} ({rid}): invalid affordability_status: ' + status_val)
            
        if method_val not in allowed_methods:
            errors.append(f'Row {idx} ({rid}): invalid recommended_payment_method: ' + method_val)
            
        if status_val == 'affordable_now':
            if method_val != 'full_payment' and 'full_payment' in method_val:
                pass
                
    return errors
