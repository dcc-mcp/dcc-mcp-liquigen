set shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

native_source := "native/liquigen-uia-bridge"
command_native_source := "native/liquigen-command-bridge"
native_build_suffix := env_var_or_default("DCC_MCP_LIQUIGEN_BUILD_SUFFIX", "")
native_build_dir := ".artifacts/liquigen-uia-bridge-build" + native_build_suffix
command_native_build_dir := ".artifacts/liquigen-command-bridge-build" + native_build_suffix

default:
    vx just --list

sync:
    vx uv sync --extra dev

lint: sync
    vx uv run ruff check src tests
    vx uv run ruff format --check src tests

python-test: sync
    vx uv run pytest -q

native-configure:
    vx --use-system-path cmake -S {{native_source}} -B {{native_build_dir}} -G "Visual Studio 17 2022" -A x64 --fresh
    vx --use-system-path cmake -S {{command_native_source}} -B {{command_native_build_dir}} -G "Visual Studio 17 2022" -A x64 --fresh

native-build: native-configure
    vx --use-system-path cmake --build {{native_build_dir}} --config Release
    vx --use-system-path cmake --build {{command_native_build_dir}} --config Release

native-test: native-build
    vx --use-system-path cmake --build {{native_build_dir}} --config Release --target RUN_TESTS
    vx --use-system-path cmake --build {{command_native_build_dir}} --config Release --target RUN_TESTS

test: python-test native-test

build: check
    vx uv run python -m build

release: build
    vx uv run python -m dcc_mcp_liquigen.packaging --project-root . --output-dir dist

local-release: build
    vx uv run python -m dcc_mcp_liquigen.packaging --project-root . --output-dir dist --include-native-bridge --native-bridge-dir {{command_native_build_dir}}/Release

check: lint test
