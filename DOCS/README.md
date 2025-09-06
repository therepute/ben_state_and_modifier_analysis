# Off-Stage Modifier Over-Assignment Analysis

## 🎯 **Root Cause Hypothesis**

**Issue**: System over-assigning "Competitor-Led" and "Innocent Bystander" instead of "Overlooked"

**Suspected Cause**: Non-canonical fallback logic in `assign_off_stage_modifier()` function

## 📋 **Key Finding**

Our implementation includes fallback logic that **does not exist in the canonical specification**:

```python
# Current non-canonical fallbacks (lines 476-479)
if narr_sent >= 0.0:
    return "Missed Opportunity"  # ❌ NOT IN CANONICAL SPEC
else:
    return "Reporter-Led Risk"   # ❌ NOT IN CANONICAL SPEC
```

**The canonical spec defines exactly 6 conditions - no fallbacks.** These extra conditions are assigning modifiers to cases that should either get no modifier or fail gracefully.

## 📊 **Logic Verification**

Traced all combinations of `(Narr_Prom, Narr_Sent, Peer_Count)` against canonical spec:

| Scenario | Canonical Expected | Current Result | Status |
|----------|-------------------|----------------|---------|
| High prom + positive + peers | Competitor-Led | ✅ Correct | Working |
| High prom + positive + no peers | Missed Opportunity | ✅ Correct | Working |
| Low prom + any sentiment + no peers | Overlooked | ✅ Correct | Working |
| **Data quality issues** | Should fail gracefully | ❌ **Wrong fallbacks** | **Problem** |

## 💡 **Proposed Solution**

1. **Remove dangerous fallbacks** that mask logic errors
2. **Add input validation** for NaN/null values
3. **Return empty string** for unmatched cases to surface issues
4. **Move "Overlooked" check first** (matches canonical precedence)

```python
def assign_off_stage_modifier(narr_prom: float, narr_sent: float, peers: int) -> str:
    # Validate inputs first
    if any(x is None or str(x) == 'nan' for x in [narr_prom, narr_sent, peers]):
        return ""
    
    # Overlooked (any sentiment) - check first
    if narr_prom < 2.5 and peers == 0:
        return "Overlooked"
    
    # Then sentiment-based logic
    if narr_sent >= 0.0:
        if peers >= 1: return "Competitor-Led"
        if narr_prom >= 2.5 and peers == 0: return "Missed Opportunity"
    else:
        if peers >= 2: return "Guilt by Association"
        if peers == 1: return "Innocent Bystander"
        if narr_prom >= 2.5 and peers == 0: return "Reporter-Led Risk"
    
    # No fallback - surface logic gaps
    return ""
```

## 🔧 **Next Steps**

1. Implement the fix above
2. Test with current dataset to verify reduction in over-assignment
3. Monitor for any empty modifier results (indicates new edge cases)

**Expected Outcome**: Significant reduction in false "Competitor-Led" and "Innocent Bystander" assignments, with proper "Overlooked" classification for weak narratives.