## 1. Cause rendering

- [x] 1.1 Add a private helper in `src/redonats/infrastructure/gateway.py` that renders an exception as its class name, appending the message only when `str(exc)` is non-empty; verify with unit tests for a message-less `TimeoutError` and a `ProtocolError("rejected")` that the rendered text contains the class name and, only in the second case, the message.

## 2. Step attribution in run_stream

- [x] 2.1 Track a `step` label in `AiohttpGateway.run_stream`, set immediately before each awaited step (token exchange, handshake, subscription, drain), and include the label plus the rendered cause in the failure warning; verify the existing gateway tests still pass.
- [x] 2.2 Add tests asserting the failure warning names the failing step and the exception class for a token-exchange HTTP error (`step=token exchange`, `ClientError`) and for a message-less exception (`step=<the failing step>`, `TimeoutError`) with no dangling empty value; verify the new assertions pass.

## 3. Verification

- [x] 3.1 Run `uv run pytest tests/test_gateway.py` and confirm all tests pass.
- [x] 3.2 Run `uv run ruff check .` and `uv run ruff format --check .` and confirm both pass.
