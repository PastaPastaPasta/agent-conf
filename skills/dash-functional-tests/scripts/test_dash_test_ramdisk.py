"""Offline checks for dash_test_ramdisk.py. Run: python3 -I test_dash_test_ramdisk.py"""
import importlib.util, os, plistlib, sys, tempfile, time

spec = importlib.util.spec_from_file_location(
    "dtr", os.path.join(os.path.dirname(os.path.abspath(__file__)), "dash_test_ramdisk.py"))
dtr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dtr)
fails = 0


def check(cond, name):
    global fails
    print(("ok   " if cond else "FAIL ") + name)
    fails += not cond


# --tmpdirprefix is added unless the caller already chose one.
argv = dtr.runner_argv("/r/test_runner.py", ["-j32", "wallet_basic.py --descriptors"], "/Volumes/dashtest-x")
check(argv == [sys.executable, "/r/test_runner.py", "--tmpdirprefix=/Volumes/dashtest-x", "-j32",
               "wallet_basic.py --descriptors"], "adds --tmpdirprefix and keeps test args intact")
for given in (["--tmpdirprefix", "/a"], ["--tmpdirprefix=/a"], ["-t", "/a"], ["-t/a"]):
    check(dtr.runner_argv("/r/t.py", given, "/ram")[2:] == given, f"respects caller's {given[0]}")
check(not dtr.has_tmpdir_arg(["--timeout-factor=2", "-j8"]), "--timeout-factor is not a tmpdir flag")
check(dtr.has_tmpdir_arg(["--tmpdir=/x"]), "an abbreviated --tmpdir counts as the caller's choice")
check(dtr.runner_argv("/r/t.py", ["-j4"], None)[2:] == ["-j4"], "no RAM disk means no injected flag")

# Only ram:// images count as RAM disks.
plist = plistlib.dumps({"images": [
    {"image-path": "ram://8388608", "system-entities": [
        {"dev-entry": "/dev/disk11"}, {"dev-entry": "/dev/disk11s1", "mount-point": "/Volumes/dashtest-x"}]},
    {"image-path": "/Users/x/disk.dmg", "system-entities": [
        {"dev-entry": "/dev/disk12s1", "mount-point": "/Volumes/dashtest-y"}]},
]})
mounts = dtr.ram_backed_mounts(plist)
check("/Volumes/dashtest-x" in mounts, "ram:// image mount is recognized")
check("/Volumes/dashtest-y" not in mounts, "a file-backed image is not a RAM disk")
check(dtr.ram_backed_mounts(plistlib.dumps({"images": []})) == set(), "no images, no RAM disks")

# Any existing dashtest RAM disk is reused, preferring the helper's own name.
def ram(*mounts):
    return {"image-path": "ram://8388608", "system-entities": [{"mount-point": m} for m in mounts]}
plist = plistlib.dumps({"images": [
    ram("/Volumes/dashtest"), ram(dtr.MAC_MOUNT), ram("/Volumes/scratch"), ram("/Volumes/dashtestfoo"),
    {"image-path": "/x.dmg", "system-entities": [{"mount-point": "/Volumes/dashtest-z"}]},
]})
check(dtr.dash_ram_disks(plist) == [dtr.MAC_MOUNT, "/Volumes/dashtest"],
      "only dashtest RAM disks count, the helper's own first")
check(dtr.dash_ram_disks(plistlib.dumps({"images": [ram("/Volumes/dashtest-other")]}))
      == ["/Volumes/dashtest-other"], "another user's dashtest RAM disk is reused, not duplicated")

# Pruning removes only old, idle test dirs.
with tempfile.TemporaryDirectory() as base:
    now = time.time()
    def mk(name, age_h):
        p = os.path.join(base, name)
        os.mkdir(p)
        os.utime(p, (now - age_h * 3600,) * 2)
        return p
    old_idle = mk("test_runner_\u220b_\U0001f3c3_20261027_101010", 13)
    old_busy = mk("test_runner_\u220b_\U0001f3c3_20261027_202020", 13)
    fresh = mk("test_runner_\u220b_\U0001f3c3_20261028_090909", 1)
    old_direct = mk("dash_func_test_abc12345", 20)
    unrelated = mk("something_else", 50)
    # ps under the C locale escapes the non-ASCII part of the dir name.
    ps = f"/x/dashd -datadir={base}/test_runner_M-bM^HM^K_M-pM^_M^OM^C_20261027_202020/wallet_basic_1/node0\n"
    dirs = dtr.test_dirs(base)
    check(unrelated not in [p for p, _ in dirs], "non-test dirs are never listed")
    stale = dtr.stale_test_dirs(dirs, ps)
    check(old_idle in stale and old_direct in stale, "old idle test dirs are stale")
    check(old_busy not in stale, "a dir a running test uses is kept even when ps escapes its name")
    check(fresh not in stale, "a recent dir is kept")
    check(dtr.in_use(old_direct, f"dashd -datadir={old_direct}/node0"), "an ASCII dir in use is detected")
    check(not dtr.in_use(old_idle, ps), "a different run's timestamp does not count as in use")
    real_listdir = os.listdir
    os.listdir = lambda d: real_listdir(d) + ["test_runner_removed_meanwhile"]
    try:
        listed = [p for p, _ in dtr.test_dirs(base)]
    finally:
        os.listdir = real_listdir
    check(len(listed) == 4, "a dir removed between listdir and stat is skipped")

sys.exit(1 if fails else 0)
