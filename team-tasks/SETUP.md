# Team Tasks Setup Guide

Ranger Team Tasks needs three things before anyone can use it: a SharePoint site to hold the data, four Microsoft Lists on that site, and an app registration in Entra ID so the page can sign people in and talk to Microsoft Graph. Plan on about an hour, most of it waiting on the Global Admin to click "Grant admin consent."

## What the dashboard needs and why

The dashboard page is public, like every other page in the suite, but it holds no task data. Everything (tasks, the roster, comments and the log of status emails) lives in Microsoft Lists inside our own Microsoft 365 tenant. The page shows a sign-in screen until someone signs in with their Longhorn Microsoft 365 account, then reads and writes the lists through Microsoft Graph with that person's own permissions. Someone outside the tenant who opens the page sees the sign-in screen and nothing else.

The page itself only carries the app's client ID, the tenant ID and the site address. Those are public identifiers for a single-page app and are safe to publish. There is no client secret, and one should never be created for this app. The browser keeps Microsoft's sign-in token cache, a few display preferences (last tab, Team layout, whether the Team filters are open, Team table sort, visible columns and column widths) and the time of your last visit to My Tasks. Tasks, the roster, comments and the status email log stay in the Microsoft Lists on the site.

Access is controlled in two places:

- Sign-in is limited to accounts in our tenant (the app is registered as single tenant), which covers every email domain in the tenant plus any guests invited through Entra B2B
- Data access follows SharePoint permissions on the site, so a person can only read or write the lists if they are a member of the site

## 1. Choose or create the SharePoint site

Use a private Microsoft 365 group site (a Teams team works too, since every team has one) whose membership is the Ranger team. List access then follows group membership, so adding someone to the group is all it takes to give them access to the data.

To create one, go to SharePoint, choose Create site, then Team site, set Privacy to Private, and name it something like Ranger Team. Add the team as members. If a private Ranger team or Teams channel already exists, its site works fine and nothing new needs to be created.

Write down the site URL. It looks like `https://contoso.sharepoint.com/sites/RangerTeam`, where `contoso.sharepoint.com` is the site hostname and `sites/RangerTeam` is the site path. Both go into the dashboard config in step 4.

Every member of the site can edit every item in the lists. The dashboard limits field edits to a task's owner and the person who assigned it, but that is a convention in the page. SharePoint is the actual security boundary, so only people who should see all Ranger tasks should be members of the site.

## 2. Create the lists with the provisioning script

The provisioning script (provision_lists.ps1) creates the four lists and all of their columns. It is safe to run more than once: it creates lists that are missing, adds columns that are missing and leaves everything else alone. It needs Windows PowerShell 5.1 or PowerShell 7 and one Microsoft module.

Open PowerShell in the folder that holds the script and install the module once:

```powershell
Install-Module Microsoft.Graph.Authentication -Scope CurrentUser
```

If PowerShell blocks the script because it was downloaded, allow it for this session only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Do a dry run first. It signs in, reads the site and reports what it would create without changing anything:

```powershell
.\provision_lists.ps1 -SiteUrl https://contoso.sharepoint.com/sites/RangerTeam -DryRun
```

Then run it for real:

```powershell
.\provision_lists.ps1 -SiteUrl https://contoso.sharepoint.com/sites/RangerTeam
```

The first run opens a Microsoft sign-in window and asks for the Sites.Manage.All permission. Sign in as someone who owns the site. If the tenant blocks user consent, the Global Admin will need to approve "Microsoft Graph Command Line Tools" once, or run the script themselves. Add `-TenantId <tenant ID>` if the sign-in lands in the wrong tenant.

The script ends with a summary table of each list and what it did, and prints the site hostname and site path for step 4.

**Optional roster import.** To load the team in one pass, save a CSV with these columns and add `-RosterCsv` to the command:

```csv
Email,DisplayName,JobTitle
first.last@example.com,First Last,Chief Credit Officer
```

Save the CSV outside the dashboards repository and pass its full path. The repository is public, and the CSV has real names and addresses. The script warns if the file sits inside a git repository where it could be committed.

```powershell
.\provision_lists.ps1 -SiteUrl https://contoso.sharepoint.com/sites/RangerTeam -RosterCsv $env:USERPROFILE\Documents\ranger-roster.csv
```

Rows whose Email is already on the Ranger Team list are skipped (the match ignores capitalization). New rows get Active and IncludeInUpdates set to Yes.

## 3. Register the app in Entra ID

