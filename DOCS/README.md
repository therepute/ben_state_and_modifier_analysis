# Pass 1 Audit Findings - Critical Issues Analysis

## 🎯 **Executive Summary**

Ben's hard audit identified **3 critical issues** requiring immediate fixes:

1. **State Trigger Violations**: 161 rows with impossible state assignments (Bet365)
2. **Under Fire Tiering Mismatches**: 15 cases with incorrect modifier precedence 
3. **Missing Output Columns**: Orchestra format entities lack state/modifier columns

**Good News**: ✅ Off-Stage modifier logic fixed, ✅ No non-canonical labels, ✅ Supporting/Leader thresholds working

---

## 🚨 **ISSUE 1: State Trigger Violations (161 cases)**

### **Problem**
Bet365 rows showing states like "Under Fire", "Leader", "Supporting Player" when `Prominence = 0` or `Sentiment = NaN`.

**Canonical Rule**: `Prominence = 0` → only "Absent" or "Off-Stage" allowed

### **Root Cause** 
Input CSV contains **pre-existing contaminated state values** that violate canonical triggers:
- 727 rows with `Prom = 0` but `State = "Offstage"` (note: should be "Off-Stage")
- System may be preserving these bad existing states instead of recalculating

### **Evidence**
```
Sample violations:
    1_Bet365 - Company-Level Prominence    1_C_State
0                                   0.0     Offstage
15                                  0.0     Offstage
20                                  0.0     Offstage
```

### **Fix Required**
1. **Force recalculation** of all states (ignore pre-existing `1_C_State` values)
2. **Add hard guardrails**: If `Prom = 0` or `Sent = NaN`, only assign "Absent"/"Off-Stage"
3. **Standardize naming**: "Offstage" → "Off-Stage"

---

## 🎯 **ISSUE 2: Under Fire & Leader Modifier Logic Errors**

### **Under Fire Tiering (15 mismatches)**

**Problem**: Wrong modifier assignments due to incorrect canonical implementation

| Modifier | **Canonical Trigger** | **Current Code** | **Status** |
|----------|----------------------|------------------|------------|
| **Narrative Shaper** | `Prom ≥ 3; Sent ≤ -2.0; Outlet = 5 + headline` | `Prom ≥ 4; Sent ≤ -3.0; Outlet = 5` | ❌ **Wrong thresholds** |
| **Takedown** | `Prom ≥ 3; Sent ≤ -2.0; Outlet = 5` | `Prom ≥ 4; Sent ≤ -3.0; Outlet = 4` | ❌ **All wrong** |
| **Body Blow** | `Prom ≥ 3; Sent ≤ -2.0; Outlet > 2 (not 5)` | `Prom ≥ 3; Sent ≤ -2.0; Outlet > 2 not [4,5]` | ⚠️ **Logic gap** |

**Key Errors**:
- Takedown outlet should be `= 5`, not `= 4`
- Prominence thresholds should be `≥ 3`, not `≥ 4`  
- Sentiment thresholds should be `≤ -2.0`, not `≤ -3.0`

### **Leader Modifier Logic (3 bugs)**

| Modifier | **Issue** |
|----------|-----------|
| **Good Story** | Wrong sentiment range for low-tier outlets: using `≥ 0` instead of `≥ +2` |
| **Good Story** | Missing upper bound: should be `≥ +1 AND < +2` for high-tier |
| **Routine Positive** | Missing `return` statement - returns empty string! |

---

## 🔧 **ISSUE 3: Missing Orchestra Format Columns**

### **Problem**
Orchestra format entities (DraftKings, BetMGM) missing state/modifier output columns

**Evidence**:
```
Bet365: ✅ Has 1_C_State, 1_C_Modifier
FanDuel: ❌ Only has 2_C_Sent_Normalized  
DraftKings: ❌ No state/modifier columns
BetMGM: ❌ No state/modifier columns
```

### **Root Cause**
Orchestra format entity mappings get empty string defaults:
```python
state=actual_mappings.get("state", f"Entity_{company}_State" if not is_orchestra_entity else ""),
modifier=actual_mappings.get("modifier", f"Entity_{company}_Modifier" if not is_orchestra_entity else ""),
```

When `state=""` and `modifier=""`, no output columns are created.

### **Fix Required**
Generate proper column names for Orchestra format entities in output CSV.

---

## 📋 **Implementation Priority**

### **Phase 1: Critical Fixes**
1. ✅ **Issue 3** (easiest) - Fix Orchestra column generation
2. ✅ **Issue 2** - Fix Under Fire/Leader canonical logic  
3. ✅ **Issue 1** - Add state validation guardrails

### **Phase 2: Validation**
1. Test with audit dataset
2. Verify state violations drop to 0
3. Confirm Under Fire tiering matches canonical rules
4. Ensure all entities have output columns

---

## 🎯 **Expected Outcomes**

- **State violations**: 161 → 0
- **Under Fire mismatches**: 15 → 0  
- **Missing columns**: 3 entities → 0
- **Audit compliance**: Full canonical rule adherence

**Result**: Clean Pass 1 output ready for Pass 2 signals analysis.