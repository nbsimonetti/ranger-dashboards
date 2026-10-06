# Iteration 2: Team Critique + Improvements

v1 worked end to end, but walking through it as the five people who will actually use it showed the same gap each time: the data was there, but the page made people go find it. The CEO could not tell who was overloaded without scrolling, assigning during the meeting meant leaving the Team view, a lender needed 6-7 taps to add a task due tomorrow, the Friday email overlapped the prior week and read like a system export, an assignee had no idea a task had landed or why, and a newcomer stuck on the wrong roster address got a message that never said which address the page saw. The changes below close each of those, add three optional SharePoint columns (all of which degrade cleanly on lists provisioned before them), and leave the v1 conflict handling, reauth handling, test mode, escaping, permissions and polling guards in place.

---

## What each persona asked and what we found

### 1. The CEO running Monday's team meeting

**Questions:** Can I see in 30 seconds what's overdue, what's blocked and who is overloaded? Can I assign three new action items during the meeting in under a minute? Does the Team view print or screen-share cleanly?

**Found:**
- Person cards showed only "N open, M overdue" in 12px text and sorted alphabetically, so the most overdue person sat below the fold at 1280x720
- Chrome plus an always-open filter block took ~65% of the screen before the first task, and the Team table scrolled inside its own box
- Assigning an action item meant leaving Team for My Tasks, so the shared screen lost the list being discussed, and Owner was the last quick-add control. Nobody could see the assignee's list while typing, which is how a near-duplicate task got added
- Overdue and Blocked were mutually exclusive filters, there was no Today window, and "Completed this week" on a Monday showed only Monday
- Nobody marked as running the meeting could check off a teammate's task when they reported it done
- Print had no as-of date, squeezed the Task column, printed bare "Fri" dates, wrapped pills, split cards across pages and printed viewer-specific text like "(you)"

### 2. A lender working from a phone between calls

**Questions:** Can I add a task in two taps? Can I mark something done without opening a panel? Does anything require horizontal scrolling at 375px?

**Found:**
- No Today / Tomorrow / Next week shortcuts. The date sat behind Options as a bare date input, so a task due tomorrow took 6-7 taps, and "tomorrow" typed in the title was ignored
- Checking a task removed the row at once with no Undo, and the next task's checkbox slid under the finger, so a double tap completed the wrong task
- Most phone controls were under 40px (24px checkbox, 20px title button, 30px selects, 31px Save), and 13px selects made iOS Safari zoom on every focus
- No horizontal scroll at 375px on any tab, which held

### 3. A team member sending their Friday update

**Questions:** Is the email ready to send with no editing if I've kept my list current? Does it read like something a person wrote? Did it go to the right people and land in my Sent Items?

**Found:**
- "Since my last update" started on the day of the last send, so the subject overlapped last week, and a one-day range read "Oct 5 – Oct 5"
- First-time senders saw "Since my last update" selected while the page actually used This Week, and there was no Last week preset
- A mid-week one-off to one person became the baseline for the next update and silently dropped Monday and Tuesday work
- At 1024x768 the To/Cc chips sat below the fold in the left column while Send was on the right, and the confirm dialog gave a count with no names
- In test mode the screen still showed four teammates, a Cc, no TEST prefix and "Send update", so it was hard to trust what would happen
- After a send the preview flipped to an empty next draft, which looked like an empty email had gone out
- The email still read as generated: an underlined workstream subheading, "(no due date)" and " – Blocked" tags, no intro spacing, a bare link with no name at the end, Completed sorted by due date, and no reason next to anything Blocked
- Fixing a stale due date before sending took 5 clicks through My Tasks, and outside test mode there was no way to see the real email in your own Outlook first

### 4. Someone who was just assigned a task

**Questions:** Did I find out? Can I see who assigned it and why? Can I push back or comment without a separate email chain?

**Found:**
- The notice linked to the bare dashboard, which opened on whatever tab was used last, and nobody could copy a link to one task
- The notice and quick-add left out notes and priority, and handing a task back read as "[Name] assigned you"
- Nothing marked what was new. A task assigned a minute ago looked like one from last month, and a reassigned task only showed its original Created date
- Polling replaced tasks and comments silently, so a new assignment, a reply or a teammate's edit appeared with no toast or highlight
- Comments notified nobody, and the placeholder implied the owner would hear about it
- A comment typed in the box was thrown away when the person clicked Save, because the box was left out of the unsaved-changes check
- In Assigned by Me, Last change ignored comments and done tasks disappeared