**Check admin access first.** Before anything else, have the Global Admin sign in at entra.microsoft.com and confirm they can open both App registrations and Enterprise applications under Identity, then Applications, and that "New registration" is available. If they cannot, check Microsoft 365 admin center, then Roles, to see who holds Global Administrator or Application Administrator, and have IT assign one of those roles to a Longhorn account before continuing.

If App registrations works, register the app:

1. In the Entra admin center go to Identity, Applications, App registrations, then New registration
2. Name it Ranger Team Tasks
3. Under Supported account types choose "Accounts in this organizational directory only" (single tenant)
4. Under Redirect URI choose the platform **Single-page application** and enter the first URI below, then Register
5. Open Authentication on the new app and add the other two redirect URIs under the same Single-page application platform:
   - `https://nbsimonetti.github.io/ranger-dashboards/team-tasks/team-tasks.html`
   - `https://ranger-dashboards.onrender.com/team-tasks/team-tasks.html`
   - `http://localhost:8765/team-tasks/team-tasks.html`
6. Leave implicit grant (access tokens and ID tokens) unchecked, since MSAL uses the authorization code flow with PKCE
7. Open API permissions, choose Add a permission, Microsoft Graph, Delegated permissions, and add:
   - User.Read
   - Sites.ReadWrite.All
   - Mail.Send
   - People.Read
   - User.ReadBasic.All
8. Click **Grant admin consent for [tenant]** and confirm. Every permission should show a green check under Status
9. From the Overview page copy the **Application (client) ID** and the **Directory (tenant) ID** for step 4

Do not add a client secret or certificate. A single-page app cannot keep one private.

**What the permissions do.** All five are delegated, so the app can never do more than the signed-in person could do themselves. Sites.ReadWrite.All reaches only the sites that person already has access to. Mail.Send sends from the person's own mailbox and the message lands in their Sent Items. People.Read and User.ReadBasic.All power the people picker when adding a one-off recipient.

**Tighter alternative: Sites.Selected.** If IT prefers, Sites.Selected can replace Sites.ReadWrite.All so the app can reach only the Ranger site. It takes three changes. Add the delegated Sites.Selected permission in place of Sites.ReadWrite.All and grant consent. An admin then grants the app write access to the one site, either with Graph (`POST /sites/{site-id}/permissions` with role `write` and the app's client ID, run by someone with Sites.FullControl.All) or with PnP PowerShell (`Grant-PnPAzureADAppSitePermission -AppId <client ID> -DisplayName "Ranger Team Tasks" -Site <site URL> -Permissions Write`). Last, the scope list in the dashboard needs Sites.Selected in place of Sites.ReadWrite.All. Users still need to be members of the site either way.

## 4. Connect the dashboard

Open the dashboard file (team-tasks.html) in a text editor. The config block is at the very top of the main script. Fill in the four blank values:

```js
const TT_CONFIG = {
  clientId: '',        // Application (client) ID from step 3
  tenantId: '',        // Directory (tenant) ID from step 3
  siteHostname: '',    // e.g. contoso.sharepoint.com
  sitePath: '',        // e.g. sites/RangerTeam
  dashboardUrl: '',    // leave blank to use the page's own address in email links
  lists: {
    tasks: 'Ranger Tasks',
    team: 'Ranger Team',
    updates: 'Ranger Status Updates',
    comments: 'Ranger Task Comments'
  },
  pollSeconds: 60
};
```

Set `dashboardUrl` only if email links should always point to one address (for example the GitHub Pages address) no matter which copy of the page sent them. Leave the list names alone unless the lists were renamed in SharePoint.

Commit and push team-tasks.html so the live site picks it up (for example `git add team-tasks/team-tasks.html`, which stages only that file). Until these values are filled in, the page shows a "Setup needed" screen and no task screens.

The page loads Microsoft's sign-in library from a CDN with an integrity check. If the library version in `MSAL_SRC` ever changes, recompute `MSAL_SRI` for the new file (jsDelivr's data API lists the hash for each file), or the browser will refuse to load it.

## 5. Fill in the Ranger Team list

The Ranger Team list drives the owner dropdowns, the Team view and the status email recipients. Skip this step if the roster CSV was imported in step 2.

Open the site, go to Site contents, open Ranger Team and add one row per person:

| Column | What to enter |
|---|---|
| Title | The person's display name, as it should appear on tasks and in emails |
| Email | Their primary Microsoft 365 email address, the one their Outlook mail comes from |
| JobTitle | Optional |
| Active | Yes. Set to No when someone leaves the team |
| IncludeInUpdates | Yes if they should receive everyone's status emails |
| CanEditAll | Yes for whoever runs the weekly meeting and needs to update anyone's task. No for everyone else (the default) |

