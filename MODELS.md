# Model Comparison Notes

## Test Device

- MacBook Pro M5
- 24 GB unified memory
- 1 TB SSD
- Ollama local runs inside `cmux` workspace `workspace:23` (`OLLAMA`)

## Models Compared

- `codegeex4`
- `qwen2.5-coder:14b`

## What Was Tested

- Basic code generation
- Debugging
- Refactor without behavior change
- LRU cache implementation
- Self-correction after a correction prompt

## Result Summary

### `qwen2.5-coder:14b`

- Better overall coding quality
- Better constraint following
- Better self-correction when corrected
- Slower than `codegeex4`, but more reliable

### `codegeex4`

- Faster first response
- Weaker task follow-through
- Drifted more often
- Mixed older context into later answers
- Not reliable enough as the main coding assistant

## Score Summary

- `qwen2.5-coder:14b`: about `8.5-9/10`
- `codegeex4`: about `5.5-6.5/10`

## Clean Benchmark Run - 2026-05-12

Each test was run from a fresh model invocation to avoid chat-history
pollution. The right-side `cmux` layout used:

- Top: `codegeex4`
- Bottom: `qwen2.5-coder:14b`

### Test 1: LRU Cache Under 60 Lines

- `codegeex4`: Produced working code quickly, but used a list for recency
  tracking, which makes promotion and eviction `O(n)`. It also added
  explanation text despite the "code only" prompt.
- `qwen2.5-coder:14b`: Produced a cleaner `OrderedDict` implementation with
  correct promotion on `get` and eviction on `put`. Followed the output
  constraint better.

Winner: `qwen2.5-coder:14b`

### Test 2: Refactor Without Behavior Change

- `codegeex4`: Kept behavior and stayed concise, but mostly rewrote the
  original function instead of meaningfully improving testability.
- `qwen2.5-coder:14b`: Extracted a helper for value cleaning while preserving
  behavior, making the result easier to test.

Winner: `qwen2.5-coder:14b`

### Test 3: Self-Correction After ATDD-Style Correction

Initial prompt asked for a `collections.Counter` implementation and explanation.
Correction then required no imports, numbers only, smaller-number tie break, and
code plus one example only.

- `codegeex4`: Initial answer returned `(number, count)` tuples, which violated
  the expected return shape. After correction, it fixed the implementation and
  tie break, but still added explanation text after the code.
- `qwen2.5-coder:14b`: Initial answer returned numbers correctly. After
  correction, it removed imports, preserved tie-breaking, and followed the
  stricter output format more closely.

Winner: `qwen2.5-coder:14b`

## Practical Takeaway

- Use `qwen2.5-coder:14b` as the main coding model on this machine.
- Use `codegeex4` only when speed matters more than answer quality.
- For ATDD-style worker loops, `qwen2.5-coder:14b` is the better fit because it recovers better after correction.
