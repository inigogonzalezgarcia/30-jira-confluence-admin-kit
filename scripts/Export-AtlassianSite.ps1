<#
.SYNOPSIS
    Read-only export of a Jira + Confluence Cloud site to the CSV files used by jcadmin (everything except users.csv).

.DESCRIPTION
    Writes to the output folder:
      group_members.csv  members of the admin groups (and any extra groups you name)
      projects.csv       projects with lead, last issue update, issue count, permission and workflow scheme, and whether
                         the permission scheme grants Browse Projects to Anyone
      spaces.csv         Confluence spaces with type, status, last page update, page count, admins and anonymous access
      sprints.csv        the last sprints of every Scrum board with committed, completed, added and carried-over estimates
      custom_fields.csv  custom fields with type, contexts, projects and last used date

    users.csv comes from admin.atlassian.com (Directory > Users > Export users, with last-seen dates): the user export
    there is richer than anything the site REST API returns.

    It only reads (GET requests). Authentication is your Atlassian e-mail and an API token typed into the Get-Credential
    prompt; nothing is stored. Use an account with site admin rights, or the counts will be limited to what it can see.

    Sprint numbers come from the Sprint Report data behind Jira's own report (rest/greenhopper/1.0/rapid/charts/sprintreport).
    It is not a documented public API and may change; if it fails, the script still writes the sprint dates and leaves the
    estimate columns empty.

.PARAMETER Site
    https://your-site.atlassian.net

.PARAMETER OutputFolder
    Default .\data

.PARAMETER AdminGroups
    Groups to export members of. Default: site-admins, org-admins, jira-admins, confluence-admins.

.PARAMETER SprintsPerBoard
    How many closed sprints per board to export (default 8), plus the active and future ones.

.EXAMPLE
    .\scripts\Export-AtlassianSite.ps1 -Site https://fabrikam-robotics.atlassian.net -OutputFolder .\data
    python -m jcadmin review .\data
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Site,
    [string] $OutputFolder = '.\data',
    [string[]] $AdminGroups = @('site-admins', 'org-admins', 'jira-admins', 'confluence-admins'),
    [int] $SprintsPerBoard = 8
)

$ErrorActionPreference = 'Stop'
$Site = $Site.TrimEnd('/')
New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null
$cred = Get-Credential -Message 'Atlassian e-mail and API token (id.atlassian.com > Security > API tokens)'
$pair = '{0}:{1}' -f $cred.UserName, $cred.GetNetworkCredential().Password
$headers = @{ Authorization = 'Basic ' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pair)); Accept = 'application/json' }

function Get-Json([string] $Path) {
    Invoke-RestMethod -Method Get -Uri ($Site + $Path) -Headers $headers
}

function Get-Paged([string] $Path, [string] $Items = 'values') {
    $start = 0; $out = @()
    do {
        $sep = if ($Path.Contains('?')) { '&' } else { '?' }
        $r = Get-Json ("{0}{1}startAt={2}&maxResults=50" -f $Path, $sep, $start)
        $page = @($r.$Items)
        $out += $page
        $start += $page.Count
    } while ($page.Count -gt 0 -and -not $r.isLast -and ($null -eq $r.total -or $start -lt $r.total))
    return $out
}

function Day($value) { if ($value) { ([datetime]$value).ToString('yyyy-MM-dd') } else { '' } }

# ---- group members ----------------------------------------------------------------------------------------------
Write-Host 'Group members...'
$members = foreach ($g in $AdminGroups) {
    try {
        foreach ($m in Get-Paged ("/rest/api/3/group/member?groupname={0}&includeInactiveUsers=true" -f [uri]::EscapeDataString($g))) {
            [pscustomobject]@{ Group = $g; Member = if ($m.emailAddress) { $m.emailAddress } else { $m.accountId } }
        }
    } catch { Write-Warning "group $g not found or not readable" }
}
$members | Export-Csv (Join-Path $OutputFolder 'group_members.csv') -NoTypeInformation -Encoding UTF8

# ---- projects ---------------------------------------------------------------------------------------------------
Write-Host 'Projects and schemes...'
$anyoneCache = @{}
$projects = foreach ($p in Get-Paged '/rest/api/3/project/search?expand=lead,insight') {
    $perm = Get-Json ("/rest/api/3/project/{0}/permissionscheme" -f $p.id)
    if (-not $anyoneCache.ContainsKey($perm.id)) {
        $full = Get-Json ("/rest/api/3/permissionscheme/{0}?expand=permissions" -f $perm.id)
        $anyoneCache[$perm.id] = [bool]($full.permissions | Where-Object { $_.permission -eq 'BROWSE_PROJECTS' -and $_.holder.type -eq 'anyone' })
    }
    $wf = ''
    try { $wf = (Get-Json ("/rest/api/3/workflowscheme/project?projectId={0}" -f $p.id)).values[0].workflowScheme.name } catch { }
    [pscustomobject]@{
        Key = $p.key; Name = $p.name; 'Project type' = $p.projectTypeKey
        Lead = if ($p.lead.emailAddress) { $p.lead.emailAddress } else { $p.lead.accountId }
        'Last issue update' = Day $p.insight.lastIssueUpdateTime; Issues = $p.insight.totalIssueCount
        'Permission scheme' = $perm.name; 'Workflow scheme' = $wf
        'Browse anyone' = if ($anyoneCache[$perm.id]) { 'Yes' } else { 'No' }
        Archived = if ($p.archived) { 'Yes' } else { 'No' }; Category = $p.projectCategory.name
    }
}
$projects | Export-Csv (Join-Path $OutputFolder 'projects.csv') -NoTypeInformation -Encoding UTF8