The tenant has more than one email domain, so use each person's primary address. Capitalization does not matter. The dashboard matches the signed-in account to this row by email, so a typo here means that person sees an empty My Tasks list.

## 6. Test with ?test=1 before real use

Add `?test=1` to the end of the address, for example `https://nbsimonetti.github.io/ranger-dashboards/team-tasks/team-tasks.html?test=1`. A banner reading "Test mode: emails go only to you" appears, and every email the page sends (status updates, assignment notices and comment emails) goes only to the signed-in person, regardless of the roster.

Run through this list:

1. Sign in and confirm your name shows in the header and the roster count on How It Works matches the Ranger Team list
2. Add a few tasks starting with "TEST -" and check that they appear as rows in the Ranger Tasks list in SharePoint
3. Assign one to another team member, complete one, reopen it, and add a comment with the email box checked
4. Open the Status Update tab, review the preview and send. Confirm it arrives in your inbox, shows in your Sent Items, and appears on the History tab
5. Delete the TEST tasks when done (deleted tasks go to the site recycle bin)

Drop `?test=1` only once all of that works.

For a look at the screens with no sign-in at all, `http://localhost:8765/team-tasks/team-tasks.html?demo=1` runs the page against fictional sample data when served from a local preview. Demo mode only works on localhost, saves nothing and sends nothing.

## 7. Adding or removing a team member

**Adding someone:**

1. Add them to the Microsoft 365 group (or the team in Teams) that owns the site, which gives them access to the lists
2. Add a row for them to the Ranger Team list with Active and IncludeInUpdates set to Yes, using their primary email address (see the table in step 5)
3. Send them the dashboard link the team uses, the GitHub Pages address from the redirect list in step 3 (`https://nbsimonetti.github.io/ranger-dashboards/team-tasks/team-tasks.html`). They sign in with their Microsoft 365 account and need no other setup. Group membership can take up to an hour to reach SharePoint, so a person added minutes ago may see "No access yet" until it does. Pages that are already open pick up roster changes within about 5 minutes, or at once with Refresh

**Adding a guest from outside the tenant:** invite them as a guest in Entra (Identity, Users, Invite external user), then do steps 1 and 2 above using their own email address. Guests can view, add and edit tasks, but they have no mailbox in our tenant, so sending status emails from the page will fail for them. They can use the Copy to clipboard or Open in Outlook buttons instead.

**Removing someone:**

1. Reassign their open tasks from the Team view
2. Set Active to No on their Ranger Team row. Their completed tasks and past status updates stay on record, and they drop out of the owner dropdowns and recipient list
3. Remove them from the Microsoft 365 group so they lose access to the lists

There is no need to delete the roster row, and keeping it with Active set to No preserves the record of who was on the team.

## 8. Troubleshooting

**AADSTS50011 (redirect URI mismatch).** The page address does not exactly match a redirect URI on the app registration. Compare the address bar (ignoring anything after `?`) to the list under Authentication, including https versus http, the full path and capitalization, and add the missing one under the Single-page application platform.

**AADSTS9002326 (cross-origin token redemption).** The redirect URI was added under the Web platform instead of Single-page application. Remove it from Web and add it under Single-page application.

**AADSTS65001 or AADSTS90094 (consent required).** Admin consent has not been granted, or a permission was added after consent was granted. The Global Admin opens API permissions on the app and clicks Grant admin consent again. Every row should show a green check.

**AADSTS50020 (user not found in tenant).** The person signed in with an account from another organization or a personal Microsoft account. They need to sign in with their Longhorn account, or be invited as a guest first.

**AADSTS700016 (application not found).** The client ID or tenant ID in the config block is wrong, or the app was registered in a different tenant. Recopy both values from the app's Overview page.

**Graph 403 on the lists.** The person is not a member of the site, or consent for Sites.ReadWrite.All is missing. Check group membership first, then API permissions. If Sites.Selected is in use, confirm the app was granted write access to this specific site.

**Graph 404 or "list not found".** The site hostname or path in the config block is wrong, or a list was renamed. The site path should look like `sites/RangerTeam` with no leading slash and no `https://`. The list names in the config must match the list names in SharePoint exactly. Running the provisioning script again recreates any list that is missing.

**Status email will not send.** The page shows the Graph error text. The usual causes:

