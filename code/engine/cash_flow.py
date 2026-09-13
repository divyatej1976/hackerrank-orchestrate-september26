import calendar
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional

def generate_monthly_dates(start_date: pd.Timestamp, anchor_dom: int, end_date: pd.Timestamp) -> List[pd.Timestamp]:
    '''
    Generates monthly recurrence dates respecting varying month lengths (28, 29, 30, 31 days).
    Always anchors to anchor_dom (e.g. 31st becomes Feb 28/29, Apr 30, May 31).
    '''
    dates = []
    y = start_date.year
    m = start_date.month
    
    while True:
        max_d = calendar.monthrange(y, m)[1]
        d = min(anchor_dom, max_d)
        curr = pd.to_datetime(f'{y:04d}-{m:02d}-{d:02d}')
        if curr > end_date:
            break
        if curr >= start_date:
            dates.append(curr)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return dates

class CashFlowReconstructor:
    def __init__(self, events_df: pd.DataFrame, fx_converter, message_parser):
        self.events_df = events_df
        self.fx = fx_converter
        self.msg_parser = message_parser
        
    def get_user_cash_schedule(
        self,
        user_id: str,
        req_date_str: str,
        home_currency: str,
        forecast_days: int = 90
    ) -> Tuple[Dict[pd.Timestamp, float], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        '''
        Reconstructs cash schedule for user_id starting from req_date.
        Returns:
        - daily_deltas: baseline net cash delta per date
        - flexible_occurrences: list of individual future flexible debit occurrences:
          [{'date': Timestamp, 'event_id': str, 'category': str, 'amount': float, 'min_allowed': float|None, 'flexibility': str}]
        - flexible_catalog: unique list of flexible expenses available for user
        - adjustments: dictionary of message adjustments
        '''
        req_date = pd.to_datetime(req_date_str)
        end_date = req_date + timedelta(days=forecast_days)
        
        u_events = self.events_df[self.events_df['user_id'] == user_id].copy()
        u_events['event_date'] = pd.to_datetime(u_events['event_date'])
        u_events['settlement_date'] = pd.to_datetime(u_events['settlement_date'])
        
        adjustments = self.msg_parser.get_user_adjustments(user_id)
        
        # Convert amounts to home currency using dated FX rates
        u_events['norm_amount'] = u_events.apply(
            lambda r: self.fx.convert(r['amount'], r['currency'], home_currency, str(r['settlement_date'])[:10]),
            axis=1
        )
        
        # Initialize daily timeline covering request_date through end_date (all discrete days)
        total_days = (end_date - req_date).days + 1
        daily_deltas = {req_date + timedelta(days=i): 0.0 for i in range(total_days)}
        
        # 1. Explicit future events in CSV
        future_events = u_events[(u_events['settlement_date'] >= req_date) & (u_events['settlement_date'] <= end_date)]
        for _, ev in future_events.iterrows():
            st = ev['status']
            dir_ = ev['direction']
            amt = float(ev['norm_amount'])
            s_date = ev['settlement_date']
            ev_id = ev['event_id']
            
            if ev_id in adjustments.get('ignore_events', set()):
                continue
            if st in ['cancelled', 'unrealized'] or dir_ == 'non_cash':
                continue
                
            if dir_ == 'credit':
                # Only confirmed scheduled salary
                if st == 'scheduled' and ev['category'] == 'salary':
                    eff_date = adjustments.get('salary_effective_date')
                    eff_dt = pd.to_datetime(eff_date) if eff_date else None
                    if adjustments.get('salary_override') and (eff_dt is None or s_date >= eff_dt):
                        amt = adjustments['salary_override']
                    daily_deltas[s_date] += amt
            elif dir_ == 'debit':
                if st in ['pending', 'scheduled']:
                    daily_deltas[s_date] -= amt
                    
        # 2. Extract recurring events from past history
        past_events = u_events[u_events['settlement_date'] < req_date].copy()
        past_debits = past_events[(past_events['direction'] == 'debit') & (past_events['status'] == 'settled')]
        
        flexible_catalog = []
        flexible_occurrences = []
        
        for (desc, cat), grp in past_debits.groupby(['description', 'category']):
            last_ev = grp.iloc[-1]
            flex = str(last_ev['flexibility']).strip()
            min_amt = last_ev['minimum_allowed_amount']
            min_amt = float(min_amt) if pd.notna(min_amt) else None
            is_flex = flex in ['stoppable', 'reducible', 'reducible_or_stoppable']
            
            dates = grp['settlement_date'].sort_values().tolist()
            last_date = dates[-1]
            last_amt = float(grp['norm_amount'].iloc[-1])
            ev_id = last_ev['event_id']
            days_since = (req_date - last_date).days
            
            if cat == 'rent' and adjustments.get('rent_increase_pct', 0.0) > 0:
                last_amt *= (1.0 + adjustments['rent_increase_pct'])
                
            if is_flex:
                flexible_catalog.append({
                    'event_id': ev_id,
                    'description': desc,
                    'category': cat,
                    'flexibility': flex,
                    'amount': last_amt,
                    'minimum_allowed_amount': min_amt,
                    'last_date': last_date
                })
                
            # Project recurring debits with calendar math
            if len(dates) >= 2:
                diffs = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
                median_diff = int(np.median(diffs))
                
                # Active monthly recurring bills (27 to 32 day cadence, must be recent within 45 days)
                if 27 <= median_diff <= 32 and days_since <= 45:
                    anchor_dom = last_date.day
                    projected_dates = generate_monthly_dates(req_date, anchor_dom, end_date)
                    for p_date in projected_dates:
                        if p_date in daily_deltas:
                            daily_deltas[p_date] -= last_amt
                        if is_flex:
                            flexible_occurrences.append({
                                'date': p_date,
                                'event_id': ev_id,
                                'category': cat,
                                'amount': last_amt,
                                'min_allowed': min_amt,
                                'flexibility': flex
                            })
                # Active shorter cadence recurring essentials (within 2*median_diff + 2 days)
                elif 5 <= median_diff <= 25 and len(diffs) >= 3 and days_since <= (median_diff * 2 + 2):
                    curr = last_date + timedelta(days=median_diff)
                    while curr <= end_date:
                        if curr >= req_date:
                            if curr in daily_deltas:
                                daily_deltas[curr] -= last_amt
                            if is_flex:
                                flexible_occurrences.append({
                                    'date': curr,
                                    'event_id': ev_id,
                                    'category': cat,
                                    'amount': last_amt,
                                    'min_allowed': min_amt,
                                    'flexibility': flex
                                })
                        curr += timedelta(days=median_diff)
                        
        # 3. Project future monthly salaries if recurring and employment has not ended
        past_salaries = past_events[(past_events['direction'] == 'credit') & (past_events['category'] == 'salary') & (past_events['status'] == 'settled')]
        last_sal_desc = str(past_salaries.iloc[-1]['description']).lower() if len(past_salaries) > 0 else ''
        
        future_sched_salaries = future_events[(future_events['category'] == 'salary') & (future_events['status'] == 'scheduled')]
        has_future_scheduled_salary = len(future_sched_salaries) > 0
        
        salary_ended = adjustments.get('salary_ended', False) or ('final' in last_sal_desc)
        
        if (len(past_salaries) >= 1 or has_future_scheduled_salary) and not salary_ended:
            if has_future_scheduled_salary:
                sched_sal = future_sched_salaries.iloc[0]
                base_sal_date = sched_sal['settlement_date']
                base_sal_amt = float(sched_sal['norm_amount'])
            else:
                base_sal_date = past_salaries['settlement_date'].max()
                base_sal_amt = float(past_salaries['norm_amount'].iloc[-1])
                
            eff_date = adjustments.get('salary_effective_date')
            eff_dt = pd.to_datetime(eff_date) if eff_date else None
            override_amt = adjustments.get('salary_override')
            
            anchor_dom = base_sal_date.day
            projected_salary_dates = generate_monthly_dates(req_date, anchor_dom, end_date)
            
            for p_date in projected_salary_dates:
                # Avoid duplicating explicit future scheduled salary
                if p_date in future_sched_salaries['settlement_date'].values:
                    continue
                cur_sal = base_sal_amt
                if override_amt and (eff_dt is None or p_date >= eff_dt):
                    cur_sal = override_amt
                if p_date in daily_deltas:
                    daily_deltas[p_date] += cur_sal
                    
        return daily_deltas, flexible_occurrences, flexible_catalog, adjustments
