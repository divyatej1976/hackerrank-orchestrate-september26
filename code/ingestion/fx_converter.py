import pandas as pd
from typing import Dict, Tuple

class FXConverter:
    def __init__(self, fx_df: pd.DataFrame):
        self.rates: Dict[Tuple[str, str, str], float] = {}
        for _, row in fx_df.iterrows():
            d = str(row['rate_date'])
            fc = str(row['from_currency'])
            tc = str(row['to_currency'])
            r = float(row['rate'])
            self.rates[(d, fc, tc)] = r
            if (d, tc, fc) not in self.rates and r > 0:
                self.rates[(d, tc, fc)] = 1.0 / r
                
    def convert(self, amount: float, from_curr: str, to_curr: str, date_str: str) -> float:
        if from_curr == to_curr or amount == 0:
            return amount
            
        key = (date_str, from_curr, to_curr)
        if key in self.rates:
            return amount * self.rates[key]
            
        # Find closest date for the currency pair
        matching = [k for k in self.rates if k[1] == from_curr and k[2] == to_curr]
        if matching:
            closest_key = min(matching, key=lambda k: abs(pd.to_datetime(k[0]) - pd.to_datetime(date_str)))
            return amount * self.rates[closest_key]
            
        return amount