- ErrorAccessDenied or 403: Mail.Send consent is missing, so grant admin consent again
- MailboxNotEnabledForRESTAPI or a mailbox not found error: the person has no Exchange Online mailbox, which is common for guests and for accounts without a mail license
- In both cases the Copy to clipboard and Open in Outlook buttons still work, and the person can send from Outlook by hand

**Someone sees an empty My Tasks list but the Team view shows their tasks.** The Email on their Ranger Team row does not match the address they signed in with. Fix the row.

**"You signed in as ..., and that address is not on the Ranger Team list."** The Email on the person's Ranger Team row does not match the address shown in that notice. Change the row to the address in the notice (or add the row if it is missing), then have them press Refresh. The page also matches a row under the account's other addresses, such as its sign-in name, so this usually means a typo or a row that was never added.

**"No access yet."** The account signed in but cannot open the team site. If the person was added to the site's Microsoft 365 group within the last hour, the membership has not reached SharePoint yet, so wait and try again. Otherwise add them to the group, and check that the address in the message is the account that was added.

**AADSTS50105 (user is not assigned to the application).** Assignment is required on the Ranger Team Tasks enterprise application, and this person (or a group they belong to) is not assigned. In the Entra admin center open Enterprise applications, then Ranger Team Tasks, then Users and groups, and assign the person or the Ranger group. Turning off Assignment required under Properties also works if every tenant account should be able to sign in.

## Data model

The provisioning script creates these four lists. Column names below are the internal names the dashboard reads and writes, so do not rename them. Choice values for Status, Priority and Workstream can be edited in SharePoint, and the dashboard picks up the new values on the next load.

**Ranger Tasks**

| Column | Type | Notes |
|---|---|---|
| Title | Single line of text | The task |
| Notes | Multiple lines, plain | |
| OwnerEmail | Single line of text | Indexed |
| OwnerName | Single line of text | |
| AssignedByEmail | Single line of text | Indexed |
| AssignedByName | Single line of text | |
| Status | Choice | Not Started, In Progress, Blocked, Done. Default Not Started. Indexed |
| Priority | Choice | High, Normal, Low. Default Normal |
| DueDate | Date only | |
| CompletedDate | Date and time | Set when a task is marked Done |
| Workstream | Choice | Regulatory & Closing, Lending, Deposits & Treasury, Operations & IT, Compliance, Marketing & Brand, Real Estate & Offices, Hiring, Board & Investors, Other. Default Other |
| SortOrder | Number | Order within a person's list |
| AssignedAt | Date and time | When the current owner got the task |

The SharePoint Created By field records who created each task and is used for delete rights.

**Ranger Team**

| Column | Type | Notes |
|---|---|---|
| Title | Single line of text | Display name |
| Email | Single line of text | Indexed |
| JobTitle | Single line of text | |
| Active | Yes/No | Default Yes |
| IncludeInUpdates | Yes/No | Default Yes |
| CanEditAll | Yes/No | Default No. Yes lets that person edit any task, for running the weekly meeting |

**Ranger Status Updates**

| Column | Type | Notes |
|---|---|---|
| Title | Single line of text | Email subject |
| SenderEmail | Single line of text | Indexed |
| SenderName | Single line of text | |
| SentAt | Date and time | |
| PeriodStart | Date only | |
| PeriodEnd | Date only | Drives the "since my last update" default |
| CompletedCount | Number | |
| OpenCount | Number | |
| Recipients | Multiple lines, plain | Semicolon separated |
| Body | Multiple lines, plain | The email HTML as sent |
| Kind | Choice | Personal, Team. Default Personal. Whether the row is a personal update or a Team Summary |
| FullTeam | Yes/No | Default Yes. No when the sender left part of the team off, so the next update does not start from it |

**Ranger Task Comments**

| Column | Type | Notes |
|---|---|---|
| Title | Single line of text | First 60 characters of the comment |
| TaskId | Number | ID of the task in Ranger Tasks. Indexed |
| AuthorEmail | Single line of text | |
| AuthorName | Single line of text | |
| Body | Multiple lines, plain | |

**Why owners are stored as email text.** SharePoint person columns look like the natural fit, but Graph can only set one by passing the person's lookup ID from the site's hidden user list, and that ID only exists once the person has visited the site or been added to it by hand. Storing the email and display name as plain text avoids that lookup, works for guests and for people who have never opened the site, and keeps filtering simple on indexed text columns. The tradeoff is that a name change does not flow through on its own. The email is the key the dashboard matches on, and an updated name on the Ranger Team row shows on new tasks going forward.
