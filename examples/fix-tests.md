# Task: Fix All Failing Tests

## Description

Analyze and fix all failing unit tests in the test suite.

## Approach

1. Run test suite to identify all failures
2. For each failing test:
   - Read the test to understand expected behavior
   - Read the implementation being tested
   - Determine if bug is in test or implementation
   - Fix the appropriate code
   - Verify fix doesn't break other tests

## Success Criteria

- All tests pass (`npm test` exits with code 0)
- No tests were deleted or skipped
- No functionality was removed to make tests pass

## Constraints

- Do NOT modify test assertions unless the test itself is wrong
- Do NOT add `skip` or `todo` to failing tests
- Do NOT change expected values to match buggy behavior
- If a test reveals a genuine bug, fix the implementation

## Loop Mode Instructions

This task is designed for loop mode:
```
/workflow --loop-mode --verify tests --task ./examples/fix-tests.md
```

Output `<promise>COMPLETE</promise>` when all tests pass.
