[CmdletBinding()]
param(
    # 指定此參數時才會刪除並重建 evals/speech/.venv；一般更新套件不需要使用。
    # 預設為 false，避免使用者只想補裝依賴時意外移除既有環境。
    [switch]$Recreate = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$evaluationRoot = Join-Path $repositoryRoot "evals\speech"
$venvPath = Join-Path $evaluationRoot ".venv"
$requirementsPath = Join-Path $evaluationRoot "requirements-notebook.txt"
$pythonPath = Join-Path $venvPath "Scripts\python.exe"

if ($Recreate.IsPresent -and (Test-Path -LiteralPath $venvPath)) {
    # 刪除前先解析絕對路徑，並確認目標確實位於 evals/speech 內；此檢查可防止路徑組合錯誤時誤刪其他資料夾。
    $resolvedEvaluationRoot = (Resolve-Path -LiteralPath $evaluationRoot).Path
    $resolvedVenv = (Resolve-Path -LiteralPath $venvPath).Path
    if (-not $resolvedVenv.StartsWith($resolvedEvaluationRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a virtual environment outside evals/speech."
    }
    Remove-Item -LiteralPath $resolvedVenv -Recurse -Force
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    # 評測工具使用獨立虛擬環境，不修改 core-api 或 agent-runtime 各自鎖定的依賴。
    & uv venv $venvPath --python 3.10
    if ($LASTEXITCODE -ne 0) {
        throw "uv failed to create the speech evaluation environment."
    }
}

# requirements 檔只列直接依賴，因此必須使用 install 解析並安裝 transitive dependencies；
# 不可改用 sync，因為 sync 只適合已包含完整依賴樹的 compiled requirements／lock 檔。
& uv pip install --python $pythonPath --strict --requirements $requirementsPath
if ($LASTEXITCODE -ne 0) {
    throw "uv failed to install speech evaluation dependencies."
}

# 安裝完成後立即匯入主要套件，讓缺少 DLL 或不相容版本在設定階段就明確失敗。
& $pythonPath -c "import ipywidgets, jupyterlab, matplotlib, nbformat, numpy, pandas; print('speech evaluation environment ready')"
if ($LASTEXITCODE -ne 0) {
    throw "Speech evaluation dependency import check failed."
}

Write-Host ""
Write-Host "Open the notebook with:"
Write-Host ".\evals\speech\.venv\Scripts\python.exe -m jupyterlab .\evals\speech\notebooks\speech_evaluation.ipynb"
