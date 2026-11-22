"""Offline checks for request_core_faucet.py. Run: python3 -I test_request_core_faucet.py"""
import contextlib, hashlib, importlib.util, io, os, sys

spec = importlib.util.spec_from_file_location(
    "rcf", os.path.join(os.path.dirname(os.path.abspath(__file__)), "request_core_faucet.py"))
rcf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rcf)
fails = 0


def check(cond, name):
    global fails
    print(("ok   " if cond else "FAIL ") + name)
    fails += not cond


def server_accepts(token, c, s, d, solutions):
    """dash-faucet-cf's verifySolutions, minus the HMAC: every sub-challenge must check out."""
    return len(solutions) == c and all(
        hashlib.sha256((rcf.prng(f"{token}{i}", s) + str(n)).encode()).hexdigest()
        .startswith(rcf.prng(f"{token}{i}d", d))
        for i, n in enumerate(solutions, 1))


# Vectors from a challenge the live cap.js server issued and accepted (dash-faucet-cf test/cap.test.ts).
LIVE_TOKEN = "b987380d8edbb0448190cd10094bc26769dc7bdaef08c2d89e"
SALT = "956fc0cbc3a458705de5f885bc50161f"
check(rcf.prng(f"{LIVE_TOKEN}1", 32) == SALT, "prng salt matches live server")
check(rcf.prng(f"{LIVE_TOKEN}1d", 4) == "7a4f", "prng target matches live server")
check(rcf.solve_one(SALT, "7a4f") == 97269, "solver finds the accepted nonce")
check(rcf.solve_one(SALT, "7a4f0") == 1308325, "odd-length target finds the first matching nonce")
check(all(len(rcf.prng(f"x{i}", 64)) == 64 for i in range(200)), "prng emits full-width hex")
for d in (1, 2, 3):
    check(server_accepts("feed", 6, 32, d, rcf.solve("feed", 6, 32, d)), f"multi-challenge solve verifies (d={d})")

check(rcf.is_testnet_p2pkh("ySTHuuVK1CXcwugMPeLUUjgjnSia7TkLLz"), "accepts a testnet P2PKH address")
check(not rcf.is_testnet_p2pkh("ySTHuuVK1CXcwugMPeLUUjgjnSia7TkLLy"), "rejects a checksum typo")
check(not rcf.is_testnet_p2pkh("yPrynRN6ViX2rCcRL5SoSi8ntcWgdHSEa0"), "rejects non-base58 characters")
check(not rcf.is_testnet_p2pkh("Xm77DBJzsf6aMBSb25BAzTNxcjgvUECEeB"), "rejects a mainnet address")
check(not rcf.is_testnet_p2pkh(""), "rejects empty input")

# API key lookup: env wins, then the key file; nothing configured means no key.
import tempfile
saved_env, saved_file = os.environ.pop("DASH_FAUCET_KEY", None), rcf.KEY_FILE
with tempfile.TemporaryDirectory() as tmp:
    rcf.KEY_FILE = os.path.join(tmp, "api-key")
    check(rcf.api_key() is None, "no key when none is configured")
    with open(rcf.KEY_FILE, "w") as f:
        f.write("dfk_fromfile\n")
    check(rcf.api_key() == "dfk_fromfile", "reads and trims the key file")
    os.environ["DASH_FAUCET_KEY"] = "dfk_fromenv"
    check(rcf.api_key() == "dfk_fromenv", "DASH_FAUCET_KEY overrides the file")
os.environ.pop("DASH_FAUCET_KEY", None)
if saved_env is not None:
    os.environ["DASH_FAUCET_KEY"] = saved_env
rcf.KEY_FILE = saved_file


# Main-path checks use a fake faucet so they never request funds.
TEST_ADDRESS = "ySTHuuVK1CXcwugMPeLUUjgjnSia7TkLLz"
STATUS = {
    "status": "ok",
    "network": "testnet",
    "capEndpoint": "https://example.test/cap/v1/",
    "amountLimits": {"turnstileAbove": 10, "publicMax": 100},
}


