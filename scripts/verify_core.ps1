param(
    [ValidateRange(1, 65535)]
    [int]$PostgresPort = 5432,

    [switch]$SkipSync,

    [switch]$ConfirmTestDatabaseMigrations
)

$ErrorActionPreference = "Stop"

function Assert-NativeSuccess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Step,

        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    if ($ExitCode -ne 0) {
        throw "$Step failed with exit code $ExitCode."
    }
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$coreProject = Join-Path $repositoryRoot "services\core-api"
$corePython = Join-Path $coreProject ".venv\Scripts\python.exe"
$databaseUrl = "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:$PostgresPort/kinsun"
$testDatabaseUrl = "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:$PostgresPort/kinsun_test"
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue

if (-not $ConfirmTestDatabaseMigrations) {
    throw "The integration suite performs migration roundtrips in kinsun_test. Re-run with -ConfirmTestDatabaseMigrations."
}

if ($uvCommand) {
    if ($SkipSync) {
        Write-Warning "Dependency sync was explicitly skipped; this is not a locked release-gate environment."
    }
    else {
        Push-Location $coreProject
        try {
            & $uvCommand.Source sync --frozen --extra test --extra dev
            Assert-NativeSuccess -Step "uv sync" -ExitCode $LASTEXITCODE
        }
        finally {
            Pop-Location
        }
    }
}
elseif (-not $SkipSync) {
    throw "uv is not available. Install uv for a locked gate, or explicitly use -SkipSync for a degraded local verification."
}
else {
    Write-Warning "uv is not available; using the existing core-api .venv because -SkipSync was explicitly provided."
}

if (-not (Test-Path $corePython -PathType Leaf)) {
    throw "Core Python environment not found at $corePython. Install uv, then run this script again."
}

$env:DATABASE_URL = $databaseUrl
$env:TEST_DATABASE_URL = $testDatabaseUrl
$env:APP_ENV = "development"
$env:FAKE_AUTH_ENABLED = "false"

$databaseGuard = @'
import asyncio
import os

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

EXPECTED_DATABASE = "kinsun_test"
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}
url = make_url(os.environ["TEST_DATABASE_URL"])
if url.host not in ALLOWED_HOSTS or url.database != EXPECTED_DATABASE:
    raise SystemExit(f"Refusing unsafe test database URL: host={url.host!r}, database={url.database!r}")

async def verify_database() -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            actual_database = (await connection.exec_driver_sql("SELECT current_database()"))
            actual_database = actual_database.scalar_one()
    finally:
        await engine.dispose()
    if actual_database != EXPECTED_DATABASE:
        raise SystemExit(
            f"Refusing migration tests against {actual_database!r}; expected {EXPECTED_DATABASE!r}"
        )
    print(f"Verified isolated test database: {actual_database}")

asyncio.run(verify_database())
'@

$databaseGuard | & $corePython -
Assert-NativeSuccess -Step "Test database safety check" -ExitCode $LASTEXITCODE

Push-Location $coreProject
try {
    & $corePython -m pytest tests/unit
    Assert-NativeSuccess -Step "Core unit tests" -ExitCode $LASTEXITCODE
    & $corePython -m pytest tests/integration
    Assert-NativeSuccess -Step "Core integration tests" -ExitCode $LASTEXITCODE
    & $corePython -m ruff check .
    Assert-NativeSuccess -Step "Ruff lint" -ExitCode $LASTEXITCODE
    & $corePython -m ruff format --check .
    Assert-NativeSuccess -Step "Ruff format check" -ExitCode $LASTEXITCODE
}
finally {
    Pop-Location
}

Push-Location $repositoryRoot
try {
    if ($uvCommand -and -not $SkipSync) {
        & $uvCommand.Source run --frozen --project services/core-api --with "pyyaml==6.0.2" --with "jsonschema==4.23.0" --with "referencing==0.35.1" python scripts/validate_contracts.py contracts
        Assert-NativeSuccess -Step "Static contract validation" -ExitCode $LASTEXITCODE
        & $uvCommand.Source run --frozen --project services/core-api --with "pyyaml==6.0.2" --with "jsonschema==4.23.0" --with "referencing==0.35.1" python scripts/verify_contract_live.py contracts
        Assert-NativeSuccess -Step "Live contract verification" -ExitCode $LASTEXITCODE
    }
    else {
        & $corePython -c "import yaml, jsonschema, referencing"
        Assert-NativeSuccess -Step "Contract validation dependency check" -ExitCode $LASTEXITCODE
        & $corePython scripts/validate_contracts.py contracts
        Assert-NativeSuccess -Step "Static contract validation" -ExitCode $LASTEXITCODE
        & $corePython scripts/verify_contract_live.py contracts
        Assert-NativeSuccess -Step "Live contract verification" -ExitCode $LASTEXITCODE
    }

    docker compose config --quiet
    Assert-NativeSuccess -Step "Docker Compose configuration" -ExitCode $LASTEXITCODE
    git diff HEAD --check
    Assert-NativeSuccess -Step "Git diff check" -ExitCode $LASTEXITCODE

    $untrackedFiles = @(git ls-files --others --exclude-standard)
    Assert-NativeSuccess -Step "Untracked file discovery" -ExitCode $LASTEXITCODE
    if ($untrackedFiles.Count -gt 0) {
        Write-Warning "Untracked files are not covered by git diff HEAD --check:"
        $untrackedFiles | ForEach-Object { Write-Warning "  $_" }
    }
}
finally {
    Pop-Location
}

if ($SkipSync) {
    Write-Warning "Core verification passed in an explicitly unsynced local environment."
}
else {
    Write-Host "Core verification completed successfully in the locked environment."
}
