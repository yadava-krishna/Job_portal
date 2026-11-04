# ATS company directories

`jobsync_greenhouse.json`, `jobsync_lever.json` and `jobsync_ashby.json` are unmodified copies of the
company directories (`{name, token}` board identifiers) from **JobSync**
(https://github.com/Gsync/jobsync, `src/lib/scraper/{greenhouse,lever,ashby}/companies.json`,
commit `8c20325c35dbf203334a270cef5aef446f06a774`), used under the MIT licence reproduced in
`JOBSYNC_LICENSE` (Copyright (c) 2024 gsync).

Only the data is reused; no JobSync code is copied. Board tokens can go stale (the employer moves ATS
or renames the board). JobPilot treats a 404 from the job-board API as "board not found" and reports it.

`curated_india.json` is JobPilot's own list of India-relevant employers whose boards were checked
against the official APIs on the date recorded in the file.
