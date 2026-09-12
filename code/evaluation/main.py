import sys
from pathlib import Path

# Add code/ directory to path
current_dir = Path(__file__).resolve().parent
code_dir = current_dir.parent
sys.path.insert(0, str(code_dir))

import pandas as pd
import numpy as np
from config import (
    SAMPLE_REQUESTS_FILE, PROFILES_FILE, EVENTS_FILE,
    OPTIONS_FILE, EXCHANGE_RATES_FILE, MESSAGES_FILE, IMAGES_FILE
)
from ingestion.image_extractor import resolve_image_amounts
from ingestion.fx_converter import FXConverter
from ingestion.message_parser import MessageParser
from engine.cash_flow import CashFlowReconstructor
from engine.simulator import FinancialSimulator
from engine.candidate_evaluator import PlanEvaluator
from engine.ranker import PlanRanker
from explainer.generator import DecisionExplainer

def evaluate_samples():
    print('Loading datasets for evaluation...')
    df_samples = pd.read_csv(SAMPLE_REQUESTS_FILE)
    df_profiles = pd.read_csv(PROFILES_FILE)
    df_events = pd.read_csv(EVENTS_FILE)
    df_options = pd.read_csv(OPTIONS_FILE)
    df_rates = pd.read_csv(EXCHANGE_RATES_FILE)
    df_messages = pd.read_csv(MESSAGES_FILE)
    df_images = pd.read_csv(IMAGES_FILE)
    
    # 1. Ingestion & Preprocessing
    events_resolved = resolve_image_amounts(df_events, df_images)
    fx = FXConverter(df_rates)
    msg_parser = MessageParser(df_messages)
    
    # 2. Engines
    cash_recon = CashFlowReconstructor(events_resolved, fx, msg_parser)
    simulator = FinancialSimulator()
    evaluator = PlanEvaluator(simulator)
    ranker = PlanRanker()
    
    # Profiles map
    profiles_map = {r['user_id']: r.to_dict() for _, r in df_profiles.iterrows()}
    
    predictions = []
    
    print(f'Evaluating {len(df_samples)} sample requests...')
    for _, req_row in df_samples.iterrows():
        req = req_row.to_dict()
        uid = req['user_id']
        prof = profiles_map.get(uid, {})
        curr = prof.get('home_currency', 'USD')
        start_bal = float(prof.get('current_available_balance', 0.0))
        min_bal = float(prof.get('minimum_balance_to_keep', 0.0))
        req_amt = float(req['requested_amount'])
        req_date = pd.to_datetime(req['request_date'])
        
        # Cash schedule
        daily_deltas, flexible_expenses, adjustments = cash_recon.get_user_cash_schedule(uid, req['request_date'], curr)
        
        # Base safety calculations
        amt_safe = simulator.calculate_amount_safe_to_pay(start_bal, min_bal, req_amt, daily_deltas)
        earliest_full = simulator.find_earliest_date_for_full_payment(start_bal, min_bal, req_amt, daily_deltas, req_date)
        
        # Candidate plans
        candidates = evaluator.evaluate_all_candidates(
            prof, req, df_options, daily_deltas, amt_safe, earliest_full, flexible_expenses
        )
        
        best_plan = ranker.rank_candidates(candidates)
        
        # Explanations
        expl = DecisionExplainer.generate_explanation(best_plan, req, prof, amt_safe, earliest_full)
        
        predictions.append({
            'request_id': req['request_id'],
            'amount_safe_to_pay': round(amt_safe, 2),
            'affordability_status': best_plan.status,
            'recommended_payment_method': best_plan.method,
            'payment_plan': best_plan.plan_str,
            'earliest_date_for_full_payment': earliest_full or '',
            'spending_changes_needed': best_plan.spending_changes,
            'decision_explanation': expl
        })
        
    df_pred = pd.DataFrame(predictions)
    
    # Compare with ground truth
    print('\n' + '='*50)
    print('EVALUATION RESULTS VS SAMPLE_REQUESTS.CSV')
    print('='*50)
    
    status_match = (df_pred['affordability_status'] == df_samples['affordability_status']).mean()
    method_match = (df_pred['recommended_payment_method'] == df_samples['recommended_payment_method']).mean()
    changes_match = (df_pred['spending_changes_needed'] == df_samples['spending_changes_needed']).mean()
    
    print(f'Affordability Status Accuracy: {status_match * 100:.1f}%')
    print(f'Payment Method Accuracy:       {method_match * 100:.1f}%')
    print(f'Spending Changes Accuracy:     {changes_match * 100:.1f}%')
    
    # Detailed comparison
    print('\nDetailed Breakdown:')
    for i in range(len(df_samples)):
        rid = df_samples.loc[i, 'request_id']
        t_status = df_samples.loc[i, 'affordability_status']
        p_status = df_pred.loc[i, 'affordability_status']
        t_method = df_samples.loc[i, 'recommended_payment_method']
        p_method = df_pred.loc[i, 'recommended_payment_method']
        t_safe = df_samples.loc[i, 'amount_safe_to_pay']
        p_safe = df_pred.loc[i, 'amount_safe_to_pay']
        
        mark = 'OK' if (t_status == p_status and t_method == p_method) else 'MISMATCH'
        print(f'[{mark}] {rid}: Status (True: {t_status} | Pred: {p_status}), Method (True: {t_method} | Pred: {p_method}), Safe (True: {t_safe} | Pred: {p_safe})')

if __name__ == '__main__':
    evaluate_samples()
