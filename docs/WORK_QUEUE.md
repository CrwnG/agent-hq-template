# Work queue (ARCHITECT-assigned work for the crew)

The daily shift works through **Open**, top to bottom, before starting anything new. ARCHITECT
adds items here after reviews (CRITIC's fixes become items) and after reading the owner's notes
on rejected approvals.

> **How to use this file.**
> - One item = one deliverable, with the ids or paths it touches, the fix or spec, and who does
>   it (`@builder`). Write it so an agent with no memory of today can do it.
> - Put a header with the date and the reason on each batch of items.
> - When an item is done, move it to **Done** with the date and the result (paths, ids). Keep
>   **Done** to the last couple of weeks; git history holds the rest.
> - Anything the crew can't do alone goes under **Needs owner**, with what exactly the owner
>   has to do and roughly how long it takes.

## Open (next daily run)

<!-- ARCHITECT <YYYY-MM-DD>, from <CRITIC's review of ... / the owner's note on #...> -->
1. **<Short title>** (@builder): <what to change, where, and what "done" means>.

## Needs owner

<!-- Blocked until the owner acts: money, accounts, credentials, taste calls, heavy jobs that
     need the owner's go-ahead (e.g. GPU work while they're away from the machine). -->
- **<What>** (about <N> min): <exact steps>. Unblocks: <which Open items>.

## Held

<!-- Parked on purpose, with the reason and what would un-hold it. Failed twice at CRITIC,
     waiting on an outside answer, or not worth doing yet. -->
- **<What>**: <why it's held>; <what would un-hold it>.

## Done

<!-- <YYYY-MM-DD> (@role): <what was done>, <output paths / approval ids>. -->