# ---- confluence spaces ------------------------------------------------------------------------------------------
Write-Host 'Confluence spaces...'
$spaces = @(); $cursor = "/wiki/api/v2/spaces?limit=100"
while ($cursor) {
    $r = Get-Json $cursor
    foreach ($s in $r.results) {
        $cqlLast = [uri]::EscapeDataString("space=`"$($s.key)`" order by lastmodified desc")
        $last = Get-Json "/wiki/rest/api/search?cql=$cqlLast&limit=1"
        $cqlPages = [uri]::EscapeDataString("space=`"$($s.key)`" and type=page")
        $pages = (Get-Json "/wiki/rest/api/search?cql=$cqlPages&limit=1").totalSize
        $perms = @(); $pc = "/wiki/api/v2/spaces/$($s.id)/permissions?limit=250"
        while ($pc) { $pr = Get-Json $pc; $perms += $pr.results; $pc = $pr._links.next }
        $admins = $perms | Where-Object { $_.operation.key -eq 'administer' -and $_.principal.type -eq 'user' } | ForEach-Object { $_.principal.id }
        $anon = [bool]($perms | Where-Object { $_.principal.type -eq 'anonymous' -and $_.operation.key -eq 'read' })
        $spaces += [pscustomobject]@{
            Key = $s.key; Name = $s.name; Type = $s.type; Status = $s.status
            'Last updated' = Day $last.results[0].lastModified; Pages = $pages
            Admins = ($admins | Select-Object -Unique) -join '; '; 'Anonymous access' = if ($anon) { 'Yes' } else { 'No' }
        }
    }
    $cursor = $r._links.next
}
$spaces | Export-Csv (Join-Path $OutputFolder 'spaces.csv') -NoTypeInformation -Encoding UTF8
Write-Host '  note: space admins are exported as account ids; jcadmin matches them against the Account id column of users.csv.'

# ---- sprints ----------------------------------------------------------------------------------------------------
Write-Host 'Scrum boards and sprints...'
function Sum-Estimates($issues, $keys) {
    $t = 0.0
    foreach ($i in @($issues)) { if (-not $keys -or $keys.ContainsKey($i.key)) { $t += [double]($i.estimateStatistic.statFieldValue.value) } }
    return $t
}
$sprints = foreach ($b in Get-Paged '/rest/agile/1.0/board?type=scrum') {
    $all = Get-Paged ("/rest/agile/1.0/board/{0}/sprint" -f $b.id)
    $closed = @($all | Where-Object state -eq 'closed' | Sort-Object { [datetime]$_.endDate } | Select-Object -Last $SprintsPerBoard)
    $rest = @($all | Where-Object state -ne 'closed')
    foreach ($s in $closed + $rest) {
        $committed = $completed = $added = $carried = ''
        if ($s.state -eq 'closed') {
            try {
                $rep = (Get-Json ("/rest/greenhopper/1.0/rapid/charts/sprintreport?rapidViewId={0}&sprintId={1}" -f $b.id, $s.id)).contents
                $addedKeys = @{}; foreach ($k in $rep.issueKeysAddedDuringSprint.PSObject.Properties.Name) { $addedKeys[$k] = $true }
                $completed = [double]$rep.completedIssuesEstimateSum.value
                $carried = [double]$rep.issuesNotCompletedEstimateSum.value
                $added = (Sum-Estimates $rep.completedIssues $addedKeys) + (Sum-Estimates $rep.issuesNotCompletedInCurrentSprint $addedKeys)
                $committed = $completed + $carried + [double]$rep.puntedIssuesEstimateSum.value - $added
            } catch { Write-Warning "sprint report not available for $($b.name) / $($s.name)" }
        }
        [pscustomobject]@{
            Board = $b.name; Project = $b.location.projectKey; Sprint = $s.name; State = $s.state
            Start = Day $s.startDate; End = Day $s.endDate; 'Complete date' = Day $s.completeDate
            Committed = $committed; Completed = $completed; 'Added after start' = $added; 'Carried over' = $carried
        }
    }
}
$sprints | Export-Csv (Join-Path $OutputFolder 'sprints.csv') -NoTypeInformation -Encoding UTF8

# ---- custom fields ----------------------------------------------------------------------------------------------
Write-Host 'Custom fields...'
$fields = foreach ($f in Get-Paged '/rest/api/3/field/search?type=custom&expand=lastUsed,contextsCount,projectsCount') {
    [pscustomobject]@{
        Name = $f.name; Type = $f.schema.custom -replace '^.*:', ''
        Contexts = $f.contextsCount; Projects = if ($f.isGlobal -or -not $f.projectsCount) { 'Global' } else { $f.projectsCount }
        'Issues with value' = ''   # not available from this endpoint; jcadmin then relies on Last used
        'Last used' = if ($f.lastUsed.type -eq 'TRACKED') { Day $f.lastUsed.value } else { '' }
    }
}
$fields | Export-Csv (Join-Path $OutputFolder 'custom_fields.csv') -NoTypeInformation -Encoding UTF8

Write-Host "Done. Add users.csv from admin.atlassian.com and settings.json, then: python -m jcadmin review $OutputFolder"
