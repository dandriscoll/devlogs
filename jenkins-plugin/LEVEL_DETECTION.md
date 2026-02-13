# Log Level Detection Criteria

The Jenkins plugin classifies each log line as `error`, `warning`, `debug`, or
`info` (the default).  Classification happens in `DevlogsLogStorage.detectLevel`
and is applied before the line is sent to the devlogs backend.

## Evaluation order

Lines are evaluated top-to-bottom; the first matching rule wins.

### 1. Archive verbose output → `debug`

Lines that look like `zip`, `tar`, or `jar` verbose progress are always
downgraded to `debug`, regardless of any keywords in the file path.

Matched pattern (after trimming whitespace):

```
^(adding|extracting|inflating|creating|replacing|updating|storing): .+
```

Examples:

```
adding: node_modules/http-errors/index.js (deflated 72%)   → debug
extracting: src/main/resources/error-codes.xml              → debug
```

### 2. Error keywords → `error`

A line is classified as `error` when any of the following keywords appear as a
**whole word** (case-insensitive, using `\b` word boundaries on both sides):

| Keyword  | Regex              |
|----------|--------------------|
| ERROR    | `\bERROR\b`        |
| FATAL    | `\bFATAL\b`        |
| FAILED   | `\bFAILED\b`       |

Because `\b` treats underscores as word characters, keywords embedded inside
snake_case identifiers or filenames do **not** match:

```
ERROR: something broke                        → error   (standalone keyword)
[ERROR] Build failed                          → error   (delimited by brackets)
FAILED tests/test_foo.py::test_bar            → error   (standalone keyword)
tests/test_errors.py ........          [ 72%] → info    ("errors" ≠ whole-word ERROR)
tests/test_failed.py ....              [ 90%] → info    ("_failed" has _ before it)
Collecting test_error_handling                 → info    (keyword inside identifier)
```

### 3. Warning keywords → `warning`

A line is classified as `warning` when the keyword `WARN` appears at a **word
boundary on the left** (case-insensitive).  There is no right-side boundary
constraint, so `WARN`, `WARNING`, and `WARNINGS` all match.

```
\bWARN
```

Examples:

```
WARNING: deprecated API                       → warning
[WARN] slow query detected                    → warning
tests/test_warnings.py ...             [100%] → info    ("_warnings" has _ before it)
```

### 4. Debug keyword → `debug`

A line is classified as `debug` when `DEBUG` appears as a **whole word**
(case-insensitive, `\b` on both sides):

```
\bDEBUG\b
```

### 5. Default → `info`

Any line that does not match the rules above is classified as `info`.

## Why word boundaries?

Earlier versions used simple substring matching (`line.contains("ERROR")`).
This caused false positives for lines where the keyword appeared inside a
filename or identifier — for example, pytest progress output like:

```
tests/test_errors.py ........   [ 72%]
```

Word-boundary matching (`\bERROR\b`) prevents this because `\b` requires a
transition between a word character (`[a-zA-Z0-9_]`) and a non-word character.
Since underscores are word characters, `test_errors` has no boundary around
`error`, and the keyword is not matched.
