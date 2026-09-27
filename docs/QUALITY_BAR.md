# Quality bar: nothing reaches the owner that isn't good enough to ship

**Owner:** CRITIC · **Applies to:** every maker on the crew.
**Rule:** <one sentence the whole crew can remember, e.g. "Everything must look deliberately made
by a skilled human. If someone could say 'that's AI' at a glance, it fails, however good the
rest is.">

> **How to fill this in.** Replace every `<...>` with your project's specifics. Keep each
> hard-fail item concrete enough that two reviewers would agree on it. Add a row to §0 and a
> subsection to §1 for each kind of work your crew makes. Date every change to a bar, and
> never lower one to hit a deadline.

---

## 0. The gate (what reaches the owner)

| Work | Machine gate (automatic) | Human gate (CRITIC) | Owner sees it when |
|---|---|---|---|
| <e.g. Web page> | <e.g. tests pass, linter clean, no console errors> | Score **≥ 9/10**, **zero hard fails**, batch review passes | both gates pass |
| <e.g. Written copy> | <e.g. spell check, banned-phrase list> | Score **≥ 9/10**, zero hard fails | both pass |
| <kind of work> | <automatic checks, or "none yet"> | <score and conditions> | <when> |

- The default bar is `HQ_PASS_SCORE` (9); `hq.report submit` refuses anything lower.
- **Hard fail = instant reject**, whatever the score. A score is only recorded after the
  hard-fail list has been walked.
- **Tie-break:** if you're unsure whether something passes, it doesn't. Reject it and name the fix.

---

## 1. Hard-fail list (instant reject)

### 1.1 Every kind of work
1. **Sameness.** Two pieces a stranger could confuse side by side, or a new piece that is an
   old one re-skinned (a font or colour swap on the same skeleton). Both fail.
2. **Invented facts.** A number, quote, source, review or claim that can't be traced to a real
   source.
3. **Someone else's IP.** Brands, logos, characters, celebrities, lyrics, known slogans, or
   copied text or art.
4. **Placeholder or filler left in.** Lorem ipsum, "Your Business", TODO, sample data shown as
   real, decorative filler that says nothing.
5. **Broken basics.** Spelling or grammar errors, broken links, broken layout at phone width,
   text contrast under 4.5:1, errors in the console or the logs.

### 1.2 <Kind of work, e.g. Visual assets>
1. <A concrete, checkable failure, e.g. "garbled or pseudo text anywhere in an image".>
2. <...>

### 1.3 <Kind of work, e.g. Written copy>
1. <e.g. "stock phrases: 'perfect for', 'high quality', 'elevate', 'seamless'".>
2. <...>

---

## 2. Craft principles (what skilled humans do)
<!-- Five to ten short principles for your domain, each with the reason. These are what turns a
     7 into a 9. Example: "One focal point per screen: the eye needs one place to land." -->
- <principle>: <why>.

---

## 3. Scoring rubric (1-10, with anchors)

Score honestly; the anchors calibrate the number.

| Work | 5 = generic / template / AI-looking | 7 = competent, not yet good enough | 9 = the best in its class |
|---|---|---|---|
| <kind> | <what a 5 looks like, concretely> | <what a 7 looks like: clean but one weak element> | <what a 9 looks like: specific, distinct, nothing to remove> |

**Anti-inflation:** a 9 has to be earned against the anchors, not granted because nothing is
broken. "No defects" alone is a 7-8. Before giving ≥ 9, name what makes this piece better than
our other recent work of its kind; if you can't, it isn't a 9.

**Caps (before rounding):**
- Any hard fail → **max 4**.
- An automatic flag that nobody has checked and explained in the notes → **max 7**.
- Work that can't be judged as the owner will see it (missing preview, broken file) → **no
  score**; send it back.

---

## 4. How to look

- **Open everything yourself.** Never score from a summary, a filename or metadata.
- **See it the way the audience will:** full size *and* at thumbnail / phone width (about
  375 px); in the context it will live in (the page, the feed, the inbox).
- **Judge in the batch:** build a contact sheet (all the batch's pieces side by side, plus our
  live work of the same kind) and compare each piece against every other. Score in context,
  never alone.
- **Walk §1 item by item** and write the walk into the notes (`HF: ... ok`).
- **What's automated vs what needs eyes:**

| Check | Where | Effect |
|---|---|---|
| <e.g. tests / lint> | <command> | <blocks / flags> |
| <e.g. banned-phrase list> | <command> | <blocks / flags> |

---

## 5. Banned phrases and patterns (copy)
<!-- The words and tics your crew must never use, with the plain alternative. -->
| Don't write | Write instead |
|---|---|
| <e.g. "Elevate your experience"> | <say the specific thing it does> |
