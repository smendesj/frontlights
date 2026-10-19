# Progress question in any project, and a start by plain words (manual; no model score claimed)

Setup: the project that declares the `roadmapSync.progress` block (approved, secret present), a second project with
an enabled `roadmapSync` block but no progress block, and a third with no `.frontlights/config.json` at all. Nothing is
registered yet. The skill is installed by the junction and its `description` names the plain-language triggers.

Expected, in this order:

1. `/frontlights` in the second project: the issue-gaps question is asked as before; the progress question is not, and
   the session asks once "Registrar o projeto que guarda o bloco do Resumo para a diretoria?" with the options "Sim,
   escolher a pasta" and "Agora não"; "Agora não" ends it for the session. In the third project the session says
   nothing about it.
2. The user answers yes to registering the project that declares the block. The session looks, read-only, for the
   folders next to the project whose config has an enabled progress block and offers each one in full as an option
   (the free-text choice takes another folder); it says that the registration only says where the block is and lives
   in the home directory, and the user's pick is the explicit yes that runs `progress_report.py home --set <project>`. `home` alone shows it registered and valid.
3. `/frontlights` in the second and in the third project: the question "Atualizar também o Resumo para a diretoria no
   RoadS?" appears, with the project where the block lives named in its text. "Sim, preparar o resumo agora" runs
   `window`, `collect`, `shots` and `push` with `--root <operationsRoot>`; the collectors run from the project that
   declares the block, and the approval record is written there, not in the project the session opened.
4. A project with its own block, even a disabled one, never uses the registration. A registration file copied from
   another machine, edited by hand or with a changed path reads `invalid`: no progress question, only the registration question.
5. `home --clear` after an explicit yes removes it; the question goes away.
6. Start a fresh session with a plain phrase ("frontlights, ataque a issue <n>") and no slash: the model opens the
   command and the stage 1 questions come before any other work. Repeat with the opt-in hook installed
   (`skills/frontlights/templates/frontlights-prompt-hook.py`): the reminder is in the turn, stage 1 opens first, and a second mention in
   the same session adds no second reminder. A path such as `.frontlights/config.json` in a prompt adds none.

Reject: the registration written without the user's yes; a block that runs without its own approval because it was
found through the registration; a project's config file that points the session at another folder; the progress
question asked with `ask` false; a hook that blocks a prompt; claiming that the hook was verified in a real session
before it was.