def run_main(amount=None, core_code=200, core_result=None, status=STATUS, key=None):
    calls = []
    old_call, old_api_key, old_solve, old_argv = rcf.call, rcf.api_key, rcf.solve, sys.argv

    def fake_call(url, body=None, key=None):
        calls.append((url, body, key))
        if url.endswith("/api/status"):
            return 200, status
        if url.endswith("/challenge"):
            return 200, {"challenge": {"c": 1, "s": 32, "d": 1}, "token": "token"}
        if url.endswith("/redeem"):
            return 200, {"success": True, "token": "cap-token"}
        if url.endswith("/api/core-faucet"):
            return core_code, core_result or {"txid": "tx", "amount": amount or 1}
        raise AssertionError(f"unexpected URL: {url}")

    rcf.call = fake_call
    rcf.api_key = lambda: key
    rcf.solve = lambda token, c, s, d: [0] * c
    sys.argv = ["request_core_faucet.py", "--base-url", "https://example.test", TEST_ADDRESS]
    if amount is not None:
        sys.argv += ["--amount", str(amount)]
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = rcf.main()
    finally:
        rcf.call, rcf.api_key, rcf.solve, sys.argv = old_call, old_api_key, old_solve, old_argv
    return result, calls, stdout.getvalue(), stderr.getvalue()


result, calls, _out, _err = run_main(amount=2)
core_calls = [call for call in calls if call[0].endswith("/api/core-faucet")]
check(result == 0 and len(core_calls) == 1, "unkeyed amount within proof-of-work limit is sent")
check(core_calls[0][1].get("amount") == 2, "unkeyed amount is sent exactly")

result, calls, _out, _err = run_main(amount=10)
core_calls = [call for call in calls if call[0].endswith("/api/core-faucet")]
check(result == 0 and len(core_calls) == 1 and core_calls[0][1].get("amount") == 10,
      "unkeyed amount at the proof-of-work ceiling is sent")

result, calls, _out, _err = run_main(amount=50, status={k: v for k, v in STATUS.items() if k != "amountLimits"})
core_calls = [call for call in calls if call[0].endswith("/api/core-faucet")]
check(result == 0 and len(core_calls) == 1 and core_calls[0][1].get("amount") == 50,
      "unkeyed amount is sent when the status reports no limits")

result, calls, _out, _err = run_main(amount=250, key="dfk_test")
posts = [call for call in calls if call[1] is not None]
check(result == 0 and len(posts) == 1 and posts[0][0].endswith("/api/core-faucet")
      and posts[0][2] == "dfk_test" and posts[0][1].get("amount") == 250,
      "keyed amount is sent with the key and no proof of work")

for bad in ("nan", "inf", "-1", "1e-9", "0.123456789"):
    result, calls, _out, err = run_main(amount=bad)
    check(result == 2 and not calls and "--amount" in err, f"invalid amount {bad} is refused before any request")

result, calls, _out, err = run_main(amount=11)
check(result == 2 and not any(call[1] is not None for call in calls),
      "unkeyed amount above proof-of-work limit is refused before POST")
check("Turnstile" in err and "API key" in err, "Turnstile refusal names browser and API-key alternatives")

result, calls, _out, err = run_main(amount=101)
check(result == 2 and not any(call[1] is not None for call in calls),
      "unkeyed amount above public limit is refused before POST")
check("sign-in" in err and "code" in err, "sign-in refusal names browser alternatives")

result, calls, _out, err = run_main(
    core_code=400,
    core_result={"error": "Large amount", "requiresTurnstile": True},
)
check(result == 1 and len([call for call in calls if call[0].endswith("/api/core-faucet")]) == 1,
      "requiresTurnstile is reported without retry")
check("requires Turnstile" in err and "Not retrying" in err,
      "requiresTurnstile message is clear")

result, calls, _out, err = run_main(
    core_code=403,
    core_result={"error": "Sign in required", "requiresSignIn": True},
)
check(result == 1 and len([call for call in calls if call[0].endswith("/api/core-faucet")]) == 1,
      "requiresSignIn is reported without retry")
check("sign-in" in err and "Not retrying" in err, "requiresSignIn message is clear")

print("FAILURES:", fails)
sys.exit(1 if fails else 0)
