import sys
import unittest
from pathlib import Path

# Add code/ to path
current_dir = Path(__file__).resolve().parent
code_dir = current_dir.parent
sys.path.insert(0, str(code_dir))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from config import *
from ingestion.fx_converter import FXConverter
from ingestion.message_parser import MessageParser
from ingestion.image_extractor import extract_amount_from_ocr_text
from engine.cash_flow import CashFlowReconstructor, generate_monthly_dates
from engine.simulator import FinancialSimulator
from engine.candidate_evaluator import PlanEvaluator, CandidatePlan
from engine.ranker import PlanRanker
from utils.validator import validate_output_dataframe

class TestBuyOrWaitComprehensive(unittest.TestCase):

    def setUp(self):
        self.df_rates = pd.read_csv(EXCHANGE_RATES_FILE)
        self.fx = FXConverter(self.df_rates)

    # 1. Image OCR extraction test
    def test_image_ocr_text_extraction(self):
        # Proves extractor works from real OCR text lines rather than a lookup map
        sample_lines_01 = ['PAY SLIP Aug-2019', 'Net Pay', '4,365,000', 'Four Million Three Hundred Sixty Five Thousand Rupiahs']
        self.assertEqual(extract_amount_from_ocr_text(sample_lines_01), 4365000.0)
        
        sample_lines_02 = ['Rent Receipt', 'Balance Due:', '1 oo 000.00']
        self.assertEqual(extract_amount_from_ocr_text(sample_lines_02), 100000.0)
        
        sample_lines_05 = ['Total : Seven Hundred Four Rupees and Five Paise Only', '704.05']
        self.assertEqual(extract_amount_from_ocr_text(sample_lines_05), 704.05)

    # 2. Calendar handling across month lengths and leap years
    def test_calendar_recurring_dates(self):
        # 31st anchor across 2024 (leap year)
        dates_leap = generate_monthly_dates(pd.to_datetime('2024-01-01'), 31, pd.to_datetime('2024-04-30'))
        self.assertEqual(dates_leap[0], pd.to_datetime('2024-01-31'))
        self.assertEqual(dates_leap[1], pd.to_datetime('2024-02-29'))  # 29-day Feb
        self.assertEqual(dates_leap[2], pd.to_datetime('2024-03-31'))  # 31-day Mar
        self.assertEqual(dates_leap[3], pd.to_datetime('2024-04-30'))  # 30-day Apr

        # 31st anchor across 2025 (non-leap year)
        dates_non_leap = generate_monthly_dates(pd.to_datetime('2025-01-01'), 31, pd.to_datetime('2025-03-31'))
        self.assertEqual(dates_non_leap[1], pd.to_datetime('2025-02-28'))  # 28-day Feb

    # 3. FX Conversion tests
    def test_fx_conversion_all_pairs(self):
        currencies = ['INR', 'USD', 'EUR', 'IDR', 'ZAR']
        for c1 in currencies:
            for c2 in currencies:
                rate = self.fx.get_rate(c1, c2, '2025-06-15')
                self.assertGreater(rate, 0.0)
                # Test inverse symmetry
                inv_rate = self.fx.get_rate(c2, c1, '2025-06-15')
                self.assertAlmostEqual(rate * inv_rate, 1.0, places=4)
                
    def test_fx_no_silent_fallback(self):
        # Unknown currency must raise ValueError rather than returning 1:1
        with self.assertRaises(ValueError):
            self.fx.get_rate('XYZ', 'USD', '2025-06-15')

    # 4. Message parsing: English & Indonesian variations
    def test_message_parser_variations(self):
        df_dummy = pd.DataFrame([
            {'user_id': 'u1', 'message_text': 'Your confirmed salary is now expected on 2025-05-15 with salary of USD 4500'},
            {'user_id': 'u2', 'message_text': 'Gaji bulanan Anda naik menjadi IDR 40000000 berlaku mulai 2025-09-01'},
            {'user_id': 'u3', 'message_text': 'StayLedger increases monthly rent by 12%'},
            {'user_id': 'u4', 'message_text': 'The current seasonal contract has ended'},
            {'user_id': 'u5', 'message_text': 'Your refund has been initiated but has not reached your account yet'}
        ])
        parser = MessageParser(df_dummy)
        
        adj_1 = parser.get_user_adjustments('u1')
        self.assertEqual(adj_1['salary_override'], 4500.0)
        self.assertEqual(adj_1['salary_effective_date'], '2025-05-15')
        
        adj_2 = parser.get_user_adjustments('u2')
        self.assertEqual(adj_2['salary_override'], 40000000.0)
        self.assertEqual(adj_2['salary_effective_date'], '2025-09-01')
        
        adj_3 = parser.get_user_adjustments('u3')
        self.assertEqual(adj_3['rent_increase_pct'], 0.12)
        
        adj_4 = parser.get_user_adjustments('u4')
        self.assertTrue(adj_4['salary_ended'])

    # 5. Six-Tier Ranking Dominance
    def test_six_tier_ranking_dominance(self):
        # Tier 1 beats Tier 2: Plan completing by deadline beats plan needing no spending changes that misses deadline
        p1 = CandidatePlan(method='full_payment', status='affordable_with_plan', plan_str='...', total_amount=1000,
                           first_date='2025-01-01', num_payments=1, option_id='opt1', spending_changes='stop:e1', completes_by_deadline=True)
        p2 = CandidatePlan(method='wait', status='affordable_later', plan_str='...', total_amount=1000,
                           first_date='2025-02-01', num_payments=1, option_id='opt2', spending_changes='none', completes_by_deadline=False)
        self.assertEqual(PlanRanker.rank_candidates([p1, p2]).method, 'full_payment')

        # Tier 2 beats Tier 3: No spending changes beats cheaper plan that requires spending changes (both on time)
        p3 = CandidatePlan(method='full_payment', status='affordable_now', plan_str='...', total_amount=1000,
                           first_date='2025-01-01', num_payments=1, option_id='opt1', spending_changes='none', completes_by_deadline=True)
        p4 = CandidatePlan(method='full_payment', status='affordable_with_plan', plan_str='...', total_amount=800,
                           first_date='2025-01-01', num_payments=1, option_id='opt2', spending_changes='stop:e1', completes_by_deadline=True)
        self.assertEqual(PlanRanker.rank_candidates([p3, p4]).spending_changes, 'none')

        # Tier 3: Cheaper plan beats more expensive plan (all else equal)
        p5 = CandidatePlan(method='installments', status='affordable_with_plan', plan_str='...', total_amount=1050,
                           first_date='2025-01-01', num_payments=3, option_id='opt1', spending_changes='none', completes_by_deadline=True)
        p6 = CandidatePlan(method='installments', status='affordable_with_plan', plan_str='...', total_amount=1000,
                           first_date='2025-01-01', num_payments=3, option_id='opt2', spending_changes='none', completes_by_deadline=True)
        self.assertEqual(PlanRanker.rank_candidates([p5, p6]).total_amount, 1000)

        # Tier 4: Earlier start date wins
        p7 = CandidatePlan(method='wait', status='affordable_later', plan_str='...', total_amount=1000,
                           first_date='2025-01-15', num_payments=1, option_id='opt1', spending_changes='none', completes_by_deadline=True)
        p8 = CandidatePlan(method='wait', status='affordable_later', plan_str='...', total_amount=1000,
                           first_date='2025-01-20', num_payments=1, option_id='opt2', spending_changes='none', completes_by_deadline=True)
        self.assertEqual(PlanRanker.rank_candidates([p7, p8]).first_date, '2025-01-15')

        # Tier 5: Fewer payments wins
        p9 = CandidatePlan(method='full_payment', status='affordable_now', plan_str='...', total_amount=1000,
                           first_date='2025-01-01', num_payments=1, option_id='opt2', spending_changes='none', completes_by_deadline=True)
        p10 = CandidatePlan(method='installments', status='affordable_with_plan', plan_str='...', total_amount=1000,
                            first_date='2025-01-01', num_payments=3, option_id='opt1', spending_changes='none', completes_by_deadline=True)
        self.assertEqual(PlanRanker.rank_candidates([p9, p10]).num_payments, 1)

    # 6. Simulator and Minimum Balance Invariant
    def test_simulator_minimum_balance(self):
        sim = FinancialSimulator(forecast_days=90)
        start_bal = 1000.0
        min_bal = 200.0
        req_amt = 500.0
        
        # Test 1: Daily deltas zero -> amount safe to pay is 800 (capped at req_amt 500)
        daily_deltas = {pd.to_datetime('2025-01-01') + timedelta(days=i): 0.0 for i in range(91)}
        safe = sim.calculate_amount_safe_to_pay(start_bal, min_bal, req_amt, daily_deltas)
        self.assertEqual(safe, 500.0)
        
        # Test 2: Large debit on day 10 of 700 -> min balance is 300 -> safe = 300 - 200 = 100
        daily_deltas[pd.to_datetime('2025-01-11')] = -700.0
        safe_dip = sim.calculate_amount_safe_to_pay(start_bal, min_bal, req_amt, daily_deltas)
        self.assertEqual(safe_dip, 100.0)
        
        # Test 3: Debit causes balance to reach exactly min_bal -> safe = 0
        daily_deltas[pd.to_datetime('2025-01-11')] = -800.0
        safe_zero = sim.calculate_amount_safe_to_pay(start_bal, min_bal, req_amt, daily_deltas)
        self.assertEqual(safe_zero, 0.0)

    # 7. Semantic Validator
    def test_validator_catches_semantic_contradictions(self):
        df_req = pd.DataFrame([{
            'request_id': 'req_01', 'requested_amount': 500.0, 'request_date': '2025-01-01', 'allows_partial_payment': False
        }])
        
        # Inconsistent status and method
        df_invalid = pd.DataFrame([{
            'request_id': 'req_01',
            'amount_safe_to_pay': 500.0,
            'affordability_status': 'affordable_now',
            'recommended_payment_method': 'wait',  # Contradiction!
            'payment_plan': '2025-01-01:500',
            'earliest_date_for_full_payment': '2025-01-01',
            'spending_changes_needed': 'none',
            'decision_explanation': 'Valid explanation text.'
        }])
        errs = validate_output_dataframe(df_invalid, df_req)
        self.assertTrue(any('status is affordable_now but method is wait' in e for e in errs))

    # 8. Non-recurring income & recurring salary projections
    def test_recurring_income_not_from_one_off_credit(self):
        # Verify that one-off credits (e.g. gift, refund) do not get projected as recurring income
        req_date = pd.to_datetime('2025-06-01')
        df_events = pd.DataFrame([
            {'event_id': 'e1', 'user_id': 'u_test', 'event_type': 'income', 'category': 'gift',
             'direction': 'credit', 'amount': 50000.0, 'currency': 'USD', 'event_date': '2025-05-15',
             'settlement_date': pd.to_datetime('2025-05-15'), 'status': 'settled', 'flexibility': 'fixed',
             'minimum_allowed_amount': np.nan, 'description': 'Birthday gift'}
        ])
        parser = MessageParser(pd.DataFrame([]))
        cfr = CashFlowReconstructor(df_events, self.fx, parser)
        daily_deltas, _, _, _ = cfr.get_user_cash_schedule('u_test', '2025-06-01', 'USD')
        # All future days should have zero credit deltas from the one-off gift
        self.assertTrue(all(delta <= 0.0 for delta in daily_deltas.values()))

    # 9. Earliest Full Payment Date Boundaries
    def test_earliest_full_payment_boundaries(self):
        sim = FinancialSimulator(forecast_days=90)
        start_bal = 1000.0
        min_bal = 500.0
        req_amt = 800.0
        req_date = pd.to_datetime('2025-01-01')
        
        # Test 1: Day 0 safe immediately if start_bal - min_bal >= req_amt
        daily_deltas_safe = {req_date + timedelta(days=i): 0.0 for i in range(91)}
        earliest_immediate = sim.find_earliest_date_for_full_payment(1500.0, min_bal, req_amt, daily_deltas_safe, req_date)
        self.assertEqual(earliest_immediate, '2025-01-01')

        # Test 2: Inflow arrives on day 30, making it safe from day 30 onwards
        daily_deltas = {req_date + timedelta(days=i): 0.0 for i in range(91)}
        daily_deltas[req_date + timedelta(days=30)] = 1000.0
        earliest_day30 = sim.find_earliest_date_for_full_payment(start_bal, min_bal, req_amt, daily_deltas, req_date)
        self.assertEqual(earliest_day30, '2025-01-31')

        # Test 3: Large late obligation on day 89 violates min balance -> cannot pay on day 30
        daily_deltas[req_date + timedelta(days=89)] = -1500.0
        earliest_blocked = sim.find_earliest_date_for_full_payment(start_bal, min_bal, req_amt, daily_deltas, req_date)
        self.assertIsNone(earliest_blocked)

    # 10. Multi-stream salary continuation after partial household termination
    def test_multi_stream_salary_continuation(self):
        df_msgs = pd.DataFrame([
            {'user_id': 'u_multi', 'message_text': 'A quick update. One household employment record has ended. The remaining confirmed monthly salary is INR 148000.'}
        ])
        parser = MessageParser(df_msgs)
        adj = parser.get_user_adjustments('u_multi')
        self.assertFalse(adj['salary_ended'])
        self.assertEqual(adj['salary_override'], 148000.0)

        # Test CashFlowReconstructor projects the continuing stream
        df_events = pd.DataFrame([
            {'event_id': 'e1', 'user_id': 'u_multi', 'event_type': 'income', 'category': 'salary',
             'direction': 'credit', 'amount': 91760.0, 'currency': 'INR', 'event_date': '2025-12-15',
             'settlement_date': pd.to_datetime('2025-12-15'), 'status': 'settled', 'flexibility': 'fixed',
             'minimum_allowed_amount': np.nan, 'description': 'Primary household salary'}
        ])
        cfr = CashFlowReconstructor(df_events, self.fx, parser)
        daily_deltas, _, _, _ = cfr.get_user_cash_schedule('u_multi', '2026-01-05', 'INR')
        # Continuing salary should be credited in January at the override amount
        jan_payday = pd.to_datetime('2026-01-15')
        self.assertIn(jan_payday, daily_deltas)
        self.assertEqual(daily_deltas[jan_payday], 148000.0)

    # 11. Rent increase applied to explicit future debits and recurring rent
    def test_rent_increase_on_explicit_and_recurring(self):
        df_msgs = pd.DataFrame([
            {'user_id': 'u_rent', 'message_text': 'The renewed lease increases monthly rent by 12%.'}
        ])
        parser = MessageParser(df_msgs)
        
        # Test explicit scheduled rent event
        df_events = pd.DataFrame([
            {'event_id': 'e_rent_fut', 'user_id': 'u_rent', 'event_type': 'expense', 'category': 'rent',
             'direction': 'debit', 'amount': 1000.0, 'currency': 'USD', 'event_date': '2025-06-01',
             'settlement_date': pd.to_datetime('2025-06-01'), 'status': 'scheduled', 'flexibility': 'fixed',
             'minimum_allowed_amount': np.nan, 'description': 'Apartment rent transfer'}
        ])
        cfr = CashFlowReconstructor(df_events, self.fx, parser)
        daily_deltas, _, _, _ = cfr.get_user_cash_schedule('u_rent', '2025-05-15', 'USD')
        # Explicit future rent must reflect 12% increase -> -1120.0
        self.assertEqual(daily_deltas[pd.to_datetime('2025-06-01')], -1120.0)

    # 12. Independent Plan Safety Validator
    def test_plan_safety_validation(self):
        from utils.validator import validate_plan_safety
        start_bal = 1000.0
        min_bal = 500.0
        req_date = pd.to_datetime('2025-01-01')
        daily_deltas = {req_date + timedelta(days=i): 0.0 for i in range(91)}
        
        # Safe plan: paying 400 when start_bal=1000, min_bal=500
        self.assertTrue(validate_plan_safety(start_bal, min_bal, daily_deltas, '2025-01-01:400', 'none', []))
        
        # Unsafe plan: paying 600 brings closing bal to 400 < 500
        self.assertFalse(validate_plan_safety(start_bal, min_bal, daily_deltas, '2025-01-01:600', 'none', []))

    # 13. Earliest Safe Date for Remainder Amount
    def test_earliest_safe_date_for_amount(self):
        sim = FinancialSimulator(forecast_days=90)
        start_bal = 1000.0
        min_bal = 500.0
        req_date = pd.to_datetime('2025-01-01')
        daily_deltas = {req_date + timedelta(days=i): 0.0 for i in range(91)}
        daily_deltas[req_date + timedelta(days=15)] = 500.0
        
        # Test finding earliest safe date for remainder of 600
        rem_date = sim.find_earliest_safe_date_for_amount(
            starting_balance=500.0,
            min_balance=min_bal,
            amount=400.0,
            daily_deltas=daily_deltas,
            req_date=req_date,
            start_from_date=req_date + timedelta(days=1)
        )
        self.assertEqual(rem_date, '2025-01-16')

if __name__ == '__main__':
    unittest.main()
