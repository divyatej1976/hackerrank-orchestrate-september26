import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any

class CashFlowReconstructor:
    def __init__(self, events_df: pd.DataFrame, fx_converter, message_parser):
        self.events_df = events_df
        self.fx = fx_converter
        self.msg_parser = message_parser
        
    def get_user_cash_schedule(self, user_id: str, req_date_str: str, home_currency: str) -> Tuple[Dict[pd.Timestamp, float], List[Dict[str, Any]], Dict[str, Any]]:
        req_date = pd.to_datetime(req_date_str)
        end_date = req_date + timedelta(days=90)
        
        u_events = self.events_df[self.events_df['user_id'] == user_id].copy()
        u_events['event_date'] = pd.to_datetime(u_events['event_date'])
        u_events['settlement_date'] = pd.to_datetime(u_events['settlement_date'])
        
        adjustments = self.msg_parser.get_user_adjustments(user_id)
        
        # Convert amounts to home currency
        u_events['norm_amount'] = u_events.apply(
            lambda r: self.fx.convert(r['amount'], r['currency'], home_currency, str(r['settlement_date'])[:10]),
            axis=1
        )
        
        daily_deltas = {req_date + timedelta(days=i): 0.0 for i in range(91)}
        
        # 1. Explicit future events in CSV
        future_events = u_events[(u_events['settlement_date'] >= req_date) & (u_events['settlement_date'] <= end_date)]
        for _, ev in future_events.iterrows():
            st = ev['status']
            dir_ = ev['direction']
            amt = ev['norm_amount']
            s_date = ev['settlement_date']
            ev_id = ev['event_id']
            
            if ev_id in adjustments['ignore_events']:
                continue
            if st in ['cancelled', 'unrealized'] or dir_ == 'non_cash':
                continue
                
            if dir_ == 'credit':
                if st == 'scheduled' and ev['category'] == 'salary':
                    if adjustments['salary_override']:
                        amt = adjustments['salary_override']
                    daily_deltas[s_date] += amt
            elif dir_ == 'debit':
                if st in ['pending', 'scheduled']:
                    daily_deltas[s_date] -= amt
                    
        # Check for failed debits that remain open
        recent_failed = u_events[(u_events['status'] == 'failed') & (u_events['direction'] == 'debit')]
        for _, ev in recent_failed.iterrows():
            if abs((ev['settlement_date'] - req_date).days) <= 10:
                daily_deltas[req_date] -= ev['norm_amount']
                
        # 2. Extract recurring events from past history
        past_events = u_events[u_events['settlement_date'] < req_date].copy()
        past_debits = past_events[(past_events['direction'] == 'debit') & (past_events['status'] == 'settled')]
        
        flexible_expenses = []
        for (desc, cat), grp in past_debits.groupby(['description', 'category']):
            last_ev = grp.iloc[-1]
            flex = str(last_ev['flexibility'])
            min_amt = last_ev['minimum_allowed_amount']
            if pd.notna(min_amt):
                min_amt = float(min_amt)
            else:
                min_amt = None
                
            if flex in ['stoppable', 'reducible', 'reducible_or_stoppable']:
                flexible_expenses.append({
                    'event_id': last_ev['event_id'],
                    'description': desc,
                    'category': cat,
                    'flexibility': flex,
                    'amount': last_ev['norm_amount'],
                    'minimum_allowed_amount': min_amt,
                    'last_date': grp['settlement_date'].max()
                })
                
        # Project monthly bills and periodic recurring expenses
        for (desc, cat), grp in past_debits.groupby(['description', 'category']):
            if cat in ['investment']:
                continue
            dates = grp['settlement_date'].sort_values().tolist()
            last_date = dates[-1]
            last_amt = grp['norm_amount'].iloc[-1]
            
            if cat == 'rent' and adjustments['rent_increase_pct'] > 0:
                last_amt *= (1.0 + adjustments['rent_increase_pct'])
                
            if len(dates) >= 2:
                diffs = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
                median_diff = int(np.median(diffs))
                
                # Monthly bills
                if 27 <= median_diff <= 32:
                    dom = last_date.day
                    curr = last_date
                    while True:
                        m = curr.month + 1
                        y = curr.year
                        if m > 12:
                            m = 1
                            y += 1
                        import calendar
                        max_d = calendar.monthrange(y, m)[1]
                        d = min(dom, max_d)
                        curr = pd.to_datetime(f'{y:04d}-{m:02d}-{d:02d}')
                        if curr > end_date:
                            break
                        if curr >= req_date:
                            daily_deltas[curr] -= last_amt
                # Periodic essentials (e.g. weekly/biweekly)
                elif 5 <= median_diff <= 25 and len(diffs) >= 3:
                    # Project with cadence
                    curr = last_date + timedelta(days=median_diff)
                    while curr <= end_date:
                        if curr >= req_date:
                            daily_deltas[curr] -= last_amt
                        curr += timedelta(days=median_diff)
                            
        # Project future monthly salaries if recurring and employment has not ended
        past_salaries = past_events[(past_events['direction'] == 'credit') & (past_events['category'] == 'salary') & (past_events['status'] == 'settled')]
        last_sal_desc = str(past_salaries.iloc[-1]['description']).lower() if len(past_salaries) > 0 else ''
        
        has_future_scheduled_salary = len(future_events[(future_events['category'] == 'salary') & (future_events['status'] == 'scheduled')]) > 0
        salary_ended = ('final' in last_sal_desc) or ('seasonal contract has ended' in str(adjustments))
        
        if (len(past_salaries) >= 1 or has_future_scheduled_salary) and not salary_ended:
            if has_future_scheduled_salary:
                sched_sal = future_events[(future_events['category'] == 'salary') & (future_events['status'] == 'scheduled')].iloc[0]
                base_sal_date = sched_sal['settlement_date']
                base_sal_amt = sched_sal['norm_amount']
            else:
                base_sal_date = past_salaries['settlement_date'].max()
                base_sal_amt = past_salaries['norm_amount'].iloc[-1]
                
            if adjustments['salary_override']:
                base_sal_amt = adjustments['salary_override']
                
            dom = base_sal_date.day
            curr = base_sal_date
            while True:
                m = curr.month + 1
                y = curr.year
                if m > 12:
                    m = 1
                    y += 1
                import calendar
                max_d = calendar.monthrange(y, m)[1]
                d = min(dom, max_d)
                curr = pd.to_datetime(f'{y:04d}-{m:02d}-{d:02d}')
                if curr > end_date:
                    break
                if curr >= req_date and curr not in future_events[future_events['category'] == 'salary']['settlement_date'].values:
                    daily_deltas[curr] += base_sal_amt
                    
        return daily_deltas, flexible_expenses, adjustments
