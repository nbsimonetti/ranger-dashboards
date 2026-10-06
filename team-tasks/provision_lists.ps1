<#
.SYNOPSIS
    Creates or updates the four Microsoft Lists behind the Ranger Team Tasks dashboard.

.DESCRIPTION
    Idempotent. For each list (Ranger Tasks, Ranger Team, Ranger Status Updates,
    Ranger Task Comments) the script finds it by display name, creates it with every
    column if it is missing, and adds any missing columns if it already exists.
    Existing columns are never changed or removed. Optionally adds roster rows to
    the Ranger Team list from a CSV, skipping anyone whose Email is already there.

    Works on Windows PowerShell 5.1 and PowerShell 7. Needs only the
    Microsoft.Graph.Authentication module. Signs in with the delegated scope
    Sites.Manage.All.

.PARAMETER SiteUrl
    Full URL of the SharePoint site, for example https://contoso.sharepoint.com/sites/RangerTeam

.PARAMETER RosterCsv
    Optional path to a CSV with columns Email, DisplayName, JobTitle. Rows whose Email
    is not already in the Ranger Team list are added with Active and IncludeInUpdates
    set to Yes.

.PARAMETER TenantId
    Optional tenant ID or domain to sign in against.

.PARAMETER DryRun
    Reads the site and reports what would be created or added without writing anything.

.EXAMPLE
    .\provision_lists.ps1 -SiteUrl https://contoso.sharepoint.com/sites/RangerTeam -DryRun

.EXAMPLE
    .\provision_lists.ps1 -SiteUrl https://contoso.sharepoint.com/sites/RangerTeam -RosterCsv $env:USERPROFILE\Documents\ranger-roster.csv
    Keep the roster CSV outside the dashboards repository. It has real names and addresses.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SiteUrl,

    [string]$RosterCsv,

    [string]$TenantId,

    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$GraphBase = 'https://graph.microsoft.com/v1.0'
$RequiredScope = 'Sites.Manage.All'

# ---------------------------------------------------------------------------
# Column definitions (Graph columnDefinition shapes)
# ---------------------------------------------------------------------------

function New-TextColumn([string]$Name, [bool]$Indexed = $false) {
    $c = [ordered]@{ name = $Name; text = [ordered]@{} }
    if ($Indexed) { $c.indexed = $true }
    return $c
}

function New-NoteColumn([string]$Name) {
    return [ordered]@{
        name = $Name
        text = [ordered]@{ allowMultipleLines = $true; linesForEditing = 6; textType = 'plain' }
    }
}

function New-ChoiceColumn([string]$Name, [string[]]$Choices, [string]$Default, [bool]$Indexed = $false) {
    $c = [ordered]@{
        name   = $Name
        choice = [ordered]@{ allowTextEntry = $false; choices = @($Choices); displayAs = 'dropDownMenu' }
    }
    if ($Default) { $c.defaultValue = [ordered]@{ value = $Default } }
    if ($Indexed) { $c.indexed = $true }
    return $c
}

function New-DateOnlyColumn([string]$Name) {
    return [ordered]@{ name = $Name; dateTime = [ordered]@{ format = 'dateOnly'; displayAs = 'standard' } }
}

function New-DateTimeColumn([string]$Name) {
    return [ordered]@{ name = $Name; dateTime = [ordered]@{ format = 'dateTime' } }
}

function New-NumberColumn([string]$Name, [bool]$Indexed = $false) {
    $c = [ordered]@{ name = $Name; number = [ordered]@{} }
    if ($Indexed) { $c.indexed = $true }
    return $c
}

function New-BooleanColumn([string]$Name, [bool]$DefaultTrue = $true) {
    $c = [ordered]@{ name = $Name; boolean = [ordered]@{} }
    if ($DefaultTrue) { $c.defaultValue = [ordered]@{ value = '1' } } else { $c.defaultValue = [ordered]@{ value = '0' } }
    return $c
}

