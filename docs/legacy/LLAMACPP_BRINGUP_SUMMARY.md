# llama.cpp Bring-up Summary

**Branch:** `phase3-week3-bringup-llamacpp`  
**Status:** ✅ Complete and operational  
**Tests:** 634/634 passing (including 11 new tool discovery tests)

## Problem Statement

Quantization was failing because:
1. llama.cpp switched from Make to CMake build system
2. Prior `make -j` did not build binaries (wrong build system)
3. Tool detection hardcoded legacy path: `llama.cpp/llama-quantize`
4. Modern CMake builds place binaries in `build/bin/llama-quantize`

## Solution

### 1. Setup Script (`scripts/setup_llama_cpp.sh`)
- Clones llama.cpp if missing
- Builds with CMake: `cmake -S . -B build && cmake --build build -j`
- Verifies both convert_hf_to_gguf.py and quantize binary exist
- Provides clear instructions for setting LLAMA_CPP_DIR

### 2. Improved Tool Discovery (`training/model_compression.py`)

Added `_find_quantize_binary()` method that searches in priority order:
```python
candidates = [
    "build/bin/llama-quantize",  # Modern CMake (bin subdir)
    "build/bin/quantize",        # Alternative name
    "build/llama-quantize",      # CMake (no bin subdir)
    "build/quantize",            # Alternative
    "llama-quantize",            # Legacy Make
    "quantize",                  # Legacy alternative
]
```

### 3. Enhanced Error Messages
Now shows:
- Current LLAMA_CPP_DIR value
- All candidate paths searched
- Whether files exist but lack execute permission
- Clear instructions to run setup script

### 4. Comprehensive Tests (`tests/test_tool_discovery.py`)
11 tests covering:
- CMake bin directory layout
- Alternative binary names (quantize vs llama-quantize)
- Build root locations
- Legacy Make layouts
- Priority ordering (prefers CMake over Make)
- Non-executable files
- Missing binaries
- Full integration with _check_llama_cpp()

## Verification

### Discovered Binary Path
```
/home/cole-hanan/llama.cpp/build/bin/llama-quantize
```

### Tool Detection Output
```
INFO:training.model_compression:  convert_hf_to_gguf.py: ✓
INFO:training.model_compression:  quantize binary: ✓ (build/bin/llama-quantize)
```

### Test Results
```
634 passed in 54.05s
```

## Usage

### One-time Setup
```bash
cd ~/milton
bash scripts/setup_llama_cpp.sh
export LLAMA_CPP_DIR=$HOME/llama.cpp
```

### Verify Installation
```bash
export LLAMA_CPP_DIR=$HOME/llama.cpp
python -c "from training.model_compression import ModelCompression; mc = ModelCompression(); print('OK' if mc._check_llama_cpp() else 'FAIL')"
```

### Run Quantization
```bash
export LLAMA_CPP_DIR=$HOME/llama.cpp
python scripts/quantize_latest_model.py --bits 4
```

## Files Changed

| File | Lines | Description |
|------|-------|-------------|
| `scripts/setup_llama_cpp.sh` | +143 | CMake build automation |
| `training/model_compression.py` | +60/-13 | Multi-location tool discovery |
| `tests/test_tool_discovery.py` | +230 | Comprehensive discovery tests |

## Error Handling

### Before (unclear)
```
RuntimeError: llama.cpp tools not found!
Set LLAMA_CPP_DIR environment variable...
```

### After (actionable)
```
RuntimeError: llama.cpp tools not found!
LLAMA_CPP_DIR: /home/cole-hanan/llama.cpp

Quantize binary not found. Searched locations:
  - /home/cole-hanan/llama.cpp/build/bin/llama-quantize (not found)
  - /home/cole-hanan/llama.cpp/build/bin/quantize (not found)
  - /home/cole-hanan/llama.cpp/build/llama-quantize (not found)
  - /home/cole-hanan/llama.cpp/build/quantize (not found)
  - /home/cole-hanan/llama.cpp/llama-quantize (not found)
  - /home/cole-hanan/llama.cpp/quantize (not found)

To build llama.cpp with CMake:
  cd ~/milton && bash scripts/setup_llama_cpp.sh
  export LLAMA_CPP_DIR=$HOME/llama.cpp
```

## Constraints Satisfied

✅ **Minimal diffs** - Only modified tool detection logic  
✅ **No silent fallbacks** - Errors show exactly what was searched  
✅ **Future-compatible** - Searches multiple common locations  
✅ **Deterministic setup** - Script ensures reproducible builds  
✅ **Robust discovery** - Tests verify all layouts work  

## Next Steps

Quantization infrastructure is now operational. To actually quantize models:

1. **Create valid distilled model:**
   ```bash
   python scripts/distill_current_adapter.py
   ```

2. **Quantize it:**
   ```bash
   python scripts/quantize_latest_model.py --bits 4
   ```

Current limitation: Test adapters don't produce valid HF models for conversion.
User must run actual LoRA training to create valid adapters first.

## Commit

```
Bring-up: build llama.cpp via CMake and improve tool discovery

- Created scripts/setup_llama_cpp.sh to build llama.cpp with CMake
- Added _find_quantize_binary() to search modern CMake and legacy Make layouts
- Updated error messages to show all searched paths and recommend setup script
- Created tests/test_tool_discovery.py with 11 comprehensive tests
- All 634 tests passing

Discovered quantize binary: /home/cole-hanan/llama.cpp/build/bin/llama-quantize
```
