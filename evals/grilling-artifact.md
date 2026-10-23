# Visual artifact in the grilling and in the list of slices (manual; no model score claimed)

Setup: a disposable request that changes one screen of a small web app (a form with three fields and a save
button, rendered from a template in the repository), in a host with the artifact tool (`Artifact` in Claude
Code), with a test account and the base able to come up. A second run of the same case in a host without the
tool, a third run, with the tool, of a request without a screen (an API change that adds a layer), and a fourth
run of the screen case with no test account available and the base failing to come up.

Expected, in this order:

1. Stage 3, problem round: before the problem is confirmed, the session publishes one artifact (a private
   page) with the **before** of the form as a print of the system running at the base (`origin/<base>`), taken
   with a test account and test data in the disposable Chrome window of the watched run and cleaned by the rule
   of `references/browser-testing.md` ("Clean"), entered as an image of the artifact, and the confirmation
   question cites its section ("artefato, seção 1: antes"). The page source is
   written to `.frontlights/artifact.html` (untracked), and the confirmation gets no section of its own.
2. Stage 3, solution round and decision tree: the same page, on the same URL, gains one section per decision
   question, numbered after the before: the solution round (the **after** of the form for each of the three
   approaches, each the same print with markings overlaid in HTML: boxes, arrows and texts) and every branch
   asked, the pre-mortem included; a naming branch gets its section too. Every
   section follows `templates/grilling-section.html` and the rule of `references/grilling.md` ("The
   artifact"): it explains what the question implies without repeating it, always carries the Visual of its
   kind of question, the Cenário por opção (with fictitious data) and the Consequências, and omits the other
   empty fields. Where the
   project already does this shows path:line and a real excerpt of up to 15 lines, with any secret value
   replaced by `***`. Each option's `preview` stays text (files, pattern fit, effort, seam) and every decision
   question names its section. Each section is written into the local source by `frontlights.py artifact section` and the whole
   source is published once per round on the same URL, never by `edits`; there is never one page per round: the URL
   never changes.
3. The request without a screen gets, in the same place, a diagram of the flow and of the layers (or of the
   current rule), the base and with each option, instead of a form, and one section per decision question as well.
4. The discovery log carries the URL and the source path in its "Artifact URL and source path" line, written at
   the first publication and never changed; every section cited in the interview belongs to that one page.
   With the local file deleted mid-interview (a new session), the session reads the published page back with
   the artifact tool's read and goes on editing that copy, on the same URL.
5. Stage 5, the quiz: the numbered list of the slices shows, for each slice, its title, "Depende de", what it
   delivers and the section of the artifact that shows what it delivers, one section per slice on the same URL
   as the grilling, numbered after the grilling's sections (the form as it stands once that slice lands); then
   the quiz asks the same three things as before (granularity, real dependencies, merge or split). A slice whose
   drawing shows nothing demonstrable is fixed before the quiz, with no extra question.
6. In the host without the tool: one line says the visual is not available, the interview and the quiz go on in
   text, and the log's line reads "artefato indisponível".
7. In the run with no test account and the base down: the grilling stops at the problem round and goes on only
   once a test account exists (any existing one, or one the session creates) and the base is up.

Reject: a screen rebuilt from the template or redrawn in the style of the page instead of the print, or an after
that is not the same print with markings; a print with real data, a real login or a person's name; the grilling
going on without the print when there is a screen; an inline widget instead of the page; a page per round, a new URL after the first
publication, or the whole page rewritten to add a section; real data, a real record, a person, an endpoint or
a client on the page, or a code excerpt with a secret value left in clear; a decision question that cites no
section; a decision branch without a section (a naming decision, say); a section for a
confirmation or the closing "Seguimos?"; a section that departs from the model's fields or keeps an empty
field; a section that repeats the question instead of saying what it implies; a section without Visual, Cenário
por opção or Consequências; the quiz changed into something other than granularity, dependencies and merge or split; a slice drawn
in the list but with no answer to "what can be demoed"; a script that builds the page; the session skipping
the artifact in silence when the tool is missing; a new page started when the local source is missing instead
of the published one read back.
