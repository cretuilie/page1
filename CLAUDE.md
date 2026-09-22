# CLAUDE.md

Acest fisier ghideaza Claude Code cand lucreaza in acest repository.

## Ce este acest repo

Acest repository git este radacina la `C:\Users\cretu` (directorul home Windows al
utilizatorului), iar remote-ul lui este `https://github.com/cretuilie/page1`. In
practica, urmareste un singur proiect mic, **page1**: o pagina statica "Hello World".

- Fisier urmarit: [page1.html](page1.html) — o pagina HTML de sine statatoare (fundal
  gradient inchis, titlu cu efect de glow "Hello World!!! Sunt online!!!"). Fara build
  step, fara dependinte, fara framework.
- Deploy pe Vercel: [page1-eta-sable.vercel.app](https://page1-eta-sable.vercel.app)
  (dashboard: `vercel.com/cretuilies-projects/page1`). O copie folosita pentru deploy exista si la
  `D:\MyProjects\page1\index.html`; redeploy cu `vercel --prod` din acel folder.
- Remote GitHub: `origin` → `cretuilie/page1`, branch `main`.

## Important: acesta e directorul home al utilizatorului, nu un folder de proiect izolat

Deoarece radacina repo-ului este `C:\Users\cretu`, `git status` aici prinde si continut
personal/de sistem neasociat, care se afla intamplator in directorul home (de ex.
`AppData/`, `Desktop/`, `Documents/`, `OneDrive/`, `NTUSER.DAT*`, dar si scripturi
razlete precum `app.py`, `tic-tac-toe.html`, `python`). **Niciunul dintre acestea nu
face parte din proiectul page1** — sunt untracked si nu trebuie adaugate, commit-uite
sau curatate din greseala. Verifica intotdeauna cu atentie output-ul `git status` inainte
de a face stage la ceva aici si adauga doar fisierele care apartin efectiv proiectului
page1.

- `app.py` — un script de calculator in terminal, de sine statator (prompturi in
  romana, +/-/*/÷). Nu are legatura cu page1.
- `tic-tac-toe.html` — o pagina X si 0 de sine statatoare, fara legatura cu page1.
- `python` — un fisier razlet de 0 octeti (nu e director, nu e folosit de nimic aici).

## Notă istorică: erp-assistant a existat aici

Commit-uri mai vechi pe `main` au adaugat si iterat un proiect Python in
`projects/erp-assistant/` (un asistent Claude + API ExpertAccounts ERP, numit intern
"SuperMatrix"). Acel proiect a fost mutat in commit-ul `b6e04fb` ("Move erp-assistant
project to D:\MyProjects\erp-assistant") si acum locuieste integral la
`D:\MyProjects\erp-assistant` — e un proiect separat, doar local (intentionat nepush-uit
pe GitHub) si trebuie lucrat acolo, nu aici.

## Conventii de lucru

- Pastreaza acest repo strict pentru pagina statica page1. Daca ti se cere sa adaugi
  unelte sau scripturi neasociate, prefera sa le pui in `D:\MyProjects\<nume-proiect>`
  (preferinta generala a utilizatorului este sa salveze lucrul pe proiecte in
  `D:\MyProjects`).
- Pentru a publica modificari la page1: editeaza `page1.html` (si/sau copia Vercel de la
  `D:\MyProjects\page1\index.html`), fa commit, push pe `origin main`, apoi ruleaza
  `vercel --prod` din `D:\MyProjects\page1\` pentru redeploy.
