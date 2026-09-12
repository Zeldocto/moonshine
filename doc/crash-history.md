# Crash report history

Moonshine stores new crash reports in `/Moonshine data/crashes/` on the launcher's
storage device. Each report has a generation number in its name, for example
`moonshine_crash_00000017.txt`, with matching `.core` and `.bin` files when those
captures completed. Keep the matching files together when reporting a crash.
The existing `tools/decode_crash.py` accepts either binary file by its full path;
its format and checksums are unchanged.

The launcher retains the newest 16 checked reports. A minimal `.core` capture
counts as a report even if the larger capture could not finish. Migrated legacy
`moonshine_crash_a/b` files remain available separately and are not rotated out.

The kernel reads only the crash directory to choose the next generation. Even
an unfinished file reserves its name after reboot. A failed directory scan
disables crash-file writing for that boot, rather than guessing a name that may
already belong to a report. Existing files at the directory path are preserved.

New generations never overwrite older reports. Binary output is flushed, closed
and read back before it counts as saved. An unsuccessful write leaves all older
generations intact; ordinary retries use the same new generation. Old reports
are removed only after the new capture and its text have saved successfully.
A failed cleanup can leave more than 16 reports temporarily; the next successful
capture retries cleanup. Optional full capture can later supplement the same
minimal report without allocating another history entry.

`scripts/test_crash_history.py` runs the production kernel initialization and
service against a simulated FatFS. It covers retention, generation wrap, legacy
files, partial/corrupt reports, delayed full capture, directory errors, and
failures while opening, writing, flushing, closing or checking output. These
checks do not establish hardware crash handling or SD-card power-loss guarantees.
