# Visual artifact in the grilling and in the list of slices (manual; no model score claimed)

Setup: a disposable request that changes one screen of a small web app (a form with three fields and a save
button, rendered from a template in the repository), in a host with the artifact tool (`Artifact` in Claude
Code). A second run of the same case in a host without the tool.

Expected, in this order:

1. Stage 3, problem round: before the problem is confirmed, the session publishes one artifact (a private
   page) with the **before** of the form built from the real template of the component (its HTML, its CSS and
   its three fields, read from the repository), filled with fictitious data only (made-up names, numbers and
   texts), and the confirmation question cites its section ("artefato, seção 1: antes").
2. Stage 3, solution round: the same page, on the same URL, gains one section for the round with the **after**
   of the form for each of the three approaches; each option's `preview` stays text (files, pattern fit,
   effort, seam) and names the section that shows its after. A decision-tree branch that changes what the user
   sees updates the page again on the same URL and cites its section; a branch that does not (a naming
   decision, say) adds nothing to the page. There is never one page per round: the URL never changes.
3. A request without a screen (an API change that adds a layer) gets, in the same place, a diagram of the flow
   and of the layers, before and after, instead of a form.
4. The discovery log carries the URL in its "Artifact URL" line, written at the first publication and never
   changed; every section cited in the interview belongs to that one page.
5. Stage 5, the quiz: the numbered list of the slices shows, for each slice, its title, "Depende de", what it
   delivers and the section of the artifact that shows what it delivers, one section per slice on the same URL
   as the grilling (the form as it stands once that slice lands); then the quiz asks the same three things as
   before (granularity, real dependencies, merge or split). A slice whose drawing shows nothing demonstrable is
   fixed before the quiz, with no extra question.
6. In the host without the tool: one line says the visual is not available, the interview and the quiz go on in
   text, and the log's "Artifact URL" line reads "artefato indisponível".
7. A request that touches no screen, flow or layer (a wording change in a document), even in the host without
   the tool: no artifact is published, the log's "Artifact URL" line reads "não se aplica", and the stage 5 list
   says once that it carries no section and goes on with the same quiz.

Reject: a real screenshot of the running product in the grilling, or an inline widget instead of the page; a
free sketch where the template exists in the repository; a page per round, or a new URL after the first
publication; real data, a secret, an endpoint, a person or a client on the page; a question that touches the
screen, the flow or the layers without citing a section; the quiz changed into something other than
granularity, dependencies and merge or split; a slice drawn in the list but with no answer to "what can be
demoed"; a script that builds the page; the session skipping the artifact in silence when the tool is missing;
a page published for a request that touches no screen, flow or layer.
