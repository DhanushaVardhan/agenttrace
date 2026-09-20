# Recording docs/demo.gif

The GIF at the top of the README is the single highest-leverage artefact in
this repo. Most people who open it will watch the GIF and read nothing else.

## What to record

The acceptance-test question, because it demonstrates four things at once:

> What's the customer due diligence threshold, and if a bank processes 40
> transactions at that exact amount, what's the total?

A good take shows, in order: the three documents in the corpus panel, the
question being asked, trace cards appearing one at a time, and the final
answer with citation chips.

## How

1. Start the app and wait for the sample corpus to finish indexing — the
   corpus panel should read `3 docs · 47 chunks` before you hit record.
2. Set the browser window to roughly 1280x800. Zoom the page to 110% so the
   trace text is readable when the GIF is scaled down in the README.
3. Record with [ScreenToGif](https://www.screentogif.com/) on Windows or
   [Kap](https://getkap.co/) on macOS. Capture just the browser window.
4. Keep it to 12-18 seconds. Trim the dead air before the first card appears.
5. Target under 8 MB: 12-15 fps and a 900px width is plenty. ScreenToGif's
   built-in optimiser gets there in one pass.
6. Save as `docs/demo.gif`.

## Rehearse it

This is also the interview demo. Run the query a few times before recording —
you want the version where the agent searches, reformulates once, then chains
into `calculate`, because a three-step trace tells the story better than a
one-step one.