### 5. A newly added team member

**Questions:** After an admin adds them to the Ranger Team list, can they sign in and use it with no other setup?

**Found:**
- Mostly yes, but the two places a newcomer gets stuck (not on the roster, no site access yet) never said which account the page had signed them in with
- How It Works told admins to use "the email they sign in with", which contradicted the Team Tasks Setup Guide's primary-address rule and could produce a roster row that never matches
- The first screen said only "No open tasks. Add one above." with nothing about the list being shared or what sends email, How It Works opened with an admin table, and the Assigned by Me empty state pointed to a button that does not exist
- Step 7 of the Team Tasks Setup Guide skipped the group membership delay and had no troubleshooting entries for the messages a newcomer actually sees

---

## What shipped

### Team view and the weekly meeting
- **Team load table** above the person cards, built from every task regardless of filters: Open, Overdue, Blocked, Due this week, High and Done last week per active member, sorted by overdue, then blocked, then open. Every number is a button that sets the Owner filter plus the matching window (e.g. Taylor's Overdue shows only Taylor's overdue work). Overdue and Blocked above zero are tinted red, zeros are muted. Under 700px it drops High and Done last week and uses short headers (Late, Week) so it fits 343px
- **Person cards** sort the same way (alphabetical order is gone) and the header reads "5 open, 1 overdue, 1 blocked, 2 due this week", leaving out zero parts
- **Add straight onto a teammate's card:** every active member's card has an add row with a due shortcut (No date / Today / Tomorrow / Fri / Next Mon). Enter adds the task to that person with their usual workstream, notifies them, names the saved title and due date in the toast, highlights the new row for 2 seconds and keeps focus in the box. Typed text survives polls and teammate edits
- **Needs attention** button and Date windows for Due today, Needs attention (overdue, blocked or due today, worst first) and Completed last week. Completed windows show "N done" headers, sort newest first and drop the strikethrough
- **Filters start closed** at every width with a "Filters (n)" toggle remembered per browser, and the chips row stays visible. The Team load table and first card now sit above y=720
- **Can edit all:** a new CanEditAll column on Ranger Team lets whoever runs the meeting check off or edit anyone's task. Delete rules are unchanged, and How It Works still says the edit rules are a convention kept by the page that SharePoint does not enforce
- **Print** prints the layout on screen (By Person as a checklist with cards kept whole, Table as a table), with an "As of" line carrying the team counts and active filters, real dates in place of relative labels, Age and Assigned by hidden, "N comments" spelled out and no viewer-specific text
- The Team table grows with the page, so there is one scrollbar. The sticky header could not follow the page through the horizontal scroll box, so it is now static

### My Tasks and quick add
- **Due shortcuts** (Today, Tomorrow, Fri, Next Mon, Pick date) under the title at every width. On a Friday the Fri shortcut reads Next Fri, and a shortcut that falls on the same date as an earlier one is left out, so two shortcuts are never pressed for one date
- **Dates typed in the title:** a parser reads a date at the end of the title ("tomorrow", "tmrw", "friday", "by fri", "next week", "10/13", with a leading "by", "on" or "due" stripped). Short weekday names count only after "by", "on" or "due", so "Call Sun" stays whole, and m/d counts only when that date comes round within 60 days, so a period end like "Reconcile GL to 9/30" typed in October keeps its text and gets no date. When the title gives a date, the line under it reads "For Riley. Saves as "Call bank about renewal". Due Wed Oct 7", with the year when it is not this year, and a Keep text button saves the title as typed. The line sits on its own, so the Add button never moves. A task due tomorrow is now type and tap Add
- **Today group** between Overdue and Due This Week, its heading marked with a warn-colored dot
- **Undo on check-off:** the row stays in place struck through for ~4 seconds, the toast "Marked done: [Title]" carries an Undo button that restores the old status, and a second tap within 600ms is ignored so the next row is never completed by mistake. From the keyboard, focus stays on the same row's checkbox (now Mark not done), then moves to Undo once the row leaves the list, and the toast does not time out while focus or the pointer is on it. Undo waits while a dialog is open and asks you to close the task first when its panel has unsaved edits. Team cards behave the same way
- **Faster assigning:** options reordered to Owner, Due, Priority, Workstream, Notify. Enter works from any option field. Workstream follows the new owner's most common one until someone picks by hand, and every add resets to you, Normal priority and your usual workstream. One toast covers the add and the notice ("Added to Sam's list. Sam was notified.")
- **Phones:** 44px touch targets on buttons, tabs, KPIs, toast actions, the Notify and comment email checkboxes and Leave test mode, 40px on the Team load numbers and the pick-list Open buttons, 32px on recipient chip remove buttons, a 44x44 hit area around the checkbox, 16px fields so iOS does not zoom, visible field labels on the Options fields, and a tap anywhere on a row's text opens the task
- First-run empty state explains that the list, notes and comments are visible to the whole team and what Status Update does, and a privacy line sits under the quick-add bar and the panel Notes label

