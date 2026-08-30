## 1. Protocol robustness (W1)

- [x] 1.1 Add `InvalidOperation` to the `except` tuple in `parse_donation` (import from `decimal`) and verify a non-numeric amount now raises `ProtocolError` rather than `InvalidOperation`
- [x] 1.2 Add a test in `tests/test_protocol.py` asserting `parse_donation` with a non-numeric `amount` raises `ProtocolError`, and verify `uv run pytest tests/test_protocol.py` passes

## 2. Publish-failure observability (W2)

- [x] 2.1 In `make_push_handler`, replace the final `logger.error(...)` with `logger.exception(...)` and add `exc_info=True` to the per-attempt `logger.warning` in `_publish_with_retry`
- [x] 2.2 Update/extend `tests/test_publisher.py` to assert the final-failure log line carries the exception (traceback) and verify `uv run pytest tests/test_publisher.py` passes

## 3. Broker protocol seam (S1)

- [x] 3.1 Add `persist: bool = False` to `Broker.publish` and re-type `ensure_queue`, `make_push_handler`, `publish_donation`, and `_publish_with_retry` from `RabbitBroker` to `Broker`
- [x] 3.2 Verify the existing fakes still satisfy the protocol and `uv run pytest tests/test_publisher.py tests/test_cli.py` passes

## 4. Toolchain & full verification (W3)

- [x] 4.1 Confirm `python:3.12.14-slim` and `ghcr.io/astral-sh/uv:0.12.7` resolve and the image builds (`docker build` or `uv sync --locked` as a sanity check); correct the pin if either tag is wrong
- [x] 4.2 Run `uv run pytest`, `uv run ruff check .`, and `uv run ruff format --check .` and verify the full suite and lint gate pass
- [x] 4.3 Run `openspec validate rev01-followup --strict` and verify the change validates
