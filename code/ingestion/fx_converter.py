import pandas as pd
from typing import Dict, Tuple, Optional
from collections import defaultdict, deque

class FXConverter:
    '''
    Robust, dated multi-currency converter with graph-based routing (e.g. via USD/EUR).
    Strictly forbids silent 1:1 fallback on cross-currency conversions.
    '''
    def __init__(self, fx_df: pd.DataFrame):
        self.df = fx_df.copy()
        self.df['rate_date'] = pd.to_datetime(self.df['rate_date'])
        
        self.dates = sorted(self.df['rate_date'].unique())
        self.graph_by_date = {}
        
        for d in self.dates:
            g = defaultdict(dict)
            sub = self.df[self.df['rate_date'] == d]
            for _, r in sub.iterrows():
                fc = str(r['from_currency']).strip()
                tc = str(r['to_currency']).strip()
                rate = float(r['rate'])
                if rate > 0:
                    g[fc][tc] = rate
                    g[tc][fc] = 1.0 / rate
            self.graph_by_date[d] = g
            
    def _find_rate_on_date(self, g: dict, from_curr: str, to_curr: str) -> Optional[float]:
        if from_curr == to_curr:
            return 1.0
        if to_curr in g.get(from_curr, {}):
            return g[from_curr][to_curr]
            
        # BFS path finding through intermediary currencies
        queue = deque([(from_curr, 1.0)])
        visited = {from_curr}
        
        while queue:
            curr, cum_rate = queue.popleft()
            for neighbor, edge_rate in g.get(curr, {}).items():
                if neighbor == to_curr:
                    return cum_rate * edge_rate
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, cum_rate * edge_rate))
                    
        return None

    def get_rate(self, from_curr: str, to_curr: str, date_str: str) -> float:
        from_curr = str(from_curr).strip()
        to_curr = str(to_curr).strip()
        if from_curr == to_curr:
            return 1.0
            
        target_date = pd.to_datetime(date_str)
        # Financial as-of rate: latest available rate on or before transaction date
        past_dates = [d for d in self.dates if d <= target_date]
        chosen_date = past_dates[-1] if past_dates else self.dates[0]
        
        rate = self._find_rate_on_date(self.graph_by_date[chosen_date], from_curr, to_curr)
        if rate is not None:
            return rate
            
        # Search nearest dated rate table if chosen table had missing currency nodes
        sorted_by_dist = sorted(self.dates, key=lambda d: abs(d - target_date))
        for d in sorted_by_dist:
            rate = self._find_rate_on_date(self.graph_by_date[d], from_curr, to_curr)
            if rate is not None:
                return rate
                
        raise ValueError(f"CRITICAL: No FX conversion path found between {from_curr} and {to_curr} for date {date_str}. Cannot silently default to 1:1.")

    def convert(self, amount: float, from_curr: str, to_curr: str, date_str: str) -> float:
        if amount == 0 or pd.isna(amount):
            return 0.0
        from_curr = str(from_curr).strip()
        to_curr = str(to_curr).strip()
        if from_curr == to_curr:
            return float(amount)
            
        rate = self.get_rate(from_curr, to_curr, date_str)
        return float(amount * rate)