$StatusChoices     = @('Not Started', 'In Progress', 'Blocked', 'Done')
$PriorityChoices   = @('High', 'Normal', 'Low')
$WorkstreamChoices = @(
    'Regulatory & Closing', 'Lending', 'Deposits & Treasury', 'Operations & IT', 'Compliance',
    'Marketing & Brand', 'Real Estate & Offices', 'Hiring', 'Board & Investors', 'Other'
)

$ListSpecs = @(
    [ordered]@{
        DisplayName = 'Ranger Tasks'
        Description = 'Tasks for the Ranger Team Tasks dashboard.'
        Columns     = @(
            (New-NoteColumn     'Notes'),
            (New-TextColumn     'OwnerEmail' $true),
            (New-TextColumn     'OwnerName'),
            (New-TextColumn     'AssignedByEmail' $true),
            (New-TextColumn     'AssignedByName'),
            (New-ChoiceColumn   'Status' $StatusChoices 'Not Started' $true),
            (New-ChoiceColumn   'Priority' $PriorityChoices 'Normal'),
            (New-DateOnlyColumn 'DueDate'),
            (New-DateTimeColumn 'CompletedDate'),
            (New-ChoiceColumn   'Workstream' $WorkstreamChoices 'Other'),
            (New-NumberColumn   'SortOrder'),
            (New-DateTimeColumn 'AssignedAt')
        )
    },
    [ordered]@{
        DisplayName = 'Ranger Team'
        Description = 'Team roster for the Ranger Team Tasks dashboard. Title holds the display name.'
        Columns     = @(
            (New-TextColumn    'Email' $true),
            (New-TextColumn    'JobTitle'),
            (New-BooleanColumn 'Active' $true),
            (New-BooleanColumn 'IncludeInUpdates' $true),
            (New-BooleanColumn 'CanEditAll' $false)
        )
    },
    [ordered]@{
        DisplayName = 'Ranger Status Updates'
        Description = 'Log of status update emails sent from the Ranger Team Tasks dashboard.'
        Columns     = @(
            (New-TextColumn     'SenderEmail' $true),
            (New-TextColumn     'SenderName'),
            (New-DateTimeColumn 'SentAt'),
            (New-DateOnlyColumn 'PeriodStart'),
            (New-DateOnlyColumn 'PeriodEnd'),
            (New-NumberColumn   'CompletedCount'),
            (New-NumberColumn   'OpenCount'),
            (New-NoteColumn     'Recipients'),
            (New-NoteColumn     'Body'),
            (New-ChoiceColumn   'Kind' @('Personal', 'Team') 'Personal'),
            (New-BooleanColumn  'FullTeam' $true)
        )
    },
    [ordered]@{
        DisplayName = 'Ranger Task Comments'
        Description = 'Comments on tasks in the Ranger Team Tasks dashboard.'
        Columns     = @(
            (New-NumberColumn 'TaskId' $true),
            (New-TextColumn   'AuthorEmail'),
            (New-TextColumn   'AuthorName'),
            (New-NoteColumn   'Body')
        )
    }
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Step([string]$Message) {
    Write-Host ''
    Write-Host "== $Message" -ForegroundColor Cyan
}

function Get-Prop($Object, [string]$Name) {
    # Works for both hashtables (Invoke-MgGraphRequest default) and PSObjects.
    if ($null -eq $Object) { return $null }
    if ($Object -is [System.Collections.IDictionary]) {
        if ($Object.Contains($Name)) { return $Object[$Name] }
        return $null
    }
    $p = $Object.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    return $null
}

function Invoke-Graph {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Uri,
        $Body
    )
    if ($Uri -notmatch '^https://') { $Uri = $GraphBase + $Uri }
    $attempt = 0
    while ($true) {
        $attempt++
        try {
            if ($null -ne $Body) {
                $json = $Body | ConvertTo-Json -Depth 20
                return Invoke-MgGraphRequest -Method $Method -Uri $Uri -Body $json -ContentType 'application/json'
            }
            return Invoke-MgGraphRequest -Method $Method -Uri $Uri
        }
        catch {
            $msg = $_.Exception.Message
            $retryable = ($msg -match '429|503|504|TooManyRequests|ServiceUnavailable|GatewayTimeout')
            if ($retryable -and $attempt -lt 4) {
                $wait = 5 * $attempt
                Write-Host "   Graph is throttling or busy, retrying in $wait seconds..." -ForegroundColor DarkYellow
                Start-Sleep -Seconds $wait
                continue
            }
            throw "Graph $Method $Uri failed: $msg"
        }
    }
}

