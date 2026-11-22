#!/usr/bin/env python3
"""Run Dash Core functional tests with their datadirs on a RAM disk.

  dash_test_ramdisk.py run [test_runner.py args...]  put datadirs on the RAM disk and run test_runner.py
  dash_test_ramdisk.py path                           print the RAM-backed directory (for TMPDIR=...)
  dash_test_ramdisk.py status                         show the RAM disk, free space and leftover test dirs
  dash_test_ramdisk.py detach                         unmount the macOS RAM disk if no test is using it

macOS: one APFS RAM disk per machine. An existing /Volumes/dashtest* RAM disk is reused;
otherwise /Volumes/dashtest-$USER is created on first use. A second one is never created.
Linux: /dev/shm/dash-func-tests-$USER (tmpfs).
Environment: DASH_TEST_RAMDISK_MB (size of a new macOS RAM disk, default 4096),
DASH_TEST_RAMDISK_MIN_FREE_MB (refuse to run below this much free space, default 2048).

test_runner.py runs under the interpreter that runs this script, so start this script
with the python3 that has dash_hash installed.
"""
import fcntl
import getpass
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

SIZE_MB = int(os.environ.get("DASH_TEST_RAMDISK_MB", "4096"))
MIN_FREE_MB = int(os.environ.get("DASH_TEST_RAMDISK_MIN_FREE_MB", "2048"))
STALE_SECONDS = 12 * 3600
TEST_DIR_PREFIXES = ("test_runner_", "dash_func_test_")
USER = getpass.getuser()
MAC_MOUNT = f"/Volumes/dashtest-{USER}"
LINUX_DIR = f"/dev/shm/dash-func-tests-{USER}"


def log(msg):
    print(f"dash-ramdisk: {msg}", file=sys.stderr)


def die(msg):
    log(msg)
    sys.exit(2)


def ram_backed_mounts(hdiutil_plist):
    """Mount points of attached ram:// images, from `hdiutil info -plist` output."""
    mounts = set()
    for image in plistlib.loads(hdiutil_plist).get("images", []):
        if str(image.get("image-path", "")).startswith("ram://"):
            mounts.update(e["mount-point"] for e in image.get("system-entities", []) if e.get("mount-point"))
    return mounts


def dash_ram_disks(hdiutil_plist):
    """Mounted dashtest RAM disks, the helper's own name first."""
    disks = [m for m in ram_backed_mounts(hdiutil_plist)
             if re.fullmatch(r"dashtest(-.+)?", os.path.basename(m))]
    return sorted(disks, key=lambda m: (m != MAC_MOUNT, m))


def mac_ram_disks():
    out = subprocess.run(["hdiutil", "info", "-plist"], capture_output=True, check=True).stdout
    return dash_ram_disks(out)


def mac_create(mount, size_mb):
    """Attach and format a RAM disk at mount; returns an error string, or None on success."""
    if os.path.exists(mount):
        return f"{mount} exists but is not a mounted volume; remove that stale directory"
    attach = subprocess.run(["hdiutil", "attach", "-nomount", f"ram://{size_mb * 2048}"],
                            capture_output=True, text=True)
    if attach.returncode != 0 or not attach.stdout.split():
        return f"could not attach a RAM disk: {attach.stderr.strip()}"
    dev = attach.stdout.split()[0]
    try:
        erase = subprocess.run(["diskutil", "erasevolume", "APFS", os.path.basename(mount), dev],
                               capture_output=True, text=True)
        if erase.returncode != 0 or not os.path.ismount(mount):
            subprocess.run(["hdiutil", "detach", dev], capture_output=True)
            return f"could not format the RAM disk {dev} at {mount}: {erase.stderr.strip()}"
    except BaseException:
        subprocess.run(["hdiutil", "detach", dev], capture_output=True)
        raise
    log(f"created a {size_mb} MB RAM disk at {mount}")
    return None


def writable(base):
    try:
        tempfile.TemporaryDirectory(dir=base).cleanup()
        return True
    except OSError:
        return False


