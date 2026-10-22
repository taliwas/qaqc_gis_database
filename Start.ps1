param([switch]$Check)

# Prefer the project's environment. Codex's bundled Python can use the existing
# Python 3.12 packages if the original system Python has become unavailable.
$ErrorActionPreference = 'Stop'
$taskVenv = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$taskBundled = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$taskPackages = Join-Path $PSScriptRoot '.venv\Lib\site-packages'
$taskOldPythonPath = $env:PYTHONPATH
$taskPython = $null

try {
    if (Test-Path -LiteralPath $taskVenv) {
        & $taskVenv --version 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $taskPython = $taskVenv }
    }
    if (-not $taskPython -and (Test-Path -LiteralPath $taskBundled) -and (Test-Path -LiteralPath $taskPackages)) {
        $taskPython = $taskBundled
        $env:PYTHONPATH = $taskPackages
    }
    if (-not $taskPython) {
        throw 'Create a Python environment and install requirements.txt using the instructions in README.md.'
    }
    Push-Location $PSScriptRoot
    try {
        if ($Check) {
            & $taskPython -c 'import streamlit, pandas, numpy, plotly, openpyxl, shapely, defusedxml; print("Ready: Streamlit " + streamlit.__version__)'
        } else {
            & $taskPython -m streamlit run app.py
        }
        if ($LASTEXITCODE -ne 0) { throw 'Application runtime failed. See the output above and README.md setup instructions.' }
    } finally {
        Pop-Location
    }
} finally {
    $env:PYTHONPATH = $taskOldPythonPath
}
