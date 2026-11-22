"""The pre-push tests must not inherit Git's repository-local environment."""
import os
import pathlib
import subprocess
import tempfile

HOOK = pathlib.Path(__file__).resolve().parent.parent / ".githooks/pre-push"
ENV = dict(os.environ)
for name in subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).split():
    ENV.pop(name, None)


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], env=ENV, text=True).strip()


with tempfile.TemporaryDirectory(prefix="pre-push-test-") as directory:
    repo = pathlib.Path(directory)
    git(repo, "init", "-q", "-b", "fix/test")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    for name in ("skills.json", "hosts.json"):
        (repo / name).write_text('{"fixture": true}\n')
    git(repo, "add", "skills.json", "hosts.json")
    git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "tests").mkdir()
    (repo / "tests/test_env.py").write_text(
        "import os\n"
        "assert not {'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_CONFIG_COUNT'} & os.environ.keys()\n"
    )
    git(repo, "add", "tests/test_env.py")
    git(repo, "commit", "-qm", "test")
    tip = git(repo, "rev-parse", "HEAD")
    config = git(repo, "config", "--local", "--list")
    env = ENV | {"GIT_DIR": str(repo / ".git"), "GIT_WORK_TREE": str(repo),
                 "GIT_INDEX_FILE": str(repo / ".git/index"), "GIT_CONFIG_COUNT": "1",
                 "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "false"}
    result = subprocess.run(["bash", str(HOOK)], cwd=repo, env=env, capture_output=True, text=True,
                            input=f"refs/heads/fix/test {tip} refs/heads/main {base}\n")
    assert git(repo, "rev-parse", "HEAD") == tip, "hook tests changed the pushed branch"
    assert git(repo, "config", "--local", "--list") == config, "hook tests changed repository config"
    assert result.returncode == 0, result.stdout + result.stderr
print("pre-push: inherited Git environment cleared; repository preserved")