def mac_ensure():
    lock_path = os.path.expanduser("~/.cache/dash-test-ramdisk.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        disks = mac_ram_disks()
        if disks:
            mount = disks[0]
        elif os.path.ismount(MAC_MOUNT):
            die(f"{MAC_MOUNT} is mounted but is not a RAM disk; unmount it or rename it")
        else:
            error = mac_create(MAC_MOUNT, SIZE_MB)
            if error:
                log(error)
                return None
            mount = MAC_MOUNT
    if not writable(mount):
        log(f"cannot write to {mount} (sandboxed session, or another user's disk?); "
            "not creating a second RAM disk")
        return None
    return mount


def linux_ensure():
    if not os.path.isdir("/dev/shm") or shutil.disk_usage("/dev/shm").total // (1 << 20) < MIN_FREE_MB:
        log("/dev/shm is missing or smaller than the minimum free space")
        return None
    try:
        os.mkdir(LINUX_DIR, 0o700)
    except FileExistsError:
        pass
    except OSError as e:
        log(f"cannot create {LINUX_DIR}: {e}")
        return None
    st = os.lstat(LINUX_DIR)
    if os.path.islink(LINUX_DIR) or st.st_uid != os.getuid() or not writable(LINUX_DIR):
        log(f"{LINUX_DIR} is not a directory this user owns and can write")
        return None
    return LINUX_DIR


def ensure():
    """The RAM-backed directory to put datadirs in, or None if this platform has none."""
    if sys.platform == "darwin":
        return mac_ensure()
    if sys.platform.startswith("linux"):
        return linux_ensure()
    return None


def running_process_args():
    env = dict(os.environ, LC_ALL="en_US.UTF-8")
    return subprocess.run(["ps", "-Awwo", "args"], capture_output=True, text=True, env=env,
                          errors="replace").stdout


def in_use(path, ps_args):
    """Whether a running process mentions this test dir.

    test_runner dirs are named test_runner_∋_🏃_<date>_<time>, and ps may escape the
    non-ASCII part, so match on the dir name's trailing ASCII run instead.
    """
    tail = re.search(r"[\x00-\x7f]*$", os.path.basename(path)).group()
    return path in ps_args or (len(tail) >= 8 and tail in ps_args)


def test_dirs(base):
    """(path, age in seconds) for each test datadir under base that still exists."""
    now = time.time()
    found = []
    for name in sorted(os.listdir(base)):
        if not name.startswith(TEST_DIR_PREFIXES):
            continue
        path = os.path.join(base, name)
        try:
            found.append((path, now - os.path.getmtime(path)))
        except FileNotFoundError:
            pass
    return found


def stale_test_dirs(dirs, ps_args):
    """Test dirs older than STALE_SECONDS that no running process mentions."""
    return [path for path, age in dirs if age > STALE_SECONDS and not in_use(path, ps_args)]


def free_mb(base):
    return shutil.disk_usage(base).free // (1 << 20)


def make_room(base):
    if free_mb(base) >= MIN_FREE_MB:
        return
    for path in stale_test_dirs(test_dirs(base), running_process_args()):
        log(f"removing stale test dir {path}")
        shutil.rmtree(path, ignore_errors=True)
    if free_mb(base) < MIN_FREE_MB:
        die(f"only {free_mb(base)} MB free on {base} (need {MIN_FREE_MB}); "
            f"see `status` and delete failed-test dirs you no longer need")


def has_tmpdir_arg(args):
    return any(a.startswith("--tmpdir") or (a.startswith("-t") and not a.startswith("--")) for a in args)


def runner_argv(test_runner, args, base):
    extra = [] if base is None or has_tmpdir_arg(args) else [f"--tmpdirprefix={base}"]
    return [sys.executable, test_runner] + extra + list(args)


def find_test_runner():
    """test_runner.py in the current dir (source tree or build dir), else at the git top level."""
    candidates = [os.path.join("test", "functional", "test_runner.py")]
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
    if top:
        candidates.append(os.path.join(top, "test", "functional", "test_runner.py"))
    for runner in candidates:
        if os.path.isfile(runner):
            return runner
    die("run this from a Dash Core source or build dir (test/functional/test_runner.py not found)")


def ensure_or_warn():
    base = ensure()
    if base is None:
        log("WARNING: no RAM disk on this platform; datadirs go to the default temp dir, "
            "so expect timeouts at high -j")
    else:
        make_room(base)
    return base


def cmd_run(args):
    runner = find_test_runner()
    base = ensure_or_warn()
    argv = runner_argv(runner, args, base)
    if base is not None:
        log(f"datadirs on {base}")
    os.execv(argv[0], argv)


def cmd_path():
    base = ensure_or_warn()
    print(base if base is not None else os.environ.get("TMPDIR", "/tmp"))


def cmd_status():
    bases = mac_ram_disks() if sys.platform == "darwin" else [LINUX_DIR] if os.path.isdir(LINUX_DIR) else []
    if not bases:
        print("no RAM disk set up yet (created on first `run` or `path`)")
        return
    if len(bases) > 1:
        print(f"WARNING: {len(bases)} dashtest RAM disks are mounted; `detach` the idle extras")
    ps_args = running_process_args()
    for base in bases:
        print(f"{base}: {free_mb(base)} MB free")
        for path, age in test_dirs(base):
            state = "in use" if in_use(path, ps_args) else "idle"
            print(f"  {os.path.basename(path)}  {state}, {age / 3600:.1f}h old")


def cmd_detach():
    if sys.platform != "darwin":
        die("detach only applies to the macOS RAM disk")
    disks = mac_ram_disks()
    if not disks:
        log("no dashtest RAM disk is mounted")
        return
    ps_args = running_process_args()
    failed = False
    for mount in disks:
        if mount in ps_args:
            log(f"a running process is using {mount}; not detaching it")
            failed = True
            continue
        result = subprocess.run(["hdiutil", "detach", mount], capture_output=True, text=True)
        if result.returncode != 0:
            log(f"could not detach {mount}: {result.stderr.strip()}")
            failed = True
    if failed:
        sys.exit(2)


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return
    cmd, rest = argv[0], argv[1:]
    if cmd == "run":
        cmd_run(rest)
    elif cmd == "path":
        cmd_path()
    elif cmd == "status":
        cmd_status()
    elif cmd == "detach":
        cmd_detach()
    else:
        die(f"unknown command {cmd!r}; try --help")


if __name__ == "__main__":
    main(sys.argv[1:])
