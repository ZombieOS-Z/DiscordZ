param(
    [string]$ZSharpHeaders = "D:\VS Code\Projects\Z#\native\include",
    [string]$PythonRoot = "D:\VS Code\Projects\Z#\build\new-installer-test\python",
    [string]$ZVM = "D:\VS Code\Projects\Z#\build\Release\zsharp.exe",
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

$taskCompilerSetup = "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"

if (!(Test-Path -LiteralPath $taskCompilerSetup)) {
    throw "Visual Studio C++ build tools are required."
}

if (!(Test-Path -LiteralPath "$ZSharpHeaders\zsharp_c.h")) {
    throw "Z# C headers not found: $ZSharpHeaders"
}

if (!(Test-Path -LiteralPath "$PythonRoot\include\Python.h")) {
    throw "Python headers not found: $PythonRoot\include"
}

if (!(Test-Path -LiteralPath "$PythonRoot\libs\python313.lib")) {
    throw "Python 3.13 library not found: $PythonRoot\libs\python313.lib"
}

if (!(Test-Path -LiteralPath $ZVM)) { throw "ZVM executable not found: $ZVM" }
$taskRuntimeRoot = Join-Path (Split-Path -Parent (Resolve-Path -LiteralPath $ZVM).Path) "python"
if (!(Test-Path -LiteralPath "$taskRuntimeRoot\python.exe")) {
    Write-Host "Preparing the development ZVM's bundled Python runtime..."
    New-Item -ItemType Directory -Path $taskRuntimeRoot -Force | Out-Null
    Get-ChildItem -LiteralPath $PythonRoot | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $taskRuntimeRoot -Recurse -Force
    }
}
if (!(Test-Path -LiteralPath "$taskRuntimeRoot\python313.dll")) {
    throw "DiscordZ is compiled for Python 3.13; the selected ZVM must bundle that ABI."
}
$taskVendor = Join-Path $PSScriptRoot "Python\vendor"
New-Item -ItemType Directory -Path $taskVendor -Force | Out-Null
if (!$SkipDependencyInstall) {
    & "$taskRuntimeRoot\python.exe" -I -m pip install --disable-pip-version-check --only-binary=:all: --upgrade --target $taskVendor "discord.py==2.7.1"
    if ($LASTEXITCODE -ne 0) { throw "Could not prepare DiscordZ's Python dependencies." }
}
& "$taskRuntimeRoot\python.exe" -I -c "import sys; sys.path.insert(0, sys.argv[1]); import discord, audioop, ssl; print('DiscordZ dependencies verified:', discord.__version__)" $taskVendor
if ($LASTEXITCODE -ne 0) { throw "DiscordZ dependency verification failed." }

Push-Location $PSScriptRoot

try {
    $taskBuild = '"{0}" && cl /nologo /c /O2 /MT /I. /I"{1}" C\Main.c /FoC\Main-wrapper.obj && cl /nologo /c /O2 /MT /I. /I"{1}" C\Presence.c /FoC\Presence-wrapper.obj && cl /nologo /c /O2 /MT /I. /I"{1}" C\Bot.c /FoC\Bot-wrapper.obj && cl /nologo /c /O2 /MT /EHsc /std:c++17 /I. /I"{1}" "C++\Main.cpp" /FoC\Main-native.obj && cl /nologo /c /O2 /MT /EHsc /std:c++17 /I. /I"{1}" "C++\Presence.cpp" /FoC\Presence-native.obj && cl /nologo /c /O2 /MT /EHsc /std:c++17 /I. /I"{1}" /I"{2}\include" "C++\Bot.cpp" /FoC\Bot-native.obj && cl /nologo /c /O2 /MT /I. /I"{1}" C\Bots\Events.c /FoC\Events-wrapper.obj && cl /nologo /c /O2 /MT /I. /I"{1}" C\Bots\Webhooks.c /FoC\Webhooks-wrapper.obj && cl /nologo /c /O2 /MT /EHsc /std:c++17 /I. /I"{1}" "C++\Bots\Events.cpp" /FoC\Events-native.obj && cl /nologo /c /O2 /MT /EHsc /std:c++17 /I. /I"{1}" "C++\Bots\Webhooks.cpp" /FoC\Webhooks-native.obj && link /nologo /DLL /OUT:C\Main.zc.dll /DELAYLOAD:python313.dll C\Main-wrapper.obj C\Presence-wrapper.obj C\Bot-wrapper.obj C\Main-native.obj C\Presence-native.obj C\Bot-native.obj C\Events-wrapper.obj C\Webhooks-wrapper.obj C\Events-native.obj C\Webhooks-native.obj Discord\discord_partner_sdk.lib /LIBPATH:"{2}\libs" python313.lib delayimp.lib' -f $taskCompilerSetup, $ZSharpHeaders, $PythonRoot

    & cmd /d /s /c $taskBuild

    if ($LASTEXITCODE -ne 0) {
        throw "DiscordZ compilation failed ($LASTEXITCODE). Close apps using this DLL before rebuilding."
    }

    if (
        !(Test-Path -LiteralPath "C\discord_partner_sdk.dll") -or
        (Get-FileHash "Discord\discord_partner_sdk.dll").Hash -ne
        (Get-FileHash "C\discord_partner_sdk.dll").Hash
    ) {
        Copy-Item `
            -LiteralPath "Discord\discord_partner_sdk.dll" `
            -Destination "C\discord_partner_sdk.dll"
    }

    Write-Host "Built C\Main.zc.dll (Main, Presence, Bot, Events and Webhooks)."
    $taskSmoke = Join-Path $PSScriptRoot "build\checks\BotSmoke.zsharp"
    if (Test-Path -LiteralPath $taskSmoke) {
        & $ZVM run $taskSmoke
        if ($LASTEXITCODE -ne 0) { throw "DiscordZ's offline bundled-Python smoke test failed." }
    }
    $taskCommandsSmoke = Join-Path $PSScriptRoot "build\checks\CommandsSmoke.zsharp"
    if (Test-Path -LiteralPath $taskCommandsSmoke) {
        & $ZVM run $taskCommandsSmoke
        if ($LASTEXITCODE -ne 0) { throw "DiscordZ's offline command/webhook integration test failed." }
    }
    $taskMessageSmoke = Join-Path $PSScriptRoot "build\checks\MessageSmoke.zsharp"
    if (Test-Path -LiteralPath $taskMessageSmoke) {
        & $ZVM run $taskMessageSmoke
        if ($LASTEXITCODE -ne 0) { throw "DiscordZ's offline message/moderation integration test failed." }
    }
}
finally {
    Pop-Location
}
