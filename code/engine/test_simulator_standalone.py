import sys
from pathlib import Path

code_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(code_dir))

import pandas as pd
from ingestion.fx_converter import FXConverter
from ingestion.message_parser import MessageParser
from engine.cash_flow import CashFlowReconstructor
from engine.simulator import FinancialSimulator

def run_standalone_test():
    print('='*70)
    print('STANDALONE 90-DAY SIMULATOR TEST ON 3 REPRESENTATIVE SAMPLES')
    print('='*70)
    
    enriched_events_csv = code_dir / 'data' / 'enriched_events.csv'
    df_events = pd.read_csv(enriched_events_csv)
    df_profiles = pd.read_csv(code_dir.parent / 'dataset' / 'financial_profiles.csv')
    df_rates = pd.read_csv(code_dir.parent / 'dataset' / 'exchange_rates.csv')
    df_messages = pd.read_csv(code_dir.parent / 'dataset' / 'messages.csv')
    df_samples = pd.read_csv(code_dir.parent / 'dataset' / 'sample_requests.csv')
    
    fx = FXConverter(df_rates)
    msg_parser = MessageParser(df_messages)
    cash_recon = CashFlowReconstructor(df_events, fx, msg_parser)
    simulator = FinancialSimulator()
    
    profiles_map = {r['user_id']: r.to_dict() for _, r in df_profiles.iterrows()}
    sample_requests = ['request_01', 'request_03', 'request_05']
    
    for rid in sample_requests:
        s_row = df_samples[df_samples['request_id'] == rid].iloc[0].to_dict()
        uid = s_row['user_id']
        prof = profiles_map[uid]
        curr = prof['home_currency']
        start_bal = float(prof['current_available_balance'])
        min_bal = float(prof['minimum_balance_to_keep'])
        req_amt = float(s_row['requested_amount'])
        req_date = pd.to_datetime(s_row['request_date'])
        req_date_str = str(s_row['request_date'])
        gt_safe = s_row['amount_safe_to_pay']
        gt_earliest = str(s_row['earliest_date_for_full_payment'])
        
        print(f'\n--- Testing {rid} (User: {uid}, Currency: {curr}) ---')
        print(f'Starting Balance:       {curr} {start_bal:,.2f}')
        print(f'Minimum Balance:        {curr} {min_bal:,.2f}')
        print(f'Requested Amount:       {curr} {req_amt:,.2f} on ' + req_date_str)
        
        daily_deltas, flex, adj = cash_recon.get_user_cash_schedule(uid, req_date_str, curr)
        
        # Simulate base trajectory
        base_traj = simulator.simulate_trajectory(start_bal, daily_deltas)
        min_traj_bal = min(b for _, b in base_traj)
        min_traj_date = min(base_traj, key=lambda x: x[1])[0].strftime('%Y-%m-%d')
        
        print(f'Lowest Point in 90-Day Trajectory (before payment): {curr} {min_traj_bal:,.2f} on {min_traj_date}')
        
        # Calculate amount_safe_to_pay
        safe_amt = simulator.calculate_amount_safe_to_pay(start_bal, min_bal, req_amt, daily_deltas)
        earliest_full = simulator.find_earliest_date_for_full_payment(start_bal, min_bal, req_amt, daily_deltas, req_date)
        
        print(f'Calculated amount_safe_to_pay:            {safe_amt:,.2f}  (Ground Truth: {gt_safe})')
        print(f'Calculated earliest_date_for_full_payment: {earliest_full}  (Ground Truth: {gt_earliest})')

if __name__ == '__main__':
    run_standalone_test()