### Assignments, comments and what is new
- **Task links:** assignment and comment notices link to the task itself. Opening a link starts on the right tab (My Tasks, Assigned by Me or Team) without passing through My Tasks, scrolls to the row, highlights it and opens the panel, and a deleted task says so. Links made in test mode keep the test flag, as does the dashboard link in a status email sent in test mode, so following one stays in test mode. The address bar follows the open task and the tab (#my, #team, #update etc.), and a Copy link button sits in the panel header
- **Notices with the why:** "Jordan Avery assigned you: [Title], due Oct 9, High priority." then the note or task notes, then "Questions or a different date: comment on the task." Hand-backs read "[Name] handed back: [Title]." followed only by the comment typed with the hand-back, if any, and "Questions for [first name]: comment on the task." Hand-offs read "[Name] handed you: [Title] (assigned by [Assigner])." with the assigner on Cc. Quick-add and the Assign dialog take an optional note, saved to Notes (or as a comment if Notes already has text)
- **Panel header** above the fields: "[Assigner] assigned this to you on [time]", the notes, and a Reply button that jumps to the comment box. The time comes from a new AssignedAt column, so a reassigned task shows when it became yours
- **New markers:** a New pill on tasks assigned to you since your last visit, "1 new comment" in bold in place of the comment count, and a strip at the top of My Tasks ("Assigned to you since your last visit: 1. New comments: 1.") whose parts jump to the row. Only a timestamp is stored in the browser, and demo mode stores nothing
- **Live changes:** each poll compares the fresh data with what is on screen. A new assignment or a new comment on your work shows a toast with an Open button, and a teammate's edit highlights the row for ~3 seconds. The toast names the first change in full and counts the rest by kind ("Also 1 new comment."). Open asks before discarding unsaved edits in an open panel and waits while a dialog is open
- **Comment emails:** a checkbox under the comment box, on by default between owner and assigner and off for anyone else, with a hint that everyone on the team can read comments and, when no email goes out, that none is sent
- **Save keeps the comment:** a typed comment posts with Save (and rides along in a hand-back notice), and Close, Cancel or Esc with an unposted comment asks before discarding. A posted or discarded comment is gone from the box when the task is reopened; a half-written one survives only redraws while the panel stays open. If the task saves but the comment does not post, the panel stays open with the comment in the box and a warning that holds until the comment posts
- **Assigned by Me:** Last change uses the newer of the last edit and the last comment ("Comment by Taylor Brooks, [time]"), the comment count goes bold when the owner wrote after your last word, and tasks finished in the last 7 days show under Done in the last 7 days
- **Blocked reasons:** setting Status to Blocked asks "What is it waiting on?" and saves the answer as a "Blocked: " comment. Rows, the Team table and the status email show "Waiting on: [reason]", taken from that comment, else the first line of Notes, else the owner's latest comment

### Status Update
- **Period:** "Since my last update" starts the weekday after the last send (a Friday send starts Monday), still counts anything finished after the send, and prints a single date for a one-day range. Last week is a preset. First-time senders see This Week selected (Last 7 days in Team Summary)
- **Partial sends:** an email that leaves part of the default team off is saved with FullTeam set to No and does not become the start of the next update (or team summary, in that mode), and a line under the actions says so before sending. On a list that does not have FullTeam yet, the line says the send will become the start of the next one
- **Layout:** To, Cc, Subject, preview and actions now read top to bottom in the right column, so recipients are visible next to Send at 1024x768. The confirm dialog names everyone ("...to Jordan Avery, Riley Chen, Sam Patel and Taylor Brooks, with you on Cc."), falling back to a count over 8
- **Test mode** shows exactly what happens: one "You ([address])" chip, a line naming who it would go to without test mode, no Cc, a TEST: prefix and a "Send test to me" button. The test banner has a Leave test mode link that drops only the test flag
- **After a send** the preview keeps the sent email read-only with "Sent [time] to [names]. Saved to History." and Send stays disabled until Start the next one is clicked
- **Polls leave the tab alone** when nothing in the email changed, and focus stays on the same pick-list checkbox or chip when it does
- **The email reads like a person wrote it:** no underlined subheading (and none when everything is one workstream), no "(no due date)" or " – Blocked" tags, the first label sits flush at the top when there is no intro, Completed sorts oldest finished first, open lines read "Build loan pricing grid (blocked, due Oct 9): CD-secured rate decision", and the sender's first name sits above the link
- **Open from the pick list** fixes a stale task in the side panel without leaving the tab, and overdue rows show how late they are in red
- **Send to me first** sends the current email to you only with a TEST: subject and logs it to History as a test, so it never moves the period start

### Newcomers and setup
- The not-on-roster notice names the signed-in address on both My Tasks and Status Update ("You signed in as [address], and that address is not on the Ranger Team list..."), and the no-access screen names the account, mentions the up-to-an-hour group delay and drops the setup-guide reference
- The page matches a roster row under any of the account's addresses (mail, sign-in name, account username), so an alias no longer leaves someone off the list. Once matched, comments carry the roster address, and the page recognizes every one of the account's addresses on rows SharePoint stamps, so the user's own comments, sends and test sends count as theirs
- How It Works opens with The tabs, adds What sends email (and what does not) and the Ctrl+Enter shortcut, explains hand-backs, and moves the roster instructions to the end under "For whoever manages the Ranger Team list" with the primary-address rule. The sign-in screen asks for the account used for Outlook and Teams
- The Assigned by Me empty state points to the real ways to assign, and Team Summary has its own note
- The Team Tasks Setup Guide: step 7 uses the primary address, names the live link, explains the group membership delay and the ~5-minute roster refresh, and Troubleshooting covers "You signed in as ... not on the Ranger Team list", "No access yet" and AADSTS50105. The data model lists the new columns. The guide still carries no names, emails or tenant IDs

### New SharePoint columns

| List | Column | Type | Purpose | On an older list |
|---|---|---|---|---|
| Ranger Tasks | AssignedAt | Date and time | When the current owner got the task | Writes retry once without it and skip it for the session; the header falls back to Created |
| Ranger Team | CanEditAll | Yes/No, default No | Lets the meeting lead edit any task | Reads as No |
| Ranger Status Updates | FullTeam | Yes/No, default Yes | No when part of the team was left off | Reads step down to Kind, then to neither; writes drop only the column SharePoint names and skip it for the session; until FullTeam exists a partial send counts as the last update |

Running the list provisioning script again adds all three to existing lists without touching anything else.

---

## Files changed

| File | Change |
|---|---|
| Ranger Team Tasks dashboard | Everything above. New pure helpers duePresets, parseDueToken, blockedReason and taskUrl (all on window.TT), Team load, card add rows, toast actions, sync change detection, comment notices, task links, Status Update signature skip, and GraphStore / DemoStore parity for aliases, AssignedAt, CanEditAll and FullTeam. Demo seed adds an inactive member with an old done task and an active member left off the status email list |
| List provisioning script | AssignedAt on Ranger Tasks, CanEditAll on Ranger Team, FullTeam on Ranger Status Updates |
| Team Tasks Setup Guide | CanEditAll in the step 5 table, step 7 rewrite, three new troubleshooting entries, data model rows for the new columns |
| Team Tasks Iteration 2 Changes | This document |

Two new Store methods, in both GraphStore and DemoStore: setIdentity (write the roster address the page matched) and canMarkPartial (whether the status list can record a partial send). Everything else uses the existing listTasks, listComments, sendMail and addComment calls. The demo seed gives one person a mailbox address that differs from their roster row, so demo mode exercises alias matching.

---

## What's NOT changed

These came up during the critique and were deliberately left out:

- **Phone layout above the list** (one line of counts, no reorder arrows, a single-row or bottom tab bar). Layout preference with a large CSS and markup cost, and the up/down arrows are the only reorder path on touch. The Today group, the due shortcuts and Undo cover the lender's actual job
- **Tappable status pill menu on each row.** A second inline editing surface with its own eTag, permission and conflict paths for a 4-tap action the panel already handles
- **Due-date popover on the row's due label.** Another inline editor with focus and conflict handling. The panel due shortcuts cut the same action to ~3 taps
- **Text search on My Tasks and Team.** None of the Iteration 2 questions needs it, and Owner, Needs attention and Team load cover meeting and phone use. A candidate for a later iteration
- **Reordering the phone edit panel** into title / due / status, comments, then More fields. Most of the value came from the assignment header with Reply and comment-on-Save, and a full reorder risks the conflict notices
- **Sticky bottom Send bar and collapsed pick list on phones.** Moving To/Cc above Subject fixed recipient visibility, phones already show To above Send, and a sticky bar adds layout risk at 375px
- **Automatic comments on every date, status or owner change.** It would write a comment row on every edit and flood threads and the new comment notices. Comment notices, Last change with comments, Done in the last 7 days and live highlights give the assigner the same visibility
- **ReturnedBy column and a "Returned by" meta line.** Another SharePoint column for a marginal gain. The hand-back notice and the comment that now posts with Save already say the task came back and why
- **A separate "Print by person" table variant.** Print now uses the layout on screen, so By Person already prints as a per-person checklist
- **Field names inside closed quick-add selects on desktop** ("Priority: Normal"). Taste, and it breaks the shared ranger-select display. Phones get visible labels and desktop has tooltips and aria-labels
- **Renaming History or adding a count.** Naming taste. The tabs section in How It Works explains what History holds
- **Workstream default from the last pick in the session.** Folded into the owner's most-used workstream default, which works for your own tasks and assignments with no extra state

The v1 data handling is unchanged: eTag and pre-flight conflict checks, ambiguous-write recovery, silent token refresh with a click-to-sign-in banner, polling that pauses when hidden and skips around in-flight saves, ?test=1 routing all mail to the signed-in user, demo mode only on localhost with ?demo=1, escaping of every user string, and no task or roster data in browser storage.

---

## Verification

Run in a local preview with ?demo=1 at 1280x720, 1024x768 and the 375x812 mobile preset, with the console clean on every tab and node --check passing on the page script.

- **Team load:** 6 active members listed (the demo seed now includes an active member left off the status email list), sorted by overdue, blocked, open. Jordan and Riley lead because each has an overdue and a blocked task. The whole table and the first card sit above y=720. Taylor's Overdue number sets Owner: Taylor Brooks and Date: Overdue and shows only "Update CIP procedures"
- **Card add:** "Order appraisal for Smith Ranch renewal by fri" in Riley's card lands in Riley's card at once, highlighted, due Fri, "by fri" stripped from the title, focus kept, Outbox 0 to 1, and the toast reads "Added to Riley's list: Order appraisal for Smith Ranch renewal, due Fri Oct 9." Each card's due select and Add button carry the person's name. Two more in Casey's and Sam's cards took the Team count from 20 to 23 without leaving Team. Text typed in Sam's box survived Simulate a teammate edit
- **Due shortcuts:** "Call bank about renewal tomorrow" showed "Saves as "Call bank about renewal". Due Wed Oct 7", and Add saved it without "tomorrow". "Plan Q1 offsite 11/20" with Keep text saved the title whole with no date, and "Reconcile GL to 9/30" showed no date line. The Fri chip set Oct 9. The panel Tomorrow chip saved. With today Oct 6, parseDueToken gave no date for "Reconcile GL to 9/30", "Call Sun" and "Draft Reg O memo part 1/2", Oct 30 for "Q3 call report 10/30" and "Send docs" due Oct 9 for "Send docs by fri"; with today Dec 20, "Plan 1/5" was due Jan 5. The shortcuts read Today, Tomorrow, Next Mon on a Thursday and Today, Tomorrow, Next Mon, Next Fri on a Friday
- **Undo:** as Casey, checking "Draft credit policy section on CRE" kept the row in place struck through with "Marked done: ..." and Undo. A fast second click did not reopen it, and Undo restored Not Started with completed cleared
- **Period:** as Jordan (seed update Friday Oct 2, 4:15 PM) the period ran Oct 5 to Oct 6. Sam's Period select showed This week. Removing Riley, Sam and Taylor showed the partial line, the send saved FullTeam No, and the note still named the Friday update. Last week showed Sep 28 to Oct 4. A same-day resend printed a single date
- **Recipients and send:** as Casey at 1024x768, To (Jordan, Riley, Sam, Taylor, not Pat or Jamie) and Cc sat above the subject. The dialog named all four, the sent email stayed in the preview with Send disabled until Start the next one, and focus stayed on a pick-list checkbox through a sync. ?demo=1&test=1 showed the single You chip, the "Without test mode..." line, no Cc, TEST: and Send test to me, and Leave test mode pointed at ?demo=1 only
- **Email text:** no underline, no "no due date", no " – Blocked", first label at margin 0 0 4px, "Casey" above the link, "Review appraisal vendor options" with no parentheses, and "Build loan pricing grid (blocked, due Oct 9): CD-secured rate decision" after setting Blocked with that reason
- **Task links:** the quick-add notice linked to ?demo=1&task=34. ?demo=1&task=11 opened the panel on "Build loan pricing grid" (on Assigned by Me for Jordan, since he assigned it to Casey) and the task parameter dropped on close. task=9999 showed the deleted message and #update opened on Status Update. Copy link wrote the link or, where the browser blocks the clipboard, shows it in the toast
- **Notices:** "Jordan Avery assigned you: Pull BSA/AML policy gap list, due Oct 9, High priority." then "FDIC asked for this first", the comment line and the task link. Taylor's hand-back read "Taylor Brooks handed back: ..." and carried the comment typed before Save. Riley's hand-off to Sam read "...(assigned by Jordan Avery)" with Jordan on Cc
- **New markers:** as Taylor, the New pill, "Assigned to you since your last visit: 2. New comments: 1.", "1 new comment" on "Write BSA/AML risk assessment", and the reassigned task's header showed today's time. No seenAt key in localStorage in demo
- **Live changes:** a task created for Taylor behind the page produced "Jordan Avery assigned you: Live test." with Open, which opened the panel. An assignment plus a comment read "...assigned you: [Title]. Also 1 new comment.", and two assignments read "...Also 1 more task now on your list." With unsaved edits and a typed comment in another task's panel, Open asked "Discard your changes?" and Cancel kept both, and the row highlight cleared after ~3 seconds. Simulate a teammate edit highlighted the row on My Tasks and Team
- **Comments:** Taylor's comment on Jordan's task had the email box checked, posted with an Outbox message to Jordan containing the text and a task link. Sam on Casey's task had it unchecked with "No email is sent." Jordan's Assigned by Me showed "Comment by Taylor Brooks, [time]" in bold and Sam's finished task under Done in the last 7 days. Esc with an unposted comment showed "You have a comment that is not posted."
- **Needs attention, Today, last week:** Riley's "Confirm core conversion timeline" sat under Today. Needs attention showed only overdue, blocked or due-today tasks, with Taylor's 5-days-overdue item first in Table. Completed last week showed "N done", no strikethrough. On this Tuesday the third KPI read Completed last week and clicked through to that window
- **Can edit all:** Jordan's checkbox on Casey's task was enabled and canEdit was true for any task. Sam saw Casey's tasks read-only
- **Print:** with the print rules applied, the As of line showed the counts and "Filters: None", due cells printed dates ("5 days overdue (Oct 1)", "Wed Oct 7"), Age and Assigned by were hidden, comments printed as "N comments", and no "(you)" text showed. The Team table's scrollHeight equaled its clientHeight
- **Phones:** the checkbox hit area measured 44x46, Add 44px, the Priority select 16px, Team load numbers at least 40x40 with a 45px row pitch and the table exactly 313px, the pick-list Open buttons 40px tall, Leave test mode 44px, a tap on a row's meta line opened the panel, and scrollWidth was 375 on all six tabs. The quick-add note shows with Options collapsed
- **Newcomer:** with Sam removed from the roster, both My Tasks and Status Update showed "You signed in as sam.patel@example.com...". How It Works starts with The tabs and covers What sends email and Ctrl+Enter. Sam's empty list showed the first-run text with 18px padding, and Jordan's empty Assigned by Me showed the new text. The Team Tasks Setup Guide covers AADSTS50105 and uses only the example.com placeholder address