function Get-AllPages([string]$Uri) {
    $results = New-Object System.Collections.ArrayList
    $next = $Uri
    while ($next) {
        $page = Invoke-Graph -Method GET -Uri $next
        $values = Get-Prop $page 'value'
        if ($values) { foreach ($v in $values) { [void]$results.Add($v) } }
        $next = Get-Prop $page '@odata.nextLink'
    }
    return ,$results
}

# ---------------------------------------------------------------------------
# Module and sign-in
# ---------------------------------------------------------------------------

Write-Step 'Checking for the Microsoft.Graph.Authentication module'
if (-not (Get-Module -ListAvailable -Name Microsoft.Graph.Authentication)) {
    Write-Host 'The Microsoft.Graph.Authentication module is not installed. Install it with:' -ForegroundColor Yellow
    Write-Host ''
    Write-Host '    Install-Module Microsoft.Graph.Authentication -Scope CurrentUser' -ForegroundColor White
    Write-Host ''
    Write-Host 'Then run this script again.'
    exit 1
}
Import-Module Microsoft.Graph.Authentication -ErrorAction Stop
Write-Host '   Found.'

Write-Step 'Signing in to Microsoft Graph'
$ctx = $null
try { $ctx = Get-MgContext } catch { $ctx = $null }
$haveScope = $false
if ($ctx -and $ctx.Scopes) {
    foreach ($s in $ctx.Scopes) {
        if ($s -ieq $RequiredScope -or $s -ieq 'Sites.FullControl.All') { $haveScope = $true }
    }
}
# Reuse an existing session only if it is for the tenant asked for.
$tenantOk = $true
if ($haveScope -and $TenantId) {
    $g = [Guid]::Empty
    if ([Guid]::TryParse($TenantId, [ref]$g)) { $tenantOk = ([string]$ctx.TenantId -ieq $g.ToString()) }
    else { $tenantOk = $false }   # a domain was given; it cannot be compared to the session's tenant GUID, so reconnect
}
if ($haveScope -and $tenantOk) {
    Write-Host "   Already connected as $($ctx.Account) (tenant $($ctx.TenantId)) with $RequiredScope."
}
else {
    if ($ctx) { try { Disconnect-MgGraph | Out-Null } catch { } }
    $connectArgs = @{ Scopes = @($RequiredScope) }
    if ($TenantId) { $connectArgs.TenantId = $TenantId }
    $cmd = Get-Command Connect-MgGraph
    if ($cmd.Parameters.ContainsKey('NoWelcome')) { $connectArgs.NoWelcome = $true }
    Connect-MgGraph @connectArgs | Out-Null
    $ctx = Get-MgContext
    Write-Host "   Connected as $($ctx.Account) (tenant $($ctx.TenantId))."
}

