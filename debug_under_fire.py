#!/usr/bin/env python3
"""
Debug script to trace Under Fire function calls and detect legacy code issues
"""

import pandas as pd
import sys
sys.path.append('.')
from vertical_analysis import assign_under_fire_modifier

# Test cases that should return "Takedown"
test_cases = [
    {"prom": 3.0, "sent": -2.0, "outlet": 4, "expected": "Takedown"},
    {"prom": 3.5, "sent": -2.5, "outlet": 4, "expected": "Takedown"},
    {"prom": 4.0, "sent": -2.0, "outlet": 4, "expected": "Takedown"},
]

print("=== UNDER FIRE FUNCTION DEBUG ===")
print()

for i, case in enumerate(test_cases):
    print(f"Test {i+1}: prom={case['prom']}, sent={case['sent']}, outlet={case['outlet']}")
    result = assign_under_fire_modifier(case['prom'], case['sent'], case['outlet'])
    status = "✅ PASS" if result == case['expected'] else "❌ FAIL"
    print(f"  Expected: {case['expected']}")
    print(f"  Got: {result}")
    print(f"  Status: {status}")
    print()

# Now check CSV data
print("=== CSV DATA VERIFICATION ===")
try:
    df = pd.read_csv('Pass1_Veritical_Analysis_tmpxjpi8tby_input.csv')
    
    # Find BetMGM Under Fire cases with outlet=4
    problem_cases = []
    for idx, row in df.iterrows():
        outlet = row.get('Outlet score', 0)
        if outlet == 4:
            state = row.get('Entity_BetMGM_State', '')
            modifier = row.get('Entity_BetMGM_Modifier', '')
            prom = row.get('Entity_BetMGM_Prominence', 0)
            sent = row.get('Entity_BetMGM_Sentiment_Normalized', 0)
            
            if state == 'Under Fire' and prom >= 3.0 and sent <= -2.0:
                expected = assign_under_fire_modifier(float(prom), float(sent), float(outlet))
                if modifier != expected:
                    problem_cases.append({
                        'row': idx,
                        'prom': prom,
                        'sent': sent,
                        'outlet': outlet,
                        'csv_modifier': modifier,
                        'function_result': expected
                    })
    
    if problem_cases:
        print(f"Found {len(problem_cases)} discrepancies between CSV and function:")
        for case in problem_cases[:3]:  # Show first 3
            print(f"  Row {case['row']}: CSV='{case['csv_modifier']}', Function='{case['function_result']}'")
            print(f"    Input: prom={case['prom']}, sent={case['sent']}, outlet={case['outlet']}")
        
        print("\n🚨 DIAGNOSIS: CSV was generated with different code than current function!")
        print("   This proves there's a legacy code path still being used.")
    else:
        print("✅ No discrepancies found - CSV matches current function")
        
except FileNotFoundError:
    print("❌ CSV file not found")
except Exception as e:
    print(f"❌ Error reading CSV: {e}")
