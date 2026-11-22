---
name: dash-core-development
description: Dash Core build, test, architecture, and development workflow guidance for the C++ reference implementation. Use when working in dashpay/dash repositories, modifying src/, running unit or functional tests, configuring depends builds, or debugging dashd/dash-qt.
---

# Dash Core Development Guide

## Overview

Dash Core is the reference implementation for Dash, a cryptocurrency. It builds on top of Bitcoin Core, a codebase that
is primarily written in C++20 (requiring at least Clang 16 or GCC 11.1). Dash Core uses the GNU Autotools build system.

## Directory Structure

- **Implementation** `src/` - C++20 codebase
  - `src/bench/` - Performance benchmarks (uses `nanobench`)
  - `src/fuzz/` - Fuzzing harnesses
  - `src/index/` - Optional indexes
  - `src/interfaces/` - Interfaces for codebase isolation and inter-process communication
  - `src/qt/` - Implementation of Dash Qt, the GUI (uses Qt 5)
  - `src/rpc/` - JSON-RPC server and endpoints
  - `src/util/` - Utility functions
  - `src/wallet/` - Wallet implementation (uses Berkeley DB and SQLite)
  - `src/zmq/` - ZeroMQ notification support for real-time event publishing
- **Unit Tests**
  - `src/test/`, `src/wallet/test/` - C++20 unit tests (uses `Boost::Test`)
  - `src/qt/test/` - C++20 unit tests for GUI implementation (uses Qt 5)
- **Functional Tests**: `test/functional/` - Python tests (minimum version in `.python-version`) dependent on `dashd` and `dash-node`

### Directories to Exclude

**Under any circumstances**, do not make changes to:
- `guix-build*` - Build system files
- `releases` - Release artifacts
- Vendored dependencies:
  - `src/{crc32c,dashbls,gsl,immer,leveldb,minisketch,secp256k1,univalue}`
  - `src/crypto/{ctaes,x11}`

**Unless specifically prompted**, avoid:
- `.github` - GitHub workflows and configs
- `depends` - Dependency build system
- `ci` - Continuous integration
- `contrib` - Contributed scripts
- `doc` - Documentation

## Build Commands

### Setup and Build
```bash
# Generate build system
./autogen.sh

# Build dependencies for the current platform
make -C depends -j"$(( $(nproc) - 1 ))" | tail 5

# Configure with depends (use the path shown in depends build output)
# Example paths: depends/x86_64-pc-linux-gnu, depends/aarch64-apple-darwin24.3.0
./configure --prefix=$(pwd)/depends/[platform-triplet]

# Developer configuration (recommended)
./configure --prefix=$(pwd)/depends/[platform-triplet] \
            --disable-hardening \
            --enable-crash-hooks \
            --enable-debug \
            --enable-reduce-exports \
            --enable-stacktraces \
            --enable-suppress-external-warnings \
            --enable-werror

# Build with parallel jobs (leaving one core free)
make -j"$(( $(nproc) - 1 ))"
```

For fresh Dash Core worktrees, prefer prebuilt dependencies from `~/workspace/dash/depends` when available.

## Testing Commands

### Unit Tests
```bash
# Run all unit tests
make check

# Run specific test (e.g. getarg_tests)
./src/test/test_dash --run_test=getarg_tests

# Debug unit tests
gdb ./src/test/test_dash
```

### Functional Tests
```bash
# Run all functional tests
test/functional/test_runner.py

# Run specific test
test/functional/wallet_hd.py

# Extended test suite
test/functional/test_runner.py --extended

# Parallel execution
test/functional/test_runner.py -j$(nproc)

# Debug options
test/functional/test_runner.py --nocleanup --tracerpc -l DEBUG
```

### Code Quality
```bash
# Run all linting
test/lint/all-lint.py

# Common individual checks
test/lint/lint-python.py
test/lint/lint-shell.py
test/lint/lint-whitespace.py
test/lint/lint-circular-dependencies.py
```

## High-Level Architecture

Dash Core extends Bitcoin Core through composition, using a layered architecture:

```
Dash Core Components
├── Bitcoin Core Foundation (Blockchain, consensus, networking)
├── Masternodes (Infrastructure)
│   ├── LLMQ (Quorum infrastructure)
│   │   ├── InstantSend (Transaction locking)
│   │   ├── ChainLocks (Block finality)
│   │   ├── EHF Signals (Hard fork coordination)
│   │   └── Platform/Evolution (Credit Pool, Asset Locks)
│   ├── CoinJoin (Coin mixing)
│   └── Governance Voting (Masternodes vote on proposals)
├── Governance System (Proposal submission/management)
└── Spork System (Feature control)
```

### Key Architectural Components

#### Masternodes (`src/masternode/`, `src/evo/`)
- **Deterministic Masternode Lists**: Consensus-critical registry using immutable data structures
- **Active Masternode Manager**: Local masternode operations and BLS key handling
- **Special Transactions**: ProRegTx, ProUpServTx, ProUpRegTx, ProUpRevTx for masternode lifecycle

#### Long-Living Masternode Quorums (`src/llmq/`)
- **Quorum Types**: Multiple configurations (50/60, 400/60, 400/85) for different services
- **Distributed Key Generation**: Cryptographically secure quorum formation
- **Services**: ChainLocks (51% attack prevention), InstantSend, governance voting

#### CoinJoin Privacy (`src/coinjoin/`)
- **Mixing Architecture**: Masternode-coordinated mixing sessions
- **Denomination**: Uniform outputs for privacy
- **Session Management**: Multi-party transaction construction

#### Governance (`src/governance/`)
- **Governance Objects**: Proposals, triggers, superblock management
- **Treasury**: Automated payouts based on governance votes
- **Voting**: On-chain proposal voting and tallying

#### Evolution Database (`src/evo/evodb`)
- **Specialized Storage**: Masternode snapshots, quorum state, governance objects
- **Efficient Updates**: Differential updates for masternode lists
- **Credit Pool Management**: Platform integration support

## Development Workflow

### Common Tasks
```bash
# Clean build
make clean

# Run dashd with debug logging
./src/dashd -debug=all -printtoconsole

# Run functional test with custom dashd
test/functional/test_runner.py --dashd=/path/to/dashd

# Generate compile_commands.json for IDEs
bear -- make -j"$(( $(nproc) - 1 ))"
```

### GitHub CI Debugging with `gh` CLI

```bash
gh pr checks <PR_NUMBER> --json name,state,link,description
gh pr checks <PR_NUMBER> --json name,state,link --jq '.[] | select(.state == "FAILURE" or .state == "PENDING")'
gh api repos/dashpay/dash/actions/jobs/<JOB_ID>/logs
gh run view <RUN_ID> --json jobs --jq '.jobs[] | select(.conclusion == "failure") | {name, conclusion}'
```

## Important Notes

- Always build and run relevant tests when modifying source code, headers, or build configuration.
- Always run linting before commits when touching Dash Core code.
- Special transactions use payload extensions - see `src/evo/specialtx.h`
- Masternode lists use immutable data structures (Immer library) for thread safety
- LLMQ quorums have different configurations for different purposes
