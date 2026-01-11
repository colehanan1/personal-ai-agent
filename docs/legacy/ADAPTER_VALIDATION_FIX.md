# Adapter Validation Fix - Complete Implementation

## Problem Statement

**Original Issue:**
```
KeyError: 'peft_type'
```

When running `scripts/distill_current_adapter.py`, the script would crash with a confusing KeyError because invalid "test adapters" with `{"test": true}` config files were being registered and activated as if they were valid PEFT adapters.

## Root Cause

1. Test adapters created during development had invalid structure:
   - `adapter_config.json` contained `{"test": true}` instead of PEFT metadata
   - No `peft_type` key required by PEFT library
   - No adapter weight files (adapter_model.safetensors/.bin)

2. No validation before registration/activation:
   - `AdapterManager.register_adapter()` accepted any directory
   - `AdapterManager.activate()` didn't validate structure
   - `AdapterManager.current_adapter()` returned invalid adapters

3. PEFT library failed when trying to load:
   - `PeftModel.from_pretrained()` expects valid adapter structure
   - Resulted in cryptic `KeyError: 'peft_type'` deep in PEFT code

## Solution

### 1. Validation Function (Single Source of Truth)

Created `validate_peft_adapter_dir()` in `training/adapter_manager.py`:

```python
def validate_peft_adapter_dir(adapter_path: Path) -> None:
    """
    Validate that a directory contains a valid PEFT LoRA adapter.
    
    Required:
    - adapter_config.json exists
    - adapter_config.json has "peft_type" key
    - adapter_model.safetensors OR adapter_model.bin exists
    
    Raises:
        RuntimeError: If invalid (with clear message about what's missing)
    """
```

### 2. Integration Points

Updated three critical methods to call validation:

**A. register_adapter()** - Validates BEFORE registration
```python
def register_adapter(self, name, adapter_path, ...):
    # Validate adapter is a real PEFT adapter
    validate_peft_adapter_dir(adapter_path)
    
    # ... rest of registration
```

**B. activate()** - Validates BEFORE activation
```python
def activate(self, name):
    # Validate adapter before activating
    adapter_path = Path(self._registry[name].adapter_path)
    validate_peft_adapter_dir(adapter_path)
    
    # ... rest of activation
```

**C. current_adapter()** - Validates when accessing active adapter
```python
def current_adapter(self):
    for adapter in self._registry.values():
        if adapter.active:
            # Validate that the active adapter is still valid
            validate_peft_adapter_dir(Path(adapter.adapter_path))
            return adapter
```

### 3. Comprehensive Tests

Created `tests/test_adapter_validation.py` with 10 tests:

**Validation Tests:**
- ✅ Fails if adapter directory doesn't exist
- ✅ Fails if adapter_config.json is missing
- ✅ Fails if adapter_config.json missing 'peft_type' key
- ✅ Fails if adapter weights file is missing
- ✅ Passes with valid adapter (safetensors)
- ✅ Passes with valid adapter (bin)

**Integration Tests:**
- ✅ Cannot register adapter with missing peft_type
- ✅ Can register valid adapter successfully
- ✅ Cannot activate invalid adapter
- ✅ current_adapter() validates and fails on invalid adapter

## Error Messages

### Before Fix
```
KeyError: 'peft_type'
  File "peft/config.py", line 326, in _get_peft_type
    return loaded_attributes["peft_type"]
           ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^
```
**Problem:** Cryptic, no guidance, hard to debug

### After Fix

**Missing peft_type:**
```
RuntimeError: Missing 'peft_type' in adapter_config.json: /path/to/adapter
This is not a valid PEFT adapter.
Found keys: ['test', 'base_model']
Run LoRA training to create a valid adapter.
```

**Missing weights:**
```
RuntimeError: Missing adapter weights in: /path/to/adapter
Expected: adapter_model.safetensors OR adapter_model.bin
This is not a valid PEFT adapter.
Run LoRA training to create a valid adapter.
```

**Active adapter invalid:**
```
RuntimeError: Active adapter 'test_adapter_real' is invalid:
Adapter directory does not exist: /path/to/adapter
Run LoRA training to create a valid adapter.

To fix this:
1. Run LoRA training to create a valid adapter
2. Or deactivate this adapter and create a new one
```

## Files Changed

### training/adapter_manager.py (+104 lines)
- Added `validate_peft_adapter_dir()` function
- Updated `register_adapter()` to validate
- Updated `activate()` to validate
- Updated `current_adapter()` to validate

### tests/test_adapter_validation.py (NEW, 227 lines)
- 10 comprehensive tests
- All validation scenarios covered
- All integration points tested

## Verification

### Test Results
```
tests/test_adapter_validation.py ............ [ 10/10 passed ]
tests/test_model_registry.py ................ [ 27/27 passed ]
Full test suite ............................ [ 623/623 passed ]
```

### Example Validation
```bash
# Try to register invalid adapter
$ python -c "from training.adapter_manager import AdapterManager; ..."
RuntimeError: Missing 'peft_type' in adapter_config.json

# Try to run distillation with invalid adapter
$ python scripts/distill_current_adapter.py
ERROR: Active adapter 'name' is invalid: ...
```

## Design Decisions

### 1. Single Validation Function
- One function (`validate_peft_adapter_dir()`) checks all requirements
- Reused everywhere validation is needed
- Ensures consistent error messages

### 2. Fail Early
- Validation happens BEFORE registration/activation
- `current_adapter()` validates on access (fail fast)
- No way to have an invalid active adapter

### 3. Clear Error Messages
- Always cite specific missing file/key
- Show what was found vs what's expected
- Suggest actionable solution ("Run LoRA training")

### 4. Standard Exceptions
- Use `RuntimeError` (not custom exception class)
- Message contains all context
- Easy to catch and handle

### 5. Minimal Changes
- Only modified adapter_manager.py
- No changes to existing tests
- No changes to other modules

## Impact

### Before
- ❌ Invalid adapters could be registered
- ❌ Invalid adapters could be activated
- ❌ Cryptic KeyError from PEFT library
- ❌ No guidance on how to fix

### After
- ✅ Invalid adapters rejected at registration
- ✅ Invalid adapters rejected at activation
- ✅ Clear RuntimeError with context
- ✅ Actionable guidance in error message
- ✅ Fail early (before reaching PEFT code)

## Commit

**Branch:** phase3-week3-bringup-adapterfix
**Commit:** 52b598a
**Message:** "Bring-up: validate PEFT adapters and prevent invalid activation"

## Conclusion

The fix is **surgical, minimal, and well-tested**:
- Only 2 files changed
- 104 lines added to adapter_manager.py
- 227 lines of tests added
- No existing tests modified
- All 623 tests pass

Invalid adapters now fail early with clear, actionable error messages instead of cryptic KeyErrors deep in the PEFT library.