if ($DryRun) {
    Write-Host ''
    Write-Host 'DRY RUN: nothing will be created or changed.' -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# Resolve the site
# ---------------------------------------------------------------------------

Write-Step "Resolving site $SiteUrl"
$u = $null
if (-not [Uri]::TryCreate($SiteUrl.Trim(), [UriKind]::Absolute, [ref]$u)) { throw "SiteUrl '$SiteUrl' is not a valid URL." }
if ($u.Scheme -ne 'https') { throw 'SiteUrl must start with https://' }
$siteHost = $u.Host
$sitePath = $u.AbsolutePath.Trim('/')
if ($sitePath) { $siteUri = "/sites/${siteHost}:/$sitePath" } else { $siteUri = "/sites/$siteHost" }
try {
    $site = Invoke-Graph -Method GET -Uri ($siteUri + '?$select=id,displayName,webUrl')
}
catch {
    $tid = ''
    if ($ctx) { $tid = [string]$ctx.TenantId }
    throw "$($_.Exception.Message)`nSigned in to tenant $tid. If that is the wrong tenant, run again with -TenantId <tenant ID>."
}
$siteId = Get-Prop $site 'id'
Write-Host "   $(Get-Prop $site 'displayName') ($(Get-Prop $site 'webUrl'))"
Write-Host "   Site ID: $siteId"

# ---------------------------------------------------------------------------
# Lists and columns
# ---------------------------------------------------------------------------

Write-Step 'Reading existing lists'
$existingLists = Get-AllPages ("/sites/$siteId/lists" + '?$select=id,displayName&$top=100')
Write-Host "   $($existingLists.Count) lists on the site."

$summary = New-Object System.Collections.ArrayList
$listIds = @{}

foreach ($spec in $ListSpecs) {
    $name = $spec.DisplayName
    Write-Step $name

    $found = $null
    foreach ($l in $existingLists) {
        if ((Get-Prop $l 'displayName') -ieq $name) { $found = $l; break }
    }

    if (-not $found) {
        $colNames = ($spec.Columns | ForEach-Object { $_.name }) -join ', '
        if ($DryRun) {
            Write-Host "   Would create the list with columns: $colNames" -ForegroundColor Yellow
            [void]$summary.Add([pscustomobject]@{ List = $name; Action = 'Would create'; Columns = $colNames; Notes = '' })
            continue
        }
        $body = [ordered]@{
            displayName = $name
            description = $spec.Description
            columns     = @($spec.Columns)
            list        = [ordered]@{ template = 'genericList' }
        }
        $created = Invoke-Graph -Method POST -Uri "/sites/$siteId/lists" -Body $body
        $listIds[$name] = Get-Prop $created 'id'
        Write-Host "   Created with columns: $colNames" -ForegroundColor Green
        [void]$summary.Add([pscustomobject]@{ List = $name; Action = 'Created'; Columns = $colNames; Notes = '' })
        continue
    }

    $listId = Get-Prop $found 'id'
    $listIds[$name] = $listId
    $cols = Get-AllPages ("/sites/$siteId/lists/$listId/columns" + '?$select=name,displayName,indexed')
    $byName = @{}
    foreach ($c in $cols) {
        $n = Get-Prop $c 'name'
        if ($n) { $byName[$n.ToLowerInvariant()] = $c }
    }

    $added = New-Object System.Collections.ArrayList
    $notes = New-Object System.Collections.ArrayList
    foreach ($col in $spec.Columns) {
        $key = $col.name.ToLowerInvariant()
        if ($byName.ContainsKey($key)) {
            $wantIndexed = $col.Contains('indexed') -and $col.indexed
            if ($wantIndexed -and -not (Get-Prop $byName[$key] 'indexed')) {
                [void]$notes.Add("$($col.name) exists but is not indexed")
            }
            continue
        }
        if ($DryRun) {
            Write-Host "   Would add column $($col.name)" -ForegroundColor Yellow
        }
        else {
            [void](Invoke-Graph -Method POST -Uri "/sites/$siteId/lists/$listId/columns" -Body $col)
            Write-Host "   Added column $($col.name)" -ForegroundColor Green
        }
        [void]$added.Add($col.name)
    }

    if ($added.Count -eq 0) {
        Write-Host '   All columns present.'
        $action = 'Up to date'
    }
    elseif ($DryRun) { $action = 'Would add columns' }
    else { $action = 'Added columns' }
    if ($notes.Count -gt 0) { foreach ($n in $notes) { Write-Host "   Note: $n" -ForegroundColor DarkYellow } }
    [void]$summary.Add([pscustomobject]@{ List = $name; Action = $action; Columns = ($added -join ', '); Notes = ($notes -join '; ') })
}

# ---------------------------------------------------------------------------
# Optional roster import
# ---------------------------------------------------------------------------

$rosterSummary = New-Object System.Collections.ArrayList
if ($RosterCsv) {
    Write-Step "Roster import from $RosterCsv"
    if (-not (Test-Path -LiteralPath $RosterCsv)) { throw "Roster CSV not found: $RosterCsv" }
    # Warn (never stop) if the CSV sits inside a git working tree where it could be committed.
    $csvFull = (Resolve-Path -LiteralPath $RosterCsv).Path
    $csvDir = Split-Path -Parent $csvFull
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'   # git writes to stderr outside a repository; that is not an error here
        try {
            $inside = & git -C $csvDir rev-parse --is-inside-work-tree 2>$null
            if ($inside -eq 'true') {
                & git -C $csvDir check-ignore -q -- $csvFull 2>$null
                $isIgnored = ($LASTEXITCODE -eq 0)
                if (-not $isIgnored) { Write-Warning 'The roster CSV is inside a git repository and is not ignored. Move it outside the repository before committing.' }
            }
        }
        catch { }
        finally { $ErrorActionPreference = $prevEap }
    }
    $rows = @(Import-Csv -LiteralPath $RosterCsv)
    if ($rows.Count -eq 0) { throw 'The roster CSV has no rows.' }
    $headers = @($rows[0].PSObject.Properties | ForEach-Object { $_.Name })
    foreach ($h in @('Email', 'DisplayName')) {
        if (-not ($headers | Where-Object { $_ -ieq $h })) { throw "The roster CSV needs an '$h' column (columns: Email, DisplayName, JobTitle)." }
    }
    $hasJobTitle = [bool]($headers | Where-Object { $_ -ieq 'JobTitle' })

    $existingEmails = @{}
    $teamListId = $listIds['Ranger Team']
    if ($teamListId) {
        $items = Get-AllPages ("/sites/$siteId/lists/$teamListId/items" + '?$expand=fields($select=Title,Email)&$top=500')
        foreach ($it in $items) {
            $e = Get-Prop (Get-Prop $it 'fields') 'Email'
            if ($e) { $existingEmails[$e.Trim().ToLowerInvariant()] = $true }
        }
    }

    foreach ($r in $rows) {
        $email = ([string]$r.Email).Trim()
        $display = ([string]$r.DisplayName).Trim()
        $job = ''
        if ($hasJobTitle) { $job = ([string]$r.JobTitle).Trim() }
        if (-not $email) {
            [void]$rosterSummary.Add([pscustomobject]@{ DisplayName = $display; Email = ''; Action = 'Skipped (no email)' })
            continue
        }
        $key = $email.ToLowerInvariant()
        if ($existingEmails.ContainsKey($key)) {
            [void]$rosterSummary.Add([pscustomobject]@{ DisplayName = $display; Email = $email; Action = 'Already on roster' })
            continue
        }
        if (-not $display) { $display = $email }
        if ($DryRun -or -not $teamListId) {
            [void]$rosterSummary.Add([pscustomobject]@{ DisplayName = $display; Email = $email; Action = 'Would add' })
        }
        else {
            $fields = [ordered]@{
                Title            = $display
                Email            = $email
                JobTitle         = $job
                Active           = $true
                IncludeInUpdates = $true
            }
            [void](Invoke-Graph -Method POST -Uri "/sites/$siteId/lists/$teamListId/items" -Body ([ordered]@{ fields = $fields }))
            [void]$rosterSummary.Add([pscustomobject]@{ DisplayName = $display; Email = $email; Action = 'Added' })
        }
        $existingEmails[$key] = $true
    }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

Write-Step 'Summary'
if ($DryRun) { Write-Host 'Dry run. No changes were made.' -ForegroundColor Yellow }
$summary | Format-Table -AutoSize -Wrap List, Action, Columns, Notes | Out-String -Width 200 | Write-Host
if ($RosterCsv) {
    Write-Host 'Roster'
    $rosterSummary | Format-Table -AutoSize DisplayName, Email, Action | Out-String -Width 200 | Write-Host
}
Write-Host "Site hostname for the dashboard config: $siteHost"
Write-Host "Site path for the dashboard config:     $sitePath"
