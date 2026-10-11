## 1. Single amount normalization (P1)

- [x] 1.1 In `parse_donation`, replace `amount=Decimal(str(data["amount"]))` with `amount=data["amount"]` and drop the now-unused `Decimal` import (keep `InvalidOperation`); verify `uv run pytest tests/test_protocol.py` passes, including `test_parse_donation_raises_on_non_numeric_amount`
- [x] 1.2 Add a test asserting `parse_donation` with an integer `amount` yields a `Decimal` (locking in that `Donation.__post_init__` normalizes non-string forms); verify the new test passes

## 2. Not-connected gateway reports a failed attempt (P2)

- [x] 2.1 In `AiohttpGateway._http`, replace `raise RuntimeError("gateway is not connected")` with `raise ProtocolError("gateway is not connected")` (no new import needed); verify the module imports and `uv run pytest tests/test_gateway.py` passes
- [x] 2.2 Add a test in `tests/test_gateway.py` asserting `run_stream` on an unconnected gateway (no session injected, `connect()` not called) returns `StreamOutcome(connected=False)` and does not raise; verify `uv run pytest tests/test_gateway.py` passes

## 3. Stats mutation encapsulation and determinism (P3/P4)

- [x] 3.1 In `Stats`, change `record_donation` to `record_donation(self, now: float)` setting `last_donation_at = now`, and add `record_publish_failure()` (increments) and `record_publish_success()` (resets to 0); verify `uv run pytest tests/test_service.py` passes
- [x] 3.2 In `make_push_handler`, import `time` and replace the direct `stats.publish_failures` writes with `stats.record_publish_failure()` / `stats.record_publish_success()`, and call `stats.record_donation(time.time())`; verify `uv run pytest tests/test_publisher.py` passes (retry-succeeds and failure-recording cases still assert the counters)
- [x] 3.3 Add tests asserting `record_donation(now)` sets `donations` and `last_donation_at` deterministically, and that `record_publish_failure` / `record_publish_success` increment and reset the counter; verify the new tests pass

## 4. Full verification

- [x] 4.1 Run `uv run pytest` and verify the full suite passes
- [x] 4.2 Run `uv run ruff check .` and `uv run ruff format --check .` and verify the lint gate passes
- [x] 4.3 Run `openspec validate fp-review-followup --strict` and verify the change validates
